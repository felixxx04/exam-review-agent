from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path

import pytest
from boto3.exceptions import RetriesExceededError
from botocore.exceptions import ClientError, EndpointConnectionError
from s3transfer.exceptions import S3DownloadFailedError

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
        self.versions: list[dict[str, str]] = []
        self.delete_markers: list[dict[str, str]] = []

    def put_object(self, **kwargs):
        self.calls.append(_RecordedCall("put_object", kwargs))
        self.metadata = kwargs["Metadata"]
        self.versions.append({"Key": kwargs["Key"], "VersionId": "version-1"})
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
        target = {
            "Key": kwargs["Key"],
            "VersionId": kwargs.get("VersionId", "null"),
        }
        self.versions = [entry for entry in self.versions if entry != target]
        self.delete_markers = [
            entry for entry in self.delete_markers if entry != target
        ]
        return {}

    def list_object_versions(self, **kwargs):
        self.calls.append(_RecordedCall("list_object_versions", kwargs))
        prefix = kwargs["Prefix"]
        return {
            "Versions": [
                entry.copy()
                for entry in self.versions
                if entry["Key"].startswith(prefix)
            ],
            "DeleteMarkers": [
                entry.copy()
                for entry in self.delete_markers
                if entry["Key"].startswith(prefix)
            ],
            "IsTruncated": False,
        }

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


def test_s3_client_disables_automatic_request_retries(monkeypatch) -> None:
    captured: dict = {}
    client = RecordingS3Client()

    def build_client(*_args, **kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr("app.services.object_storage.boto3.client", build_client)

    S3ObjectStorage(
        bucket="exam-review-materials",
        region="us-east-1",
        endpoint_url="http://minio.test:9000",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
    )

    assert captured["config"].retries == {
        "total_max_attempts": 1,
        "mode": "standard",
    }


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
    assert put.kwargs["IfNoneMatch"] == "*"


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
    client.versions.append({"Key": key, "VersionId": "version-1"})

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
async def test_s3_storage_deletes_all_exact_versions_and_markers_idempotently() -> None:
    key = "users/1/courses/2/materials/3/objects/random"
    sibling = f"{key}-sibling"
    client = RecordingS3Client()
    client.versions = [
        {"Key": key, "VersionId": "version-2"},
        {"Key": key, "VersionId": "version-1"},
        {"Key": sibling, "VersionId": "sibling-version"},
    ]
    client.delete_markers = [
        {"Key": key, "VersionId": "delete-marker-1"},
        {"Key": sibling, "VersionId": "sibling-marker"},
    ]

    storage = _storage(client)
    await storage.delete_object(key=key, version_id="version-1")
    await storage.delete_object(key=key, version_id="version-1")

    listed = [call for call in client.calls if call.name == "list_object_versions"]
    deleted = [call.kwargs for call in client.calls if call.name == "delete_object"]
    assert listed
    assert all(call.kwargs["Prefix"] == key for call in listed)
    assert {(call["Key"], call["VersionId"]) for call in deleted} == {
        (key, "version-2"),
        (key, "version-1"),
        (key, "delete-marker-1"),
    }
    assert client.versions == [{"Key": sibling, "VersionId": "sibling-version"}]
    assert client.delete_markers == [{"Key": sibling, "VersionId": "sibling-marker"}]


@pytest.mark.asyncio
async def test_s3_storage_paginates_exact_version_cleanup() -> None:
    key = "users/1/courses/2/materials/3/objects/random"
    sibling = f"{key}-sibling"
    client = RecordingS3Client()
    pages = [
        {
            "Versions": [
                {"Key": key, "VersionId": "version-2"},
                {"Key": sibling, "VersionId": "sibling-version"},
            ],
            "DeleteMarkers": [],
            "IsTruncated": True,
            "NextKeyMarker": key,
            "NextVersionIdMarker": "version-2",
        },
        {
            "Versions": [{"Key": key, "VersionId": "version-1"}],
            "DeleteMarkers": [{"Key": key, "VersionId": "delete-marker-1"}],
            "IsTruncated": False,
        },
        {"Versions": [], "DeleteMarkers": [], "IsTruncated": False},
    ]

    def paginated_versions(**kwargs):
        client.calls.append(_RecordedCall("list_object_versions", kwargs))
        return pages.pop(0)

    client.list_object_versions = paginated_versions  # type: ignore[method-assign]

    await _storage(client).delete_object(key=key, version_id="version-2")

    listed = [
        call.kwargs for call in client.calls if call.name == "list_object_versions"
    ]
    deleted = [call.kwargs for call in client.calls if call.name == "delete_object"]
    assert listed[0] == {"Bucket": "exam-review-materials", "Prefix": key}
    assert listed[1] == {
        "Bucket": "exam-review-materials",
        "Prefix": key,
        "KeyMarker": key,
        "VersionIdMarker": "version-2",
    }
    assert {(call["Key"], call["VersionId"]) for call in deleted} == {
        (key, "version-2"),
        (key, "version-1"),
        (key, "delete-marker-1"),
    }
    assert all(call["Key"] != sibling for call in deleted)


@pytest.mark.asyncio
async def test_s3_storage_rejects_a_stalled_version_pagination_token() -> None:
    key = "users/1/courses/2/materials/3/objects/random"
    client = RecordingS3Client()

    def stalled_versions(**kwargs):
        client.calls.append(_RecordedCall("list_object_versions", kwargs))
        if len(client.calls) > 3:
            raise AssertionError("version pagination did not stop")
        return {
            "Versions": [],
            "DeleteMarkers": [],
            "IsTruncated": True,
            "NextKeyMarker": key,
            "NextVersionIdMarker": "version-1",
        }

    client.list_object_versions = stalled_versions  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).delete_object(key=key)

    assert error.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    listed = [call for call in client.calls if call.name == "list_object_versions"]
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_s3_storage_does_not_head_an_unknown_put_before_cleanup() -> None:
    client = RecordingS3Client()

    def denied_head(**_kwargs):
        raise _client_error("AccessDenied", 403, "HeadObject")

    client.head_object = denied_head  # type: ignore[method-assign]

    await _storage(client).delete_object(
        key="users/1/courses/2/materials/3/objects/missing"
    )

    assert not any(call.name == "head_object" for call in client.calls)
    assert not any(call.name == "delete_object" for call in client.calls)


