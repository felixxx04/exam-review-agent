from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path

import boto3
import httpx
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_object_storage
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.middleware import RateLimitMiddleware
from app.db.database import bind_tenant_context, get_db
from app.db.models import (
    Course,
    Material,
    ProcessingStatus,
    StorageStatus,
    User,
)
from app.main import app
from app.services.parser_service import ParseResult
from app.services.object_storage import S3ObjectStorage


MINIO_ENDPOINT = os.getenv("MINIO_INTEGRATION_ENDPOINT_URL")
MINIO_BUCKET = os.getenv("MINIO_INTEGRATION_BUCKET")
MINIO_ACCESS_KEY = os.getenv("MINIO_INTEGRATION_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_INTEGRATION_SECRET_KEY")
POSTGRES_INTEGRATION_URL = os.getenv("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not all((MINIO_ENDPOINT, MINIO_BUCKET, MINIO_ACCESS_KEY, MINIO_SECRET_KEY)),
    reason="MinIO integration environment variables are required",
)


class _SecretUrl:
    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return "<redacted signed URL>"


async def _request_secret_url(url: _SecretUrl) -> httpx.Response:
    try:
        async with httpx.AsyncClient() as client:
            return await client.get(url.value)
    except httpx.HTTPError:
        pytest.fail("The MinIO request failed", pytrace=False)


def _assert_response_does_not_expose(
    response_data: Mapping[str, object], field: str
) -> None:
    if field in response_data:
        pytest.fail(f"response must not expose {field}", pytrace=False)


@pytest.mark.asyncio
async def test_minio_private_object_lifecycle_and_presigned_download(tmp_path):
    assert MINIO_ENDPOINT is not None
    assert MINIO_BUCKET is not None
    assert MINIO_ACCESS_KEY is not None
    assert MINIO_SECRET_KEY is not None
    source = tmp_path / "source.pdf"
    source.write_bytes(b"private storage integration test")
    key = (
        "users/900000001/courses/900000002/materials/900000003/objects/"
        f"{uuid.uuid4().hex}"
    )
    storage = S3ObjectStorage(
        bucket=MINIO_BUCKET,
        region="us-east-1",
        endpoint_url=MINIO_ENDPOINT,
        public_endpoint_url=MINIO_ENDPOINT,
        access_key_id=MINIO_ACCESS_KEY,
        secret_access_key=MINIO_SECRET_KEY,
    )
    await storage.check_bucket()

    stored = await storage.put_file(
        key=key,
        source=source,
        size_bytes=source.stat().st_size,
        content_type="application/pdf",
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    access = await storage.presign_get(
        key=stored.key,
        filename="notes.pdf",
        content_type="application/pdf",
        disposition="attachment",
        expires_in_seconds=300,
        version_id=stored.version_id,
    )
    downloaded = tmp_path / "downloaded.pdf"
    await storage.download_to_path(
        key=stored.key,
        destination=downloaded,
        version_id=stored.version_id,
    )

    unsigned = await _request_secret_url(
        _SecretUrl(f"{MINIO_ENDPOINT}/{MINIO_BUCKET}/{key}")
    )
    signed = await _request_secret_url(_SecretUrl(access.url))

    assert unsigned.status_code in {401, 403, 404}
    assert signed.status_code == 200
    assert signed.content == source.read_bytes()
    assert downloaded.read_bytes() == source.read_bytes()

    client = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )
    with pytest.raises(ClientError) as denied_listing:
        await asyncio.to_thread(client.list_objects_v2, Bucket=MINIO_BUCKET)
    assert denied_listing.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403

    exact_versions = await asyncio.to_thread(
        client.list_object_versions,
        Bucket=MINIO_BUCKET,
        Prefix=key,
    )
    assert any(
        version.get("Key") == key for version in exact_versions.get("Versions", [])
    )
    with pytest.raises(ClientError) as denied_unscoped_version_listing:
        await asyncio.to_thread(client.list_object_versions, Bucket=MINIO_BUCKET)
    assert (
        denied_unscoped_version_listing.value.response["ResponseMetadata"][
            "HTTPStatusCode"
        ]
        == 403
    )

    await asyncio.to_thread(
        client.put_object,
        Bucket=MINIO_BUCKET,
        Key=key,
        Body=b"historical retry version",
        ContentType="application/pdf",
        Metadata={"sha256": hashlib.sha256(b"historical retry version").hexdigest()},
    )

    await storage.delete_object(key=stored.key, version_id=stored.version_id)
    await storage.delete_object(key=stored.key, version_id=stored.version_id)

    remaining = await asyncio.to_thread(
        client.list_object_versions,
        Bucket=MINIO_BUCKET,
        Prefix=key,
    )
    assert not any(
        entry.get("Key") == key
        for group in ("Versions", "DeleteMarkers")
        for entry in remaining.get(group, [])
    )


