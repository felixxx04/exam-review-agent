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
    RefreshToken,
    User,
)


ARTIFACT_FAILURE_MESSAGE = "Account artifacts could not be removed"
DATABASE_FAILURE_MESSAGE = "Account data could not be removed"
logger = logging.getLogger(__name__)


class CollectionStore(Protocol):
    def delete_collection(self, scope: str) -> None: ...


@dataclass(frozen=True)
class MaterialArtifact:
    filename: str
    storage_path: str | None


@dataclass(frozen=True)
class AccountDeletionRequestResult:
    job: AccountDeletionJob
    status_token: str


class AccountArtifactCleaner:
    def __init__(self, upload_root: str | Path, vector_store: CollectionStore) -> None:
        self.upload_root = Path(upload_root).resolve()
        self.vector_store = vector_store

    async def clean(
        self,
        user_id: int,
        course_ids: list[int],
        materials: list[MaterialArtifact],
    ) -> None:
        await asyncio.to_thread(
            self._clean_sync,
            user_id,
            course_ids,
            materials,
        )

    def _clean_sync(
        self,
        user_id: int,
        course_ids: list[int],
        materials: list[MaterialArtifact],
    ) -> None:
        for material in materials:
            self._material_path(material).unlink(missing_ok=True)

        self.vector_store.delete_collection(str(user_id))
        for course_id in course_ids:
            self.vector_store.delete_collection(f"{user_id}_course_{course_id}")

    def _material_path(self, material: MaterialArtifact) -> Path:
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
                    select(Material.filename, Material.storage_path).where(
                        Material.user_id == user_id
                    )
                )
            ).all()
            materials = [
                MaterialArtifact(filename=row.filename, storage_path=row.storage_path)
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
