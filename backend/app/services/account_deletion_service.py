from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.database import bind_tenant_context
from app.db.models import (
    AccountDeletionJob,
    Course,
    InviteCode,
    Material,
    MaterialJob,
    MaterialJobStatus,
    ProcessingStatus,
    RefreshToken,
    StorageStatus,
    User,
)
from app.services.object_storage import ObjectStorage, ObjectStorageError
from app.services.material_storage_cleanup import is_processing_lease_active


ARTIFACT_FAILURE_MESSAGE = "Account artifacts could not be removed"
DATABASE_FAILURE_MESSAGE = "Account data could not be removed"
logger = logging.getLogger(__name__)


class CollectionStore(Protocol):
    def delete_collection(self, scope: str) -> None: ...


@dataclass(frozen=True)
class MaterialArtifact:
    filename: str = ""
    storage_path: str | None = None
    object_key: str | None = None
    object_version_id: str | None = None
    storage_status: str = StorageStatus.AVAILABLE
    processing_status: str = ProcessingStatus.READY
    processing_lease_expires_at: datetime.datetime | None = None
    object_write_uncertain: bool = False


@dataclass(frozen=True)
class AccountDeletionRequestResult:
    job: AccountDeletionJob
    status_token: str


class AccountArtifactCleaner:
    def __init__(
        self,
        object_storage_or_legacy_upload_root: ObjectStorage | str | Path,
        vector_store: CollectionStore,
        *,
        legacy_upload_root: str | Path | None = None,
    ) -> None:
        self.object_storage: ObjectStorage | None = None
        self.upload_root: Path | None = None
        if isinstance(object_storage_or_legacy_upload_root, (str, Path)):
            self.upload_root = Path(object_storage_or_legacy_upload_root).resolve()
        else:
            self.object_storage = object_storage_or_legacy_upload_root
            if legacy_upload_root is not None:
                self.upload_root = Path(legacy_upload_root).resolve()
        self.vector_store = vector_store

    async def clean(
        self,
        user_id: int,
        course_ids: list[int],
        materials: list[MaterialArtifact],
    ) -> None:
        for material in materials:
            if (
                material.object_write_uncertain
                or material.storage_status == StorageStatus.RESERVED
                or (
                    material.processing_status == ProcessingStatus.PROCESSING
                    and is_processing_lease_active(material.processing_lease_expires_at)
                )
            ):
                # Deleting the user now would cascade away the only durable
                # record for an ambiguous PUT or live index. The job stays
                # retryable after recovery finishes the material lifecycle.
                raise ObjectStorageError(
                    "Material cleanup is pending", "OBJECT_STORAGE_UNAVAILABLE"
                )
            if material.object_key is not None:
                if self.object_storage is None:
                    raise ValueError("Object storage is required for stored materials")
                await self.object_storage.delete_object(
                    key=material.object_key,
                    version_id=material.object_version_id,
                )
            else:
                await asyncio.to_thread(self._delete_legacy_material, material)
        await asyncio.to_thread(self._clean_vectors, user_id, course_ids)

    def _clean_vectors(self, user_id: int, course_ids: list[int]) -> None:
        self.vector_store.delete_collection(str(user_id))
        for course_id in course_ids:
            self.vector_store.delete_collection(f"{user_id}_course_{course_id}")

    def _delete_legacy_material(self, material: MaterialArtifact) -> None:
        self._material_path(material).unlink(missing_ok=True)

    def _material_path(self, material: MaterialArtifact) -> Path:
        if self.upload_root is None:
            raise ValueError("A legacy upload root is not configured")
        if material.storage_path:
            candidate = Path(material.storage_path)
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
        else:
            candidate = self.upload_root / material.filename

        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.upload_root):
            raise ValueError("Material path is outside the upload root")
        return resolved


