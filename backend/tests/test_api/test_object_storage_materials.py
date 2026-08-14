from __future__ import annotations

import asyncio
import datetime
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api import materials as materials_api
from app.api.dependencies import get_object_storage
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.models import Course, Material, StorageStatus, User
from app.main import app
from app.services.object_storage import (
    ObjectStorageError,
    PresignedGet,
    StoredObject,
)
from app.services.material_storage_cleanup import recover_stale_material_reservations


MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _data(response):
    payload = response.json()
    assert payload["success"] is True
    return payload["data"]


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_attempts: list[str] = []
        self.deleted: list[str] = []
        self.delete_attempts: list[str] = []
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
        self.put_attempts.append(key)
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
        self.delete_attempts.append(key)
        if self.fail_delete:
            raise ObjectStorageError(
                "Object storage is temporarily unavailable",
                "OBJECT_STORAGE_UNAVAILABLE",
            )
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
    monkeypatch.setattr(
        "app.services.parser_service.ParserService", lambda: ParserStub()
    )
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
    assert data["original_filename"] == "course-notes.pdf"
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
async def test_storage_quota_rejection_before_object_write_discards_reservation_without_storage_calls(
    client_with_db, db_session, authenticated_user, object_storage
):
    authenticated_user.storage_limit_bytes = len(MINIMAL_PDF) - 1
    await db_session.commit()
    object_storage.fail_delete = True

    response = await client_with_db.post(
        "/api/materials",
        files={"file": ("quota.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert (await db_session.execute(select(Material))).scalars().all() == []
    assert object_storage.objects == {}
    assert object_storage.put_attempts == []
    assert object_storage.delete_attempts == []


@pytest.mark.asyncio
async def test_unknown_object_write_keeps_a_deleting_tombstone_until_recovery(
    client_with_db, db_session, object_storage, monkeypatch
):
    release_late_write = asyncio.Event()
    late_write_finished = asyncio.Event()

    async def write_after_timeout(*, key, source, **_kwargs):
        content = source.read_bytes()

        async def finish_late_write() -> None:
            await release_late_write.wait()
            object_storage.objects[key] = content
            late_write_finished.set()

        asyncio.create_task(finish_late_write())
        raise ObjectStorageError(
            "Object storage is temporarily unavailable", "OBJECT_STORAGE_UNAVAILABLE"
        )

    monkeypatch.setattr(object_storage, "put_file", write_after_timeout)

    failed = await client_with_db.post(
        "/api/materials",
        files={"file": ("late-write.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert failed.status_code == 503
    material = await db_session.scalar(select(Material))
    assert material is not None
    assert material.storage_status == StorageStatus.DELETING
    assert material.object_key is not None
    assert object_storage.delete_attempts == []

    object_key = material.object_key
    with pytest.raises(ObjectStorageError) as blocked_delete:
        await materials_api.delete_material(
            material.id,
            current_user=AuthenticatedUser(
                id=material.user_id,
                username="test_user",
                role="user",
                session_id="test-session",
            ),
            db=db_session,
            storage=object_storage,
        )
    assert blocked_delete.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert object_storage.delete_attempts == []

    release_late_write.set()
    await asyncio.wait_for(late_write_finished.wait(), timeout=1)
    material.created_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        hours=2
    )
    await db_session.commit()

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    assert report.tombstones_written == 1
    assert material.storage_status == StorageStatus.DELETED
    assert object_key not in object_storage.objects


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
async def test_identical_content_is_isolated_across_courses_and_users(
    client_with_db, db_session, authenticated_user, object_storage
):
    first = await client_with_db.post(
        "/api/materials",
        files={"file": ("first.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert first.status_code == 200

    other_course = Course(
        user_id=authenticated_user.id,
        name="Other private course",
        is_default=False,
    )
    other_user = User(
        username="duplicate_scope_other",
        email=None,
        hashed_password="test-password-hash",
        display_name="Other User",
        role="user",
    )
    db_session.add_all([other_course, other_user])
    await db_session.commit()
    await db_session.refresh(other_course)
    await db_session.refresh(other_user)
    other_user_course = Course(
        user_id=other_user.id,
        name="Other user's private course",
        is_default=True,
    )
    db_session.add(other_user_course)
    await db_session.commit()
    await db_session.refresh(other_user_course)

    same_user_other_course = await client_with_db.post(
        "/api/materials",
        params={"course_id": other_course.id},
        files={"file": ("course-copy.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert same_user_other_course.status_code == 200

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=other_user.id,
        username=other_user.username,
        role=other_user.role,
        session_id="other-session",
    )
    other_user_upload = await client_with_db.post(
        "/api/materials",
        params={"course_id": other_user_course.id},
        files={"file": ("user-copy.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert other_user_upload.status_code == 200
    materials = (await db_session.execute(select(Material))).scalars().all()
    assert len(materials) == 3
    assert len({material.object_key for material in materials}) == 3
    assert len(object_storage.objects) == 3


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
    assert owner.headers["cache-control"] == "private, no-store"
    assert owner.headers["referrer-policy"] == "no-referrer"

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
@pytest.mark.parametrize(
    "storage_status",
    [StorageStatus.RESERVED, StorageStatus.DELETING, StorageStatus.DELETED],
)
async def test_non_available_material_cannot_get_a_download_url(
    client_with_db, db_session, object_storage, storage_status
):
    uploaded = await client_with_db.post(
        "/api/materials",
        files={"file": ("notes.pdf", MINIMAL_PDF, "application/pdf")},
    )
    material_id = _data(uploaded)["id"]
    material = await db_session.get(Material, material_id)
    assert material is not None
    material.storage_status = storage_status
    await db_session.commit()

    denied = await client_with_db.get(f"/api/materials/{material_id}/access-url")

    assert denied.status_code == 404
    assert object_storage.presigned == []


@pytest.mark.asyncio
async def test_material_delete_removes_private_object_before_recording_a_tombstone(
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
    material = await db_session.get(Material, material_id)
    assert material is not None
    assert material.storage_status == StorageStatus.DELETED

    repeated = await client_with_db.delete(f"/api/materials/{material_id}")
    assert repeated.status_code == 200
    assert object_storage.deleted.count(object_key) == 1


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

    object_storage.fail_delete = False
    retried = await client_with_db.delete(f"/api/materials/{material_id}")

    assert retried.status_code == 200
    await db_session.refresh(material)
    assert material.storage_status == StorageStatus.DELETED
