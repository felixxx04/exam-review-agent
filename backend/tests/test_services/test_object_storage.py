from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

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
        self.metadata: dict[str, str] = {}

    def put_object(self, **kwargs):
        self.calls.append(_RecordedCall("put_object", kwargs))
        self.metadata = kwargs["Metadata"]
        return {"ETag": '"etag-123"', "VersionId": "version-1"}

    def head_object(self, **kwargs):
        self.calls.append(_RecordedCall("head_object", kwargs))
        return {
            "ContentLength": 11,
            "ETag": '"etag-123"',
            "VersionId": "version-1",
            "Metadata": self.metadata,
        }

    def head_bucket(self, **kwargs):
        self.calls.append(_RecordedCall("head_bucket", kwargs))

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


def _client_error(code: str, status_code: int, operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        operation,
    )


def test_material_object_key_is_server_generated_and_scoped() -> None:
    key = build_material_object_key(
        user_id=42,
        course_id=7,
        material_id=99,
        object_id="b7e4e7a36cb9493e91c04ac94d977333",
    )

    assert key == (
        "users/42/courses/7/materials/99/objects/b7e4e7a36cb9493e91c04ac94d977333"
    )
    assert "lecture-final.pdf" not in key


def test_material_object_key_rejects_non_server_owned_components() -> None:
    with pytest.raises(ValueError):
        build_material_object_key(
            user_id=0,
            course_id=7,
            material_id=99,
            object_id="b7e4e7a36cb9493e91c04ac94d977333",
        )
    with pytest.raises(ValueError):
        build_material_object_key(
            user_id=42,
            course_id=7,
            material_id=99,
            object_id="../../course-notes.pdf",
        )