@pytest.mark.asyncio
async def test_s3_storage_ignores_a_missing_explicit_object_version() -> None:
    client = RecordingS3Client()
    key = "users/1/courses/2/materials/3/objects/missing"
    client.versions = [{"Key": key, "VersionId": "missing-version"}]

    def missing_delete(**_kwargs):
        client.versions.clear()
        raise _client_error("NoSuchVersion", 404, "DeleteObject")

    client.delete_object = missing_delete  # type: ignore[method-assign]

    await _storage(client).delete_object(
        key=key,
        version_id="missing-version",
    )


@pytest.mark.asyncio
async def test_s3_storage_does_not_treat_a_missing_bucket_as_a_missing_object() -> None:
    client = RecordingS3Client()
    key = "users/1/courses/2/materials/3/objects/random"
    client.versions = [{"Key": key, "VersionId": "version-1"}]

    def missing_bucket(**_kwargs):
        raise _client_error("NoSuchBucket", 404, "DeleteObject")

    client.delete_object = missing_bucket  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).delete_object(key=key, version_id="version-1")

    assert error.value.code == "OBJECT_STORAGE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_s3_storage_drops_sensitive_sdk_exception_context(tmp_path) -> None:
    client = RecordingS3Client()
    source = tmp_path / "upload.pdf"
    source.write_bytes(b"hello world")
    key = "users/1/courses/2/materials/3/objects/secret-object-key"
    leaked_url = (
        f"http://minio.test:9000/exam-review-materials/{key}"
        "?X-Amz-Signature=secret-signature"
    )

    def failed_put(**_kwargs):
        raise EndpointConnectionError(endpoint_url=leaked_url)

    client.put_object = failed_put  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).put_file(
            key=key,
            source=source,
            size_bytes=11,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    rendered = "".join(traceback.format_exception(error.value))
    assert error.value.__cause__ is None
    assert key not in rendered
    assert "minio.test:9000" not in rendered
    assert "X-Amz-Signature" not in rendered


@pytest.mark.asyncio
async def test_s3_storage_drops_verification_context_when_cleanup_does_not_converge(
    tmp_path,
) -> None:
    client = RecordingS3Client()
    source = tmp_path / "upload.pdf"
    source.write_bytes(b"hello world")
    key = "users/1/courses/2/materials/3/objects/secret-object-key"
    leaked_url = (
        f"http://minio.test:9000/exam-review-materials/{key}"
        "?X-Amz-Signature=secret-signature"
    )

    def failed_head(**_kwargs):
        raise EndpointConnectionError(endpoint_url=leaked_url)

    def ineffective_delete(**kwargs):
        client.calls.append(_RecordedCall("delete_object", kwargs))
        return {}

    client.head_object = failed_head  # type: ignore[method-assign]
    client.delete_object = ineffective_delete  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).put_file(
            key=key,
            source=source,
            size_bytes=11,
            content_type="application/pdf",
            sha256="a" * 64,
        )

    rendered = "".join(traceback.format_exception(error.value))
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True
    assert key not in rendered
    assert "minio.test:9000" not in rendered
    assert "X-Amz-Signature" not in rendered


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
async def test_s3_storage_hides_download_context_when_partial_cleanup_fails(
    tmp_path, monkeypatch, caplog
) -> None:
    client = RecordingS3Client()
    destination = tmp_path / "locked-download.pdf"
    key = "users/1/courses/2/materials/3/objects/secret-object-key"
    leaked_url = (
        f"http://minio.test:9000/exam-review-materials/{key}"
        "?X-Amz-Signature=secret-signature"
    )

    def failed_download(**_kwargs):
        raise EndpointConnectionError(endpoint_url=leaked_url)

    def locked_unlink(_path, *_args, **_kwargs):
        raise PermissionError("locked temporary path must not escape")

    client.download_file = failed_download  # type: ignore[method-assign]
    monkeypatch.setattr(Path, "unlink", locked_unlink)

    with caplog.at_level("WARNING", logger="app.services.object_storage"):
        with pytest.raises(ObjectStorageError) as error:
            await _storage(client).download_to_path(
                key=key,
                destination=destination,
            )

    rendered = "".join(traceback.format_exception(error.value))
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True
    assert key not in rendered
    assert "minio.test:9000" not in rendered
    assert "X-Amz-Signature" not in rendered
    assert "locked temporary path" not in rendered
    assert "Partial object download cleanup failed" in caplog.text
    assert key not in caplog.text
    assert str(destination) not in caplog.text