class AccountDeletionService:
    def __init__(self, db: AsyncSession, cleaner: AccountArtifactCleaner) -> None:
        self.db = db
        self.cleaner = cleaner

    async def request(self, user_id: int) -> AccountDeletionRequestResult:
        await bind_tenant_context(self.db, user_id)
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise AppException("Resource not found", "NOT_FOUND")
        existing = await self.db.scalar(
            select(AccountDeletionJob.id).where(AccountDeletionJob.user_id == user_id)
        )
        if existing is not None:
            raise AppException("Account deletion already requested", "CONFLICT")

        status_token = secrets.token_urlsafe(32)
        now = self._now()
        job = AccountDeletionJob(
            user_id=user.id,
            status_token_hash=self._hash_token(status_token),
            status="pending",
            attempt_count=0,
        )
        user.is_disabled = True
        user.disabled_at = now
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.db.execute(
            update(InviteCode)
            .where(
                InviteCode.created_by_user_id == user_id,
                InviteCode.disabled_at.is_(None),
            )
            .values(disabled_at=now)
        )
        self.db.add(job)
        await self.db.commit()
        return AccountDeletionRequestResult(job=job, status_token=status_token)

    async def execute(self, job_id: str) -> AccountDeletionJob:
        result = await self.db.execute(
            select(AccountDeletionJob)
            .where(AccountDeletionJob.public_id == job_id)
            .with_for_update()
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AppException("Resource not found", "NOT_FOUND")
        await self._execute(job)
        return job

    async def get_status(self, job_id: str, status_token: str) -> AccountDeletionJob:
        job = await self._authenticated_job(job_id, status_token)
        return job

    async def retry(self, job_id: str, status_token: str) -> AccountDeletionJob:
        job = await self._authenticated_job(job_id, status_token, lock=True)
        if job.status == "succeeded":
            return job
        if job.status == "running":
            raise AppException("Account deletion is already running", "CONFLICT")
        await self._execute(job)
        return job

    async def _authenticated_job(
        self,
        job_id: str,
        status_token: str,
        *,
        lock: bool = False,
    ) -> AccountDeletionJob:
        statement = select(AccountDeletionJob).where(
            AccountDeletionJob.public_id == job_id
        )
        if lock:
            statement = statement.with_for_update()
        result = await self.db.execute(statement)
        job = result.scalar_one_or_none()
        token_hash = self._hash_token(status_token)
        if job is None or not secrets.compare_digest(job.status_token_hash, token_hash):
            raise AppException("Resource not found", "NOT_FOUND")
        return job

    async def _execute(self, job: AccountDeletionJob) -> None:
        if job.status == "succeeded":
            return
        if job.user_id is None:
            await self._mark_failed(
                job,
                code="ACCOUNT_DATA_MISSING",
                message=DATABASE_FAILURE_MESSAGE,
            )
            return

        user_id = job.user_id
        job_id = job.public_id
        attempt_count = job.attempt_count + 1
        try:
            await bind_tenant_context(self.db, user_id)
            now = self._now()
            job.status = "running"
            job.attempt_count = attempt_count
            job.started_at = now
            job.completed_at = None
            job.error_code = None
            job.error_message = None
            user = await self.db.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None:
                await self._mark_failed(
                    job,
                    code="ACCOUNT_DATA_MISSING",
                    message=DATABASE_FAILURE_MESSAGE,
                )
                return
            # Fence queued and running material workers before collecting
            # artifacts. The same user-row lock serializes this with upload,
            # indexing, and single-material deletion; clearing the lease makes
            # any late worker fail its ownership check before external writes.
            now = self._now()
            await self.db.execute(
                update(MaterialJob)
                .where(
                    MaterialJob.user_id == user_id,
                    MaterialJob.status.in_(
                        [MaterialJobStatus.QUEUED, MaterialJobStatus.RUNNING]
                    ),
                )
                .values(
                    status=MaterialJobStatus.CANCELLED,
                    current_step="cancelled",
                    completed_at=now,
                    error_code="PROCESSING_CANCELLED",
                    error_message="Material processing cancelled",
                )
            )
            await self.db.execute(
                update(Material)
                .where(
                    Material.user_id == user_id,
                    Material.processing_status == ProcessingStatus.PROCESSING,
                )
                .values(
                    processing_status=ProcessingStatus.FAILED,
                    processing_lease_id=None,
                    processing_lease_expires_at=None,
                    error_message="Material processing cancelled",
                    parse_error="Material processing cancelled",
                )
            )
            await self.db.flush()

            course_ids = list(
                (
                    await self.db.execute(
                        select(Course.id)
                        .where(Course.user_id == user_id)
                        .order_by(Course.id)
                    )
                )
                .scalars()
                .all()
            )
            material_rows = (
                await self.db.execute(
                    select(
                        Material.filename,
                        Material.storage_path,
                        Material.object_key,
                        Material.object_version_id,
                        Material.storage_status,
                        Material.processing_status,
                        Material.processing_lease_expires_at,
                        Material.object_write_uncertain,
                    ).where(Material.user_id == user_id)
                )
            ).all()
            materials = [
                MaterialArtifact(
                    filename=row.filename,
                    storage_path=row.storage_path,
                    object_key=row.object_key,
                    object_version_id=row.object_version_id,
                    storage_status=row.storage_status,
                    processing_status=row.processing_status,
                    processing_lease_expires_at=row.processing_lease_expires_at,
                    object_write_uncertain=row.object_write_uncertain,
                )
                for row in material_rows
            ]
        except Exception as exc:
            await self._record_database_failure(
                job_id,
                user_id,
                attempt_count,
                exc,
            )
            return

        try:
            await self.cleaner.clean(user_id, course_ids, materials)
        except Exception as exc:
            logger.exception(
                "Account artifact cleanup failed job_id=%s user_id=%s error_type=%s",
                job.public_id,
                user_id,
                type(exc).__name__,
            )
            await self._mark_failed(
                job,
                code="ARTIFACT_CLEANUP_FAILED",
                message=ARTIFACT_FAILURE_MESSAGE,
            )
            return

        attempt_count = job.attempt_count
        try:
            job.user_id = None
            job.status = "succeeded"
            job.completed_at = self._now()
            job.error_code = None
            job.error_message = None
            await self.db.delete(user)
            await self.db.commit()
        except Exception as exc:
            logger.exception(
                "Account database deletion failed job_id=%s user_id=%s error_type=%s",
                job_id,
                user_id,
                type(exc).__name__,
            )
            await self.db.rollback()
            try:
                recovered = await self._reload_job(job_id)
                if recovered.status == "succeeded":
                    return
                recovered.attempt_count = max(recovered.attempt_count, attempt_count)
                await self._mark_failed(
                    recovered,
                    code="DATABASE_DELETION_FAILED",
                    message=DATABASE_FAILURE_MESSAGE,
                )
            except Exception as status_exc:
                logger.exception(
                    "Could not recover deletion status job_id=%s error_type=%s",
                    job_id,
                    type(status_exc).__name__,
                )

    async def _record_database_failure(
        self,
        job_id: str,
        user_id: int,
        attempt_count: int,
        exc: Exception,
    ) -> None:
        logger.exception(
            "Account deletion preparation failed job_id=%s user_id=%s error_type=%s",
            job_id,
            user_id,
            type(exc).__name__,
        )
        await self.db.rollback()
        try:
            recovered = await self._reload_job(job_id)
            if recovered.status == "succeeded":
                return
            recovered.attempt_count = max(recovered.attempt_count, attempt_count)
            await self._mark_failed(
                recovered,
                code="DATABASE_DELETION_FAILED",
                message=DATABASE_FAILURE_MESSAGE,
            )
        except Exception as status_exc:
            logger.exception(
                "Could not persist deletion failure job_id=%s error_type=%s",
                job_id,
                type(status_exc).__name__,
            )

    async def _reload_job(self, job_id: str) -> AccountDeletionJob:
        result = await self.db.execute(
            select(AccountDeletionJob).where(AccountDeletionJob.public_id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AppException("Resource not found", "NOT_FOUND")
        return job

    async def _mark_failed(
        self,
        job: AccountDeletionJob,
        *,
        code: str,
        message: str,
    ) -> None:
        if job.status == "succeeded":
            return
        job.status = "failed"
        job.error_code = code
        job.error_message = message
        job.completed_at = self._now()
        await self.db.commit()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)