@pytest.mark.skipif(
    not POSTGRES_INTEGRATION_URL,
    reason="POSTGRES_INTEGRATION_URL is required for the real material API flow",
)
@pytest.mark.asyncio
async def test_real_material_api_uses_postgres_and_private_minio(monkeypatch):
    assert POSTGRES_INTEGRATION_URL is not None
    assert MINIO_ENDPOINT is not None
    assert MINIO_BUCKET is not None
    assert MINIO_ACCESS_KEY is not None
    assert MINIO_SECRET_KEY is not None

    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

    class ParserStub:
        async def parse(self, file_path, file_type=None):
            assert Path(file_path).read_bytes() == content
            assert file_type == "pdf"
            return ParseResult(chunks=[], page_count=1)

    monkeypatch.setattr("app.services.parser_service.ParserService", ParserStub)
    storage = S3ObjectStorage(
        bucket=MINIO_BUCKET,
        region="us-east-1",
        endpoint_url=MINIO_ENDPOINT,
        public_endpoint_url=MINIO_ENDPOINT,
        access_key_id=MINIO_ACCESS_KEY,
        secret_access_key=MINIO_SECRET_KEY,
    )
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    assert engine.dialect.name == "postgresql"
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user_id: int | None = None
    object_key: str | None = None
    object_version_id: str | None = None

    try:
        async with session_factory() as setup_session:
            user = User(
                username=f"minio_api_{suffix}",
                email=None,
                hashed_password="integration-test-hash",
                display_name="MinIO API Integration",
            )
            setup_session.add(user)
            await setup_session.flush()
            user_id = user.id
            username = user.username
            role = user.role
            await setup_session.commit()

        async with session_factory() as session:
            await bind_tenant_context(session, user_id)
            course = Course(
                user_id=user_id,
                name=f"MinIO API course {suffix}",
                is_default=True,
            )
            session.add(course)
            await session.commit()
            await session.refresh(course)

            async def override_get_db():
                yield session

            app.dependency_overrides[get_db] = override_get_db
            app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
                id=user_id,
                username=username,
                role=role,
                session_id="minio-api-integration",
            )
            app.dependency_overrides[get_object_storage] = lambda: storage
            RateLimitMiddleware.reset()

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as api_client:
                uploaded = await api_client.post(
                    "/api/materials",
                    params={"course_id": course.id},
                    files={"file": ("integration.pdf", content, "application/pdf")},
                )
                assert uploaded.status_code == 200
                upload_data = uploaded.json()["data"]
                _assert_response_does_not_expose(upload_data, "object_key")

                material = await session.scalar(
                    select(Material).where(Material.id == upload_data["id"])
                )
                assert material is not None
                object_key = material.object_key
                object_version_id = material.object_version_id
                assert material.storage_status == StorageStatus.AVAILABLE
                assert material.processing_status == ProcessingStatus.READY

                access_response = await api_client.get(
                    f"/api/materials/{material.id}/access-url",
                    params={"disposition": "attachment"},
                )
                assert access_response.status_code == 200
                assert access_response.headers["cache-control"] == "private, no-store"
                assert access_response.headers["referrer-policy"] == "no-referrer"
                access_data = access_response.json()["data"]
                signed_url = _SecretUrl(access_data.pop("url"))
                _assert_response_does_not_expose(access_data, "object_key")
                assert access_data["expires_in_seconds"] == 300

                downloaded = await _request_secret_url(signed_url)
                assert downloaded.status_code == 200
                assert downloaded.content == content

                deleted = await api_client.delete(f"/api/materials/{material.id}")
                assert deleted.status_code == 200
                await session.refresh(material)
                assert material.storage_status == StorageStatus.DELETED

                stale_access = await _request_secret_url(signed_url)
                assert stale_access.status_code in {403, 404}
    finally:
        primary_error = sys.exception()
        cleanup_failures: list[str] = []
        cleanup_targets: list[tuple[str, str | None]] = []
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_object_storage, None)
        RateLimitMiddleware.reset()
        if user_id is not None:
            try:
                async with session_factory() as cleanup_session:
                    await bind_tenant_context(cleanup_session, user_id)
                    materials = list(
                        await cleanup_session.scalars(
                            select(Material).where(Material.user_id == user_id)
                        )
                    )
                    cleanup_targets.extend(
                        (material.object_key, material.object_version_id)
                        for material in materials
                        if material.object_key is not None
                    )
                    await cleanup_session.execute(
                        delete(User).where(User.id == user_id)
                    )
                    await cleanup_session.commit()
            except Exception:
                cleanup_failures.append("PostgreSQL cleanup")

        if object_key is not None and not any(
            key == object_key and version_id == object_version_id
            for key, version_id in cleanup_targets
        ):
            cleanup_targets.append((object_key, object_version_id))

        for cleanup_key, cleanup_version_id in cleanup_targets:
            try:
                await storage.delete_object(
                    key=cleanup_key,
                    version_id=cleanup_version_id,
                )
            except Exception:
                cleanup_failures.append("MinIO object cleanup")

        try:
            await engine.dispose()
        except Exception:
            cleanup_failures.append("database engine disposal")

        if cleanup_failures:
            cleanup_note = "Integration cleanup failed: " + ", ".join(cleanup_failures)
            if primary_error is not None:
                primary_error.add_note(cleanup_note)
            else:
                raise AssertionError(cleanup_note)
