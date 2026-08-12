from __future__ import annotations

import asyncio
import hmac
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.exceptions import AppException


_OBJECT_ID_PATTERN = re.compile(r"[a-zA-Z0-9-]{16,128}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_VALID_DISPOSITIONS = frozenset({"attachment", "inline"})
_READINESS_OBJECT_KEY = "__system__/object-storage-ready"


class ObjectStorageError(AppException):
    """A storage failure that is safe to return through the API envelope."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    etag: str | None
    version_id: str | None


@dataclass(frozen=True)
class PresignedGet:
    url: str
    expires_in_seconds: int


class ObjectStorage(Protocol):
    async def put_file(
        self,
        *,
        key: str,
        source: Path,
        size_bytes: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject: ...

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        version_id: str | None = None,
    ) -> None: ...

    async def delete_object(
        self,
        *,
        key: str,
        version_id: str | None = None,
    ) -> None: ...

    async def presign_get(
        self,
        *,
        key: str,
        filename: str,
        content_type: str,
        disposition: str,
        expires_in_seconds: int,
        version_id: str | None = None,
    ) -> PresignedGet: ...

    async def check_bucket(self) -> None: ...


def build_material_object_key(
    *, user_id: int, course_id: int, material_id: int, object_id: str
) -> str:
    """Return the fixed, server-owned S3 key for one material object."""
    if min(user_id, course_id, material_id) <= 0:
        raise ValueError("Material ownership identifiers must be positive")
    if not _OBJECT_ID_PATTERN.fullmatch(object_id):
        raise ValueError("Object ID must be an opaque server-generated identifier")
    return (
        f"users/{user_id}/courses/{course_id}/materials/{material_id}/"
        f"objects/{object_id}"
    )


class S3ObjectStorage:
    """Private S3-compatible storage backed by a blocking SDK in worker threads."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        public_endpoint_url: str | None = None,
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = 30,
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self._client = client or self._build_client(
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
        )
        self._presign_client = (
            self._client
            if client is not None or public_endpoint_url in (None, endpoint_url)
            else self._build_client(
                endpoint_url=public_endpoint_url,
                region=region,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                connect_timeout_seconds=connect_timeout_seconds,
                read_timeout_seconds=read_timeout_seconds,
            )
        )

    @staticmethod
    def _build_client(
        *,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        connect_timeout_seconds: int,
        read_timeout_seconds: int,
    ) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=connect_timeout_seconds,
                read_timeout=read_timeout_seconds,
                s3={"addressing_style": "path"},
            ),
        )

    async def put_file(
        self,
        *,
        key: str,
        source: Path,
        size_bytes: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        if size_bytes < 0 or not _SHA256_PATTERN.fullmatch(sha256):
            raise ObjectStorageError(
                "Object upload could not be verified", "OBJECT_VERIFICATION_FAILED"
            )
        try:
            source_size = source.stat().st_size
        except OSError as exc:
            raise self._storage_error(exc) from exc
        if source_size != size_bytes:
            raise ObjectStorageError(
                "Object upload could not be verified", "OBJECT_VERIFICATION_FAILED"
            )

        try:
            response = await asyncio.to_thread(
                self._put_and_verify,
                key,
                source,
                size_bytes,
                content_type,
                sha256,
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise self._storage_error(exc) from exc

        return StoredObject(
            key=key,
            size_bytes=size_bytes,
            etag=_clean_etag(response.get("ETag")),
            version_id=response.get("VersionId"),
        )

    def _put_and_verify(
        self,
        key: str,
        source: Path,
        size_bytes: int,
        content_type: str,
        sha256: str,
    ) -> dict[str, Any]:
        with source.open("rb") as handle:
            put_response = self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=handle,
                ContentLength=size_bytes,
                ContentType=content_type,
                Metadata={"sha256": sha256},
            )
        version_id = put_response.get("VersionId")
        try:
            head_response = self._client.head_object(Bucket=self.bucket, Key=key)
            metadata = head_response.get("Metadata") or {}
            stored_sha256 = metadata.get("sha256")
            if (
                head_response.get("ContentLength") != size_bytes
                or not isinstance(stored_sha256, str)
                or not hmac.compare_digest(stored_sha256.lower(), sha256)
            ):
                raise ObjectStorageError(
                    "Object upload could not be verified", "OBJECT_VERIFICATION_FAILED"
                )
        except Exception:
            # A verification failure cannot make an unverified version available.
            try:
                self._delete(key, version_id)
            except (BotoCoreError, ClientError):
                pass
            raise
        return {
            "ETag": head_response.get("ETag", put_response.get("ETag")),
            "VersionId": head_response.get("VersionId", version_id),
        }

    async def check_bucket(self) -> None:
        """Verify the application identity can reach the private bucket.

        ``HeadBucket`` requires ``s3:ListBucket`` on AWS-compatible providers.
        The application deliberately lacks that broad permission, so the MinIO
        bootstrap creates a fixed sentinel which can be checked with its
        already-required ``s3:GetObject`` permission.
        """
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self.bucket,
                Key=_READINESS_OBJECT_KEY,
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._storage_error(exc) from exc

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        error = exc.response.get("Error", {})
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return (
            error.get("Code") in {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}
            or status == 404
        )

    def _current_version(self, key: str) -> tuple[bool, str | None]:
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._is_not_found(exc):
                return False, None
            raise
        version_id = response.get("VersionId")
        return True, version_id if isinstance(version_id, str) else None

    def _delete(self, key: str, version_id: str | None) -> None:
        if version_id is None:
            exists, resolved_version_id = self._current_version(key)
            if not exists:
                return
        else:
            resolved_version_id = version_id
        if resolved_version_id is None:
            # The provider is unversioned; DeleteObject itself is idempotent.
            self._client.delete_object(Bucket=self.bucket, Key=key)
            return
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if resolved_version_id is not None:
            kwargs["VersionId"] = resolved_version_id
        try:
            self._client.delete_object(**kwargs)
        except ClientError as exc:
            if not self._is_not_found(exc):
                raise

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        version_id: str | None = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(self._download_file, key, destination, version_id)
        except (BotoCoreError, ClientError, OSError) as exc:
            destination.unlink(missing_ok=True)
            raise self._storage_error(exc) from exc

    def _download_file(
        self, key: str, destination: Path, version_id: str | None
    ) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Filename": str(destination),
        }
        if version_id is not None:
            kwargs["ExtraArgs"] = {"VersionId": version_id}
        self._client.download_file(**kwargs)

    async def delete_object(self, *, key: str, version_id: str | None = None) -> None:
        try:
            await asyncio.to_thread(self._delete, key, version_id)
        except (BotoCoreError, ClientError) as exc:
            raise self._storage_error(exc) from exc

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
        if disposition not in _VALID_DISPOSITIONS:
            raise ObjectStorageError("Invalid download disposition", "INVALID_DOWNLOAD")
        if not 1 <= expires_in_seconds <= 900:
            raise ObjectStorageError("Invalid download lifetime", "INVALID_DOWNLOAD")

        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "ResponseContentDisposition": _content_disposition(disposition, filename),
            "ResponseContentType": content_type,
        }
        if version_id is not None:
            params["VersionId"] = version_id
        try:
            url = await asyncio.to_thread(
                self._presign_client.generate_presigned_url,
                "get_object",
                Params=params,
                ExpiresIn=expires_in_seconds,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._storage_error(exc) from exc
        return PresignedGet(url=url, expires_in_seconds=expires_in_seconds)

    @staticmethod
    def _storage_error(_exc: Exception) -> ObjectStorageError:
        return ObjectStorageError(
            "Object storage is temporarily unavailable", "OBJECT_STORAGE_UNAVAILABLE"
        )


def _clean_etag(value: Any) -> str | None:
    return value.strip('"') if isinstance(value, str) else None


def _content_disposition(disposition: str, filename: str) -> str:
    safe_name = Path(filename.replace("\\", "/")).name
    safe_name = safe_name.replace('"', "'").replace("\r", "").replace("\n", "")
    return f'{disposition}; filename="{safe_name or "download"}"'
