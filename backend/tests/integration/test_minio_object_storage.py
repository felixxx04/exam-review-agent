from __future__ import annotations

import os
import uuid
import hashlib

import httpx
import pytest

from app.services.object_storage import S3ObjectStorage


MINIO_ENDPOINT = os.getenv("MINIO_INTEGRATION_ENDPOINT_URL")
MINIO_BUCKET = os.getenv("MINIO_INTEGRATION_BUCKET")
MINIO_ACCESS_KEY = os.getenv("MINIO_INTEGRATION_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_INTEGRATION_SECRET_KEY")
pytestmark = pytest.mark.skipif(
    not all((MINIO_ENDPOINT, MINIO_BUCKET, MINIO_ACCESS_KEY, MINIO_SECRET_KEY)),
    reason="MinIO integration environment variables are required",
)


@pytest.mark.asyncio
async def test_minio_private_object_lifecycle_and_presigned_download(tmp_path):
    assert MINIO_ENDPOINT is not None
    assert MINIO_BUCKET is not None
    assert MINIO_ACCESS_KEY is not None
    assert MINIO_SECRET_KEY is not None
    source = tmp_path / "source.pdf"
    source.write_bytes(b"private storage integration test")
    key = f"tests/{uuid.uuid4().hex}/object"
    storage = S3ObjectStorage(
        bucket=MINIO_BUCKET,
        region="us-east-1",
        endpoint_url=MINIO_ENDPOINT,
        public_endpoint_url=MINIO_ENDPOINT,
        access_key_id=MINIO_ACCESS_KEY,
        secret_access_key=MINIO_SECRET_KEY,
    )

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

    async with httpx.AsyncClient() as client:
        unsigned = await client.get(f"{MINIO_ENDPOINT}/{MINIO_BUCKET}/{key}")
        signed = await client.get(access.url)

    assert unsigned.status_code in {401, 403, 404}
    assert signed.status_code == 200
    assert signed.content == source.read_bytes()
    assert downloaded.read_bytes() == source.read_bytes()

    await storage.delete_object(key=stored.key, version_id=stored.version_id)
    await storage.delete_object(key=stored.key, version_id=stored.version_id)