@pytest.mark.asyncio
async def test_s3_storage_uploads_verified_object_with_private_metadata(
    tmp_path,
) -> None:
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
async def test_s3_storage_rejects_a_same_size_object_with_a_mismatched_hash(
    tmp_path,
) -> None:
    source = tmp_path / "upload.bin"
    source.write_bytes(b"hello world")
    client = RecordingS3Client()
    storage = _storage(client)
    client.metadata = {"sha256": "b" * 64}

    original_put = client.put_object

    def put_without_matching_metadata(**kwargs):
        original_put(**kwargs)
        client.metadata = {"sha256": "b" * 64}
        return {"ETag": '"etag-123"', "VersionId": "version-1"}

    client.put_object = put_without_matching_metadata  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await storage.put_file(
            key="users/1/courses/2/materials/3/objects/random",
            source=source,
            size_bytes=11,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    assert error.value.code == "OBJECT_VERIFICATION_FAILED"
    delete = next(call for call in client.calls if call.name == "delete_object")
    assert delete.kwargs["VersionId"] == "version-1"


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
async def test_s3_storage_delete_and_download_use_the_single_server_key(
    tmp_path,
) -> None:
    client = RecordingS3Client()
    storage = _storage(client)
    destination = tmp_path / "temporary-download.pdf"
    key = "users/1/courses/2/materials/3/objects/random"

    await storage.download_to_path(
        key=key, destination=destination, version_id="version-1"
    )
    await storage.delete_object(key=key, version_id="version-1")

    assert destination.read_bytes() == b"stored bytes"
    download = next(call for call in client.calls if call.name == "download_file")
    delete = next(call for call in client.calls if call.name == "delete_object")
    assert download.kwargs["Key"] == key
    assert download.kwargs["ExtraArgs"] == {"VersionId": "version-1"}
    assert delete.kwargs["Key"] == key
    assert delete.kwargs["VersionId"] == "version-1"


@pytest.mark.asyncio
async def test_s3_storage_checks_a_private_readiness_sentinel_with_its_service_identity() -> (
    None
):
    client = RecordingS3Client()

    await _storage(client).check_bucket()

    check = next(call for call in client.calls if call.name == "head_object")
    assert check.kwargs == {
        "Bucket": "exam-review-materials",
        "Key": "__system__/object-storage-ready",
    }


@pytest.mark.asyncio
async def test_s3_storage_rejects_invalid_source_metadata_before_upload(
    tmp_path,
) -> None:
    source = tmp_path / "upload.bin"
    source.write_bytes(b"hello world")
    client = RecordingS3Client()

    with pytest.raises(ObjectStorageError) as invalid_hash:
        await _storage(client).put_file(
            key="users/1/courses/2/materials/3/objects/random",
            source=source,
            size_bytes=11,
            content_type="application/pdf",
            sha256="not-a-sha256",
        )
    with pytest.raises(ObjectStorageError) as invalid_size:
        await _storage(client).put_file(
            key="users/1/courses/2/materials/3/objects/random",
            source=source,
            size_bytes=10,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    assert invalid_hash.value.code == "OBJECT_VERIFICATION_FAILED"
    assert invalid_size.value.code == "OBJECT_VERIFICATION_FAILED"
    assert not any(call.name == "put_object" for call in client.calls)


@pytest.mark.asyncio
async def test_s3_storage_hides_missing_source_and_sdk_upload_failures(
    tmp_path,
) -> None:
    client = RecordingS3Client()
    missing_source = tmp_path / "missing.pdf"

    with pytest.raises(ObjectStorageError) as missing:
        await _storage(client).put_file(
            key="users/1/courses/2/materials/3/objects/random",
            source=missing_source,
            size_bytes=0,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    source = tmp_path / "upload.pdf"
    source.write_bytes(b"hello world")

    def failed_put(**_kwargs):
        raise _client_error("AccessDenied", 403, "PutObject")

    client.put_object = failed_put  # type: ignore[method-assign]
    with pytest.raises(ObjectStorageError) as denied:
        await _storage(client).put_file(
            key="users/1/courses/2/materials/3/objects/random",
            source=source,
            size_bytes=11,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    assert missing.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert denied.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert "AccessDenied" not in denied.value.message


@pytest.mark.asyncio
async def test_s3_storage_deletes_the_current_or_unversioned_object_idempotently() -> (
    None
):
    key = "users/1/courses/2/materials/3/objects/random"
    versioned_client = RecordingS3Client()

    await _storage(versioned_client).delete_object(key=key)

    versioned_delete = next(
        call for call in versioned_client.calls if call.name == "delete_object"
    )
    assert versioned_delete.kwargs["VersionId"] == "version-1"

    unversioned_client = RecordingS3Client()
    unversioned_client.head_object = lambda **_kwargs: {"VersionId": None}  # type: ignore[method-assign]
    await _storage(unversioned_client).delete_object(key=key)

    unversioned_delete = next(
        call for call in unversioned_client.calls if call.name == "delete_object"
    )
    assert unversioned_delete.kwargs == {"Bucket": "exam-review-materials", "Key": key}


@pytest.mark.asyncio
async def test_s3_storage_ignores_not_found_during_idempotent_delete() -> None:
    client = RecordingS3Client()

    def missing_head(**_kwargs):
        raise _client_error("NoSuchKey", 404, "HeadObject")

    client.head_object = missing_head  # type: ignore[method-assign]

    await _storage(client).delete_object(
        key="users/1/courses/2/materials/3/objects/missing"
    )

    assert not any(call.name == "delete_object" for call in client.calls)


@pytest.mark.asyncio
async def test_s3_storage_ignores_a_missing_explicit_object_version() -> None:
    client = RecordingS3Client()

    def missing_delete(**_kwargs):
        raise _client_error("NoSuchVersion", 404, "DeleteObject")

    client.delete_object = missing_delete  # type: ignore[method-assign]

    await _storage(client).delete_object(
        key="users/1/courses/2/materials/3/objects/missing",
        version_id="missing-version",
    )


@pytest.mark.asyncio
async def test_s3_storage_removes_partial_downloads_and_hides_sdk_errors(
    tmp_path,
) -> None:
    client = RecordingS3Client()
    destination = tmp_path / "private-download.pdf"

    def failed_download(**_kwargs):
        destination.write_bytes(b"partial")
        raise OSError("network path details must not escape")

    client.download_file = failed_download  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).download_to_path(
            key="users/1/courses/2/materials/3/objects/random",
            destination=destination,
        )

    assert error.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert "network path" not in error.value.message
    assert not destination.exists()


@pytest.mark.asyncio
async def test_s3_storage_rejects_invalid_presign_parameters_and_maps_sdk_failures() -> (
    None
):
    client = RecordingS3Client()
    storage = _storage(client)
    common = {
        "key": "users/1/courses/2/materials/3/objects/random",
        "filename": "notes.pdf",
        "content_type": "application/pdf",
    }

    with pytest.raises(ObjectStorageError) as invalid_disposition:
        await storage.presign_get(
            **common,
            disposition="redirect",
            expires_in_seconds=300,
        )
    with pytest.raises(ObjectStorageError) as invalid_lifetime:
        await storage.presign_get(
            **common,
            disposition="attachment",
            expires_in_seconds=901,
        )

    def denied_presign(*_args, **_kwargs):
        raise _client_error("AccessDenied", 403, "GetObject")

    client.generate_presigned_url = denied_presign  # type: ignore[method-assign]
    with pytest.raises(ObjectStorageError) as denied:
        await storage.presign_get(
            **common,
            disposition="attachment",
            expires_in_seconds=300,
        )

    assert invalid_disposition.value.code == "INVALID_DOWNLOAD"
    assert invalid_lifetime.value.code == "INVALID_DOWNLOAD"
    assert denied.value.code == "OBJECT_STORAGE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_s3_storage_hides_bucket_readiness_failure() -> None:
    client = RecordingS3Client()

    def denied_readiness_object(**_kwargs):
        raise _client_error("AccessDenied", 403, "HeadObject")

    client.head_object = denied_readiness_object  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).check_bucket()

    assert error.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert "AccessDenied" not in error.value.message
