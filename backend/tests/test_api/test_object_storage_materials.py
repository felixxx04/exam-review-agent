from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api.dependencies import get_object_storage
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.models import Material
from app.main import app
from app.services.object_storage import (
    ObjectStorageError,
    PresignedGet,
    StoredObject,
)


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _data(response):
    payload = response.json()
    assert payload["success"] is True
    return payload["data"]


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.presigned: list[str] = []
        self.fail_delete = False

    async def put_file(
        self,
        *,
        key: str,
        source: Path,
        size_bytes: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        content = source.read_bytes()
        assert len(content) == size_bytes
        assert hashlib.sha256(content).hexdigest() == sha256
        self.objects[key] = content
        return StoredObject(
            key=key,
            size_bytes=size_bytes,
            etag="fake-etag",
            version_id="fake-version",
        )

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        version_id: str | None = None,
    ) -> None:
        destination.write_bytes(self.objects[key])

    async def delete_object(
        self,
        *,
        key: str,
        version_id: str | None = None,
    ) -> None:
        if self.fail_delete:
            raise ObjectStorageError("Object storage is temporarily unavailable", "OBJECT_STORAGE_UNAVAILABLE")
        self.deleted.append(key)
        self.objects.pop(key, None)

    async def presign_get(
        self,
        *,
        key: str,
        filename: str,
        content_type: str,
        disposition: str,
        expires_in_seconds: int,
        version_id: str | None = None,
    ) -> PresignedGet:
        self.presigned.append(key)
        return PresignedGet(
            url="https://storage.example.test/owner-only?signature=redacted",
            expires_in_seconds=expires_in_seconds,
        )


class ParserStub:
    async def parse(self, file_path, file_type=None):
        from app.services.parser_service import ParseResult

        assert Path(file_path).read_bytes() == MINIMAL_PDF
        return ParseResult(chunks=[], page_count=1)


@pytest.fixture
def object_storage(monkeypatch):
    storage = FakeObjectStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    monkeypatch.setattr("app.services.parser_service.ParserService", lambda: ParserStub())
    yield storage
    app.dependency_overrides.pop(get_object_storage, None)


@pytest.mark.asyncio
async def test_upload_stores_a_private_object_and_hides_internal_storage_fields(
    client_with_db, db_session, object_storage
):
    response = await client_with_db.post(
        "/api/materials",
        files={"file": ("../../course-notes.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert response.status_code == 200
    data = _data(response)
    assert data["original_filename"] == "../../course-notes.pdf"
    assert "object_key" not in data
    assert "storage_path" not in data
    assert "parse_error" not in data

    material = await db_session.get(Material, data["id"])
    assert material is not None
    assert material.object_key in object_storage.objects
    assert material.object_key is not None
    assert "course-notes.pdf" not in material.object_key
    assert material.storage_status == "available"


@pytest.mark.asyncio
async def test_rejected_file_signature_creates_no_object_or_material_reservation(
    client_with_db, db_session, object_storage
):
    response = await client_with_db.post(
        "/api/materials",
        files={"file": ("forged.pdf", b"this is not a PDF", "application/pdf")},
    )

    assert response.status_code == 400
    assert (await db_session.execute(select(Material))).scalars().all() == []
    assert object_storage.objects == {}


@pytest.mark.asyncio
async def test_identical_upload_in_the_same_course_is_rejected_without_a_second_object(
    client_with_db, db_session, object_storage
):
    first = await client_with_db.post(
        "/api/materials",
        files={"file": ("first.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert first.status_code == 200

    duplicate = await client_with_db.post(
        "/api/materials",
        files={"file": ("copy.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_MATERIAL"
    materials = (await db_session.execute(select(Material))).scalars().all()
    assert len(materials) == 1
    assert len(object_storage.objects) == 1


@pytest.mark.asyncio
async def test_owner_can_get_a_short_lived_download_url_but_other_users_cannot(
    client_with_db, db_session, object_storage
):
    uploaded = await client_with_db.post(
        "/api/materials",
        files={"file": ("notes.pdf", MINIMAL_PDF, "application/pdf")},
    )
    material_id = _data(uploaded)["id"]

    owner = await client_with_db.get(
        f"/api/materials/{material_id}/access-url?disposition=attachment"
    )
    assert owner.status_code == 200
    access = _data(owner)
    assert access["url"].startswith("https://storage.example.test/")
    assert access["expires_in_seconds"] == 300
    assert "object_key" not in access

    other = AuthenticatedUser(
        id=999,
        username="other-user",
        role="user",
        session_id="other-session",
    )
    app.dependency_overrides[get_current_user] = lambda: other
    try:
        denied = await client_with_db.get(f"/api/materials/{material_id}/access-url")
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=1,
            username="test_user",
            role="user",
            session_id="test-session",
        )

    assert denied.status_code == 404
    assert len(object_storage.presigned) == 1


@pytest.mark.asyncio
async def test_material_delete_removes_private_object_before_forgetting_metadata(
    client_with_db, db_session, object_storage
):
    uploaded = await client_with_db.post(
        "/api/materials",
        files={"file": ("notes.pdf", MINIMAL_PDF, "application/pdf")},
    )
    material_id = _data(uploaded)["id"]
    material = await db_session.get(Material, material_id)
    assert material is not None
    object_key = material.object_key

    deleted = await client_with_db.delete(f"/api/materials/{material_id}")

    assert deleted.status_code == 200
    assert object_key in object_storage.deleted
    assert object_key not in object_storage.objects
    assert await db_session.get(Material, material_id) is None


@pytest.mark.asyncio
async def test_delete_keeps_database_metadata_when_object_storage_delete_fails(
    client_with_db, db_session, object_storage
):
    uploaded = await client_with_db.post(
        "/api/materials",
        files={"file": ("notes.pdf", MINIMAL_PDF, "application/pdf")},
    )
    material_id = _data(uploaded)["id"]
    object_storage.fail_delete = True

    failed = await client_with_db.delete(f"/api/materials/{material_id}")

    assert failed.status_code == 503
    material = await db_session.get(Material, material_id)
    assert material is not None
    assert material.storage_status == "deleting"
    assert material.object_key in object_storage.objects