@pytest.mark.parametrize(
    "failure_kind",
    ["download_failed", "retries_exceeded"],
)
@pytest.mark.asyncio
async def test_s3_storage_maps_high_level_download_failures(
    tmp_path, failure_kind
) -> None:
    client = RecordingS3Client()
    destination = tmp_path / "partial-download.pdf"
    key = "users/1/courses/2/materials/3/objects/secret-object-key"
    leaked_url = (
        f"http://minio.test:9000/exam-review-materials/{key}"
        "?X-Amz-Signature=secret-signature"
    )
    failure = (
        S3DownloadFailedError(f"failed bucket=exam-review-materials key={key}")
        if failure_kind == "download_failed"
        else RetriesExceededError(EndpointConnectionError(endpoint_url=leaked_url))
    )

    def failed_download(**kwargs):
        Path(kwargs["Filename"]).write_bytes(b"partial")
        raise failure

    client.download_file = failed_download  # type: ignore[method-assign]

    with pytest.raises(ObjectStorageError) as error:
        await _storage(client).download_to_path(
            key=key,
            destination=destination,
        )

    rendered = "".join(traceback.format_exception(error.value))
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True
    assert key not in rendered
    assert "exam-review-materials" not in rendered
    assert "minio.test:9000" not in rendered
    assert "X-Amz-Signature" not in rendered
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
