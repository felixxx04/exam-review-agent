from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.object_storage import (
    ObjectStorageError,
    S3ObjectStorage,
    build_material_object_key,
)


@dataclass
class _RecordedCall:
    name: str
    kwargs: dict


class RecordingS3Client:
    def __init__(self) -> None:
        self.calls: list[_RecordedCall] = []

    def put_object(self, **kwargs):
        self.calls.append(_RecordedCall("put_object", kwargs))
        return {"ETag": '"etag-123"', "VersionId": "version-1"}

    def head_object(self, **kwargs):
        self.calls.append(_RecordedCall("head_object", kwargs))
        return {"ContentLength": 11, "ETag": '"etag-123"', "VersionId": "version-1"}

    def delete_object(self, **kwargs):
        self.calls.append(_RecordedCall("delete_object", kwargs))
        return {}

    def download_file(self, **kwargs):
        self.calls.append(_RecordedCall("download_file", kwargs))
        Path(kwargs["Filename"]).write_bytes(b"stored bytes")

    def generate_presigned_url(self, *args, **kwargs):
        self.calls.append(
            _RecordedCall(
                "generate_presigned_url",
                {"operation": args[0], **kwargs},
            )
        )
        return "https://storage.example.test/private-object?X-Amz-Signature=redacted"


def _storage(client: RecordingS3Client) -> S3ObjectStorage:
    return S3ObjectStorage(
        bucket="exam-review-materials",
        region="us-east-1",
        endpoint_url="http://minio.test:9000",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
        client=client,
    )


def test_material_object_key_is_server_generated_and_scoped() -> None:
    key = build_material_object_key(
        user_id=42,
        course_id=7,
        material_id=99,
        object_id="b7e4e7a36cb9493e91c04ac94d977333",
    )

    assert key == (
        "users/42/courses/7/materials/99/objects/"
        "b7e4e7a36cb9493e91c04ac94d977333"
    )
    assert "lecture-final.pdf" not in key


@pytest.mark.asyncio
async def test_s3_storage_uploads_verified_object_with_private_metadata(tmp_path) -> None:
    source = tmp_path / "upload.bin"
    source.write_bytes(b"hello world")
    client = RecordingS3Client()

    stored = await _storage(client).put_file(
        key="users/1/courses/2/materials/3/objects/random",
        source=source,
        size_bytes=11,
        content_type="application/pdf",
        sha256="a" * 64,
    )

    assert stored.size_bytes == 11
    assert stored.etag == "etag-123"
    assert stored.version_id == "version-1"
    put = next(call for call in client.calls if call.name == "put_object")
    assert put.kwargs["Bucket"] == "exam-review-materials"
    assert put.kwargs["Key"] == "users/1/courses/2/materials/3/objects/random"
    assert put.kwargs["Metadata"] == {"sha256": "a" * 64}
    assert put.kwargs["ContentType"] == "application/pdf"


@pytest.mark.asyncio
async def test_s3_storage_rejects_a_size_mismatch_without_exposing_storage_details(
    tmp_path,
) -> None:
    source = tmp_path / "upload.bin"
    source.write_bytes(b"hello world")
    client = RecordingS3Client()
    storage = _storage(client)
    client.head_object = lambda **kwargs: {"ContentLength": 10}  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await storage.put_file(
            key="users/1/courses/2/materials/3/objects/random",
            source=source,
            size_bytes=11,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    assert error.value.code == "OBJECT_VERIFICATION_FAILED"
    assert "random" not in error.value.message
    assert "test-secret-key" not in error.value.message


@pytest.mark.asyncio
async def test_s3_storage_creates_a_short_get_only_presigned_url() -> None:
    client = RecordingS3Client()

    access = await _storage(client).presign_get(
        key="users/1/courses/2/materials/3/objects/random",
        filename="course notes.pdf",
        content_type="application/pdf",
        disposition="attachment",
        expires_in_seconds=300,
    )

    assert access.expires_in_seconds == 300
    assert access.url.startswith("https://storage.example.test/")
    call = next(call for call in client.calls if call.name == "generate_presigned_url")
    assert call.kwargs["operation"] == "get_object"
    assert call.kwargs["HttpMethod"] == "GET"
    assert call.kwargs["ExpiresIn"] == 300
    assert call.kwargs["Params"]["Bucket"] == "exam-review-materials"
    assert call.kwargs["Params"]["Key"].endswith("/random")
    assert "attachment" in call.kwargs["Params"]["ResponseContentDisposition"]


@pytest.mark.asyncio
async def test_s3_storage_delete_and_download_use_the_single_server_key(tmp_path) -> None:
    client = RecordingS3Client()
    storage = _storage(client)
    destination = tmp_path / "temporary-download.pdf"
    key = "users/1/courses/2/materials/3/objects/random"

    await storage.download_to_path(key=key, destination=destination, version_id="version-1")
    await storage.delete_object(key=key, version_id="version-1")

    assert destination.read_bytes() == b"stored bytes"
    download = next(call for call in client.calls if call.name == "download_file")
    delete = next(call for call in client.calls if call.name == "delete_object")
    assert download.kwargs["Key"] == key
    assert download.kwargs["ExtraArgs"] == {"VersionId": "version-1"}
    assert delete.kwargs["Key"] == key
    assert delete.kwargs["VersionId"] == "version-1"
