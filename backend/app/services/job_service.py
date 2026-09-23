"""Durable material job state and the Redis delivery boundary."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.database import bind_tenant_context
from app.db.models import (
    Material,
    MaterialChunk,
    MaterialJob,
    MaterialJobStatus,
    ProcessingStatus,
    StorageStatus,
    User,
)
from app.services.material_storage_cleanup import delete_material_chunks


logger = logging.getLogger(__name__)
SAFE_PROCESSING_ERROR = "Material processing failed"
SAFE_PROCESSING_CANCELLED = "Material processing cancelled"
SAFE_INDEX_CLEANUP_PENDING = "Material index cleanup is pending"
SAFE_INDEX_CLEANUP_ERROR_CODE = "INDEX_CLEANUP_PENDING"


class JobQueue(Protocol):
    async def enqueue_job(self, function_name: str, *args: Any, **kwargs: Any) -> Any: ...


QueueFactory = Callable[[], Awaitable[JobQueue]]


class JobService:
    """Keep PostgreSQL authoritative while Redis only delivers wakeups."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        queue: JobQueue | None = None,
        now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self.db = db
        self.queue = queue
        self._now_factory = now or (lambda: datetime.datetime.now(datetime.UTC))

    def _now(self) -> datetime.datetime:
        value = self._now_factory()
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.UTC)
        return value

    @staticmethod
    def _aware(value: datetime.datetime) -> datetime.datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.UTC)
        return value

    async def _cleanup_material_index(
        self, *, user_id: int, material_id: int, course_id: int
    ) -> bool:
        """Delete durable chunk intent and external vectors before another attempt."""
        try:
            await self._lock_user(user_id)
            material = await self.db.scalar(
                select(Material)
                .where(
                    Material.id == material_id,
                    Material.user_id == user_id,
                    Material.course_id == course_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if material is None:
                await self.db.rollback()
                return False
            await delete_material_chunks(self.db, material=material)
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            logger.warning(
                "Could not clean material index before retry material_id=%s",
                material_id,
                exc_info=True,
            )
            return False

    async def _finish_cleanup_recovery(
        self,
        *,
        user_id: int,
        job_id: str,
        immediate: bool = True,
    ) -> bool:
        """Requeue a cleanup-fenced job only after reloading current state."""
        await self._lock_user(user_id, require_active=True)
        job = await self.db.scalar(
            select(MaterialJob)
            .where(MaterialJob.public_id == job_id, MaterialJob.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None or (
            job.status != MaterialJobStatus.FAILED
            or job.error_code != SAFE_INDEX_CLEANUP_ERROR_CODE
        ):
            await self.db.rollback()
            return False
        material = await self.db.scalar(
            select(Material)
            .where(
                Material.id == job.material_id,
                Material.user_id == user_id,
                Material.course_id == job.course_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if material is None or material.storage_status != StorageStatus.AVAILABLE:
            await self.db.rollback()
            return False
        if material.processing_status == ProcessingStatus.READY:
            job.status = MaterialJobStatus.SUCCEEDED
            job.progress_percent = 100
            job.current_step = "completed"
            job.completed_at = self._now()
            job.error_code = None
            job.error_message = None
            material.processing_lease_id = None
            material.processing_lease_expires_at = None
            await self.db.commit()
            return True
        has_chunks = await self.db.scalar(
            select(MaterialChunk.id)
            .where(
                MaterialChunk.material_id == material.id,
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == material.course_id,
            )
            .limit(1)
        )
        if has_chunks is not None:
            await self.db.rollback()
            return False

        now = self._now()
        if job.attempt_count >= job.max_attempts:
            job.current_step = "failed"
            job.error_code = "WORKER_INTERRUPTED"
            job.error_message = SAFE_PROCESSING_ERROR
            job.completed_at = now
            material.processing_status = ProcessingStatus.FAILED
            material.error_message = SAFE_PROCESSING_ERROR
            material.parse_error = SAFE_PROCESSING_ERROR
            material.processing_lease_id = None
            material.processing_lease_expires_at = None
            await self.db.commit()
            return True

        delay = 0 if immediate else min(
            3600, 2 ** max(job.attempt_count - 1, 0)
        )
        job.status = MaterialJobStatus.QUEUED
        job.progress_percent = 0
        job.current_step = "queued"
        job.available_at = now + datetime.timedelta(seconds=delay)
        job.started_at = None
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        material.processing_status = ProcessingStatus.PENDING
        material.processing_lease_id = None
        material.processing_lease_expires_at = None
        material.error_message = None
        material.parse_error = None
        await self.db.commit()
        await self._enqueue(job)
        return True

    async def _lock_user(
        self, user_id: int, *, require_active: bool = False
    ) -> User:
        await bind_tenant_context(self.db, user_id)
        user = await self.db.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None:
            raise LookupError("user not found")
        if require_active and user.is_disabled:
            raise AppException(
                "Account deletion is in progress",
                "ACCOUNT_DELETION_IN_PROGRESS",
            )
        return user

    async def create_material_job(
        self,
        *,
        user_id: int,
        material_id: int,
        course_id: int,
        priority: int = 0,
        commit: bool = True,
        enqueue: bool = True,
    ) -> MaterialJob:
        await self._lock_user(user_id, require_active=True)
        material = await self.db.scalar(
            select(Material)
            .where(
                Material.id == material_id,
                Material.user_id == user_id,
                Material.course_id == course_id,
            )
            .with_for_update()
        )
        if material is None:
            raise LookupError("material not found")
        if material.storage_status != StorageStatus.AVAILABLE:
            await self.db.rollback()
            raise LookupError("material not found")

        active = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.user_id == user_id,
                MaterialJob.material_id == material_id,
                MaterialJob.status.in_(
                    [MaterialJobStatus.QUEUED, MaterialJobStatus.RUNNING]
                ),
            )
            .order_by(MaterialJob.id.desc())
        )
        if active is not None:
            return active

        prior_ids = (
            await self.db.scalars(
                select(MaterialJob.id)
                .where(
                    MaterialJob.user_id == user_id,
                    MaterialJob.material_id == material_id,
                )
                .order_by(MaterialJob.id)
            )
        ).all()
        generation = len(prior_ids)
        job = MaterialJob(
            user_id=user_id,
            course_id=course_id,
            material_id=material_id,
            job_type="material.process",
            idempotency_key=f"material:{material_id}:process:{generation}",
            status=MaterialJobStatus.QUEUED,
            progress_percent=0,
            current_step="queued",
            attempt_count=0,
            max_attempts=3,
            priority=priority,
            available_at=self._now(),
        )
        self.db.add(job)
        if commit:
            await self.db.commit()
            await self.db.refresh(job)
            if enqueue:
                await self._enqueue(job)
        else:
            await self.db.flush()
        return job

    async def enqueue_material_job(self, job: MaterialJob) -> bool:
        return await self._enqueue(job)

    async def _enqueue(self, job: MaterialJob) -> bool:
        queue = self.queue
        owns_queue = queue is None
        if queue is None:
            try:
                from app.tasks.worker import WorkerConfig

                queue = await WorkerConfig.get_pool()
            except Exception:
                logger.warning("Material job queue is unavailable")
                return False
        try:
            result = await queue.enqueue_job(
                "process_material_job",
                job.public_id,
                job.user_id,
                _job_id=job.public_id,
                _defer_until=self._aware(job.available_at),
            )
            job.redis_job_id = getattr(result, "job_id", None) or job.public_id
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            logger.warning("Could not enqueue material job; recovery will retry")
            return False
        finally:
            if owns_queue:
                close = getattr(queue, "close", None)
                if close is not None:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result

    async def get_material_job(self, *, user_id: int, material_id: int) -> MaterialJob:
        await bind_tenant_context(self.db, user_id)
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.user_id == user_id,
                MaterialJob.material_id == material_id,
            )
            .order_by(MaterialJob.id.desc())
        )
        if job is None:
            raise LookupError("material job not found")
        return job

    async def get_job(self, *, user_id: int, job_id: str) -> MaterialJob:
        await bind_tenant_context(self.db, user_id)
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
            .with_for_update()
        )
        if job is None:
            raise LookupError("material job not found")
        return job

    async def retry_job(self, *, user_id: int, job_id: str) -> MaterialJob:
        await self._lock_user(user_id, require_active=True)
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None:
            raise LookupError("material job not found")
        if job.status == MaterialJobStatus.SUCCEEDED:
            return job
        if job.status in {MaterialJobStatus.QUEUED, MaterialJobStatus.RUNNING}:
            return job
        if job.status == MaterialJobStatus.CANCELLED:
            await self.db.rollback()
            raise AppException(
                "Cancelled material jobs cannot be retried",
                "CONFLICT",
            )
        material = await self.db.scalar(
            select(Material)
            .where(
                Material.id == job.material_id,
                Material.user_id == user_id,
                Material.course_id == job.course_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if material is None or material.storage_status != StorageStatus.AVAILABLE:
            await self.db.rollback()
            raise LookupError("material not found")
        try:
            await delete_material_chunks(self.db, material=material)
        except Exception as exc:
            await self.db.rollback()
            raise AppException(
                "Material index cleanup is pending", "CONFLICT"
            ) from exc
        delay = min(3600, 2 ** max(job.attempt_count, 0))
        job.status = MaterialJobStatus.QUEUED
        job.attempt_count = 0
        job.progress_percent = 0
        job.current_step = "queued"
        job.available_at = self._now() + datetime.timedelta(seconds=delay)
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        await self.db.execute(
            update(Material)
            .where(
                Material.id == job.material_id,
                Material.user_id == user_id,
            )
            .values(
                processing_status=ProcessingStatus.PENDING,
                processing_lease_id=None,
                processing_lease_expires_at=None,
                error_message=None,
                parse_error=None,
            )
        )
        await self.db.commit()
        await self._enqueue(job)
        return job

    async def cancel_material_job(self, *, user_id: int, material_id: int) -> MaterialJob:
        await self._lock_user(user_id, require_active=True)
        material = await self.db.scalar(
            select(Material)
            .where(Material.id == material_id, Material.user_id == user_id)
            .with_for_update()
        )
        if material is None:
            raise LookupError("material not found")
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.user_id == user_id,
                MaterialJob.material_id == material_id,
            )
            .order_by(MaterialJob.id.desc())
            .with_for_update()
        )
        if job is None:
            raise LookupError("material job not found")
        if job.status in {
            MaterialJobStatus.SUCCEEDED,
            MaterialJobStatus.FAILED,
            MaterialJobStatus.CANCELLED,
        }:
            return job
        job.status = MaterialJobStatus.CANCELLED
        job.current_step = "cancelled"
        job.completed_at = self._now()
        job.error_code = "PROCESSING_CANCELLED"
        job.error_message = SAFE_PROCESSING_CANCELLED
        await self.db.execute(
            update(Material)
            .where(
                Material.id == material_id,
                Material.user_id == user_id,
                Material.processing_status.in_(
                    [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
                ),
            )
            .values(
                processing_status=ProcessingStatus.FAILED,
                processing_lease_id=None,
                processing_lease_expires_at=None,
                error_message=SAFE_PROCESSING_CANCELLED,
                parse_error=SAFE_PROCESSING_CANCELLED,
            )
        )
        await self.db.commit()
        return job

    async def cancel_jobs_for_material(
        self,
        *,
        user_id: int,
        material_id: int,
        commit: bool = True,
    ) -> int:
        await self._lock_user(user_id)
        await self.db.scalar(
            select(Material)
            .where(Material.id == material_id, Material.user_id == user_id)
            .with_for_update()
        )
        result = await self.db.execute(
            select(MaterialJob)
            .where(
                MaterialJob.user_id == user_id,
                MaterialJob.material_id == material_id,
                MaterialJob.status.in_(
                    [MaterialJobStatus.QUEUED, MaterialJobStatus.RUNNING]
                ),
            )
            .with_for_update()
        )
        jobs = list(result.scalars().all())
        now = self._now()
        for job in jobs:
            job.status = MaterialJobStatus.CANCELLED
            job.current_step = "cancelled"
            job.completed_at = now
            job.error_code = "PROCESSING_CANCELLED"
            job.error_message = SAFE_PROCESSING_CANCELLED
        if jobs:
            await self.db.execute(
                update(Material)
                .where(Material.id == material_id, Material.user_id == user_id)
                .values(
                    processing_status=ProcessingStatus.FAILED,
                    processing_lease_id=None,
                    processing_lease_expires_at=None,
                    error_message=SAFE_PROCESSING_CANCELLED,
                    parse_error=SAFE_PROCESSING_CANCELLED,
                )
            )
        if commit:
            await self.db.commit()
        return len(jobs)

    async def list_jobs(
        self,
        *,
        user_id: int,
        status: MaterialJobStatus | None = None,
    ) -> list[MaterialJob]:
        await bind_tenant_context(self.db, user_id)
        statement = select(MaterialJob).order_by(
            MaterialJob.priority.desc(), MaterialJob.created_at
        )
        statement = statement.where(MaterialJob.user_id == user_id)
        if status is not None:
            statement = statement.where(MaterialJob.status == status)
        return list((await self.db.scalars(statement)).all())

    async def retry_material_job(self, *, user_id: int, material_id: int) -> MaterialJob:
        await self._lock_user(user_id, require_active=True)
        job = await self.get_material_job(user_id=user_id, material_id=material_id)
        return await self.retry_job(user_id=user_id, job_id=job.public_id)

    async def update_progress(
        self,
        *,
        user_id: int,
        job_id: str,
        percent: int,
        step: str,
        attempt_count: int | None = None,
    ) -> None:
        await self._lock_user(user_id)
        statement = update(MaterialJob).where(
            MaterialJob.public_id == job_id,
            MaterialJob.user_id == user_id,
            MaterialJob.status == MaterialJobStatus.RUNNING,
        )
        if attempt_count is not None:
            statement = statement.where(MaterialJob.attempt_count == attempt_count)
        result = await self.db.execute(
            statement.values(
                progress_percent=max(0, min(100, percent)), current_step=step
            )
        )
        if result.rowcount != 1:
            await self.db.rollback()
            return
        await self.db.commit()

    async def claim_job(self, *, user_id: int, job_id: str) -> MaterialJob | None:
        owner = await self._lock_user(user_id)
        if owner.is_disabled:
            await self.db.rollback()
            return None
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
            .with_for_update()
        )
        if job is None or job.status != MaterialJobStatus.QUEUED:
            await self.db.rollback()
            return None
        now = self._now()
        if self._aware(job.available_at) > now:
            await self.db.rollback()
            return None
        if job.attempt_count >= job.max_attempts:
            job.status = MaterialJobStatus.FAILED
            job.current_step = "failed"
            job.error_code = "MAX_ATTEMPTS_EXCEEDED"
            job.error_message = SAFE_PROCESSING_ERROR
            job.completed_at = now
            await self.db.execute(
                update(Material)
                .where(
                    Material.id == job.material_id,
                    Material.user_id == user_id,
                )
                .values(
                    processing_status=ProcessingStatus.FAILED,
                    error_message=SAFE_PROCESSING_ERROR,
                    parse_error=SAFE_PROCESSING_ERROR,
                    processing_lease_id=None,
                    processing_lease_expires_at=None,
                )
            )
            await self.db.commit()
            return None
        job.status = MaterialJobStatus.RUNNING
        job.current_step = "starting"
        job.attempt_count += 1
        job.started_at = now
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        await self.db.commit()
        return job

    async def is_cancelled(
        self,
        *,
        user_id: int,
        job_id: str,
        attempt_count: int | None = None,
    ) -> bool:
        await bind_tenant_context(self.db, user_id)
        result = await self.db.execute(
            select(MaterialJob.status, MaterialJob.attempt_count).where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
        )
        job = result.first()
        if job is None:
            return True
        status, current_attempt = job
        return status != MaterialJobStatus.RUNNING or (
            attempt_count is not None and current_attempt != attempt_count
        )

    async def mark_succeeded(
        self,
        *,
        user_id: int,
        job_id: str,
        progress_percent: int = 100,
        attempt_count: int | None = None,
    ) -> None:
        await self._lock_user(user_id)
        statement = update(MaterialJob).where(
            MaterialJob.public_id == job_id,
            MaterialJob.user_id == user_id,
            MaterialJob.status == MaterialJobStatus.RUNNING,
        )
        if attempt_count is not None:
            statement = statement.where(MaterialJob.attempt_count == attempt_count)
        result = await self.db.execute(
            statement.values(
                status=MaterialJobStatus.SUCCEEDED,
                progress_percent=progress_percent,
                current_step="completed",
                completed_at=self._now(),
                error_code=None,
                error_message=None,
            )
        )
        if result.rowcount != 1:
            await self.db.rollback()
            return
        await self.db.commit()

    async def mark_cancelled(
        self,
        *,
        user_id: int,
        job_id: str,
        attempt_count: int | None = None,
    ) -> None:
        await self._lock_user(user_id)
        statement = update(MaterialJob).where(
            MaterialJob.public_id == job_id,
            MaterialJob.user_id == user_id,
            MaterialJob.status == MaterialJobStatus.RUNNING,
        )
        if attempt_count is not None:
            statement = statement.where(MaterialJob.attempt_count == attempt_count)
        result = await self.db.execute(
            statement.values(
                status=MaterialJobStatus.CANCELLED,
                current_step="cancelled",
                completed_at=self._now(),
                error_code="PROCESSING_CANCELLED",
                error_message=SAFE_PROCESSING_CANCELLED,
            )
        )
        if result.rowcount != 1:
            await self.db.rollback()
            return
        await self.db.execute(
            update(Material)
            .where(Material.user_id == user_id)
            .where(
                Material.processing_status.in_(
                    [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
                )
            )
            .where(
                Material.id
                == select(MaterialJob.material_id)
                .where(
                    MaterialJob.public_id == job_id,
                    MaterialJob.user_id == user_id,
                )
                .scalar_subquery()
            )
            .values(
                processing_status=ProcessingStatus.FAILED,
                processing_lease_id=None,
                processing_lease_expires_at=None,
                error_message=SAFE_PROCESSING_CANCELLED,
                parse_error=SAFE_PROCESSING_CANCELLED,
            )
        )
        await self.db.commit()

    async def mark_failed(
        self,
        *,
        user_id: int,
        job_id: str,
        error_code: str = "PROCESSING_FAILED",
        attempt_count: int | None = None,
    ) -> MaterialJob | None:
        await self._lock_user(user_id)
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
            .with_for_update()
        )
        if job is None:
            await self.db.rollback()
            return None
        if job.status != MaterialJobStatus.RUNNING or (
            attempt_count is not None and job.attempt_count != attempt_count
        ):
            await self.db.rollback()
            return job
        material = await self.db.scalar(
            select(Material)
            .where(
                Material.id == job.material_id,
                Material.user_id == user_id,
                Material.course_id == job.course_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if material is not None and material.processing_status == ProcessingStatus.READY:
            job.status = MaterialJobStatus.SUCCEEDED
            job.progress_percent = 100
            job.current_step = "completed"
            job.completed_at = self._now()
            job.error_code = None
            job.error_message = None
            await self.db.commit()
            return job
        now = self._now()
        has_cleanup_intent = (
            await self.db.scalar(
                select(MaterialChunk.id)
                .where(
                    MaterialChunk.material_id == job.material_id,
                    MaterialChunk.user_id == user_id,
                    MaterialChunk.course_id == job.course_id,
                )
                .limit(1)
            )
            is not None
        )
        if has_cleanup_intent:
            cleanup_already_attempted = (
                material is not None
                and material.processing_status == ProcessingStatus.FAILED
                and material.error_message == SAFE_INDEX_CLEANUP_PENDING
            )
            # Fence the worker before touching the external index. A failed
            # cleanup remains terminal and is picked up by the recovery scan.
            job.status = MaterialJobStatus.FAILED
            job.current_step = "cleanup_pending"
            job.completed_at = now
            job.error_code = SAFE_INDEX_CLEANUP_ERROR_CODE
            job.error_message = SAFE_INDEX_CLEANUP_PENDING
            if material is not None:
                material.processing_status = ProcessingStatus.FAILED
                material.processing_lease_id = None
                material.processing_lease_expires_at = None
                material.error_message = SAFE_INDEX_CLEANUP_PENDING
                material.parse_error = SAFE_INDEX_CLEANUP_PENDING
            await self.db.commit()
            if cleanup_already_attempted:
                return job
            if not await self._cleanup_material_index(
                user_id=user_id,
                material_id=job.material_id,
                course_id=job.course_id,
            ):
                return job
            await self._finish_cleanup_recovery(
                user_id=user_id,
                job_id=job.public_id,
                immediate=False,
            )
            await self.db.refresh(job)
            return job

        job.error_code = error_code
        job.error_message = SAFE_PROCESSING_ERROR
        if job.attempt_count < job.max_attempts:
            job.status = MaterialJobStatus.QUEUED
            job.current_step = "retry_wait"
            job.available_at = now + datetime.timedelta(
                seconds=min(3600, 2 ** max(job.attempt_count - 1, 0))
            )
        else:
            job.status = MaterialJobStatus.FAILED
            job.current_step = "failed"
            job.completed_at = now
        material_status = (
            ProcessingStatus.PENDING
            if job.status == MaterialJobStatus.QUEUED
            else ProcessingStatus.FAILED
        )
        await self.db.execute(
            update(Material)
            .where(
                Material.id == job.material_id,
                Material.user_id == user_id,
                Material.processing_status != ProcessingStatus.READY,
            )
            .values(
                processing_status=material_status,
                error_message=(
                    None if job.status == MaterialJobStatus.QUEUED else SAFE_PROCESSING_ERROR
                ),
                parse_error=(
                    None if job.status == MaterialJobStatus.QUEUED else SAFE_PROCESSING_ERROR
                ),
            )
        )
        await self.db.commit()
        if job.status == MaterialJobStatus.QUEUED:
            await self._enqueue(job)
        return job

    async def recover_jobs(
        self,
        *,
        older_than: datetime.datetime,
        user_id: int | None = None,
    ) -> int:
        if user_id is None:
            # material_jobs is FORCE ROW LEVEL SECURITY on PostgreSQL. Enumerate
            # owners from the non-tenant users table, then scan each owner in a
            # trusted tenant-bound transaction rather than bypassing RLS.
            await self.db.commit()
            owner_ids = list((await self.db.scalars(select(User.id))).all())
            recovered = 0
            for owner_id in owner_ids:
                try:
                    recovered += await self.recover_jobs(
                        older_than=older_than,
                        user_id=owner_id,
                    )
                except LookupError:
                    # The owner may have been deleted after enumeration.
                    continue
            return recovered
        owner = await self._lock_user(user_id)
        if owner.is_disabled:
            await self.db.rollback()
            return 0
        # Release the owner lock before collecting IDs. Each candidate is
        # reloaded and locked in its own transaction below, so a stale scan
        # cannot mutate a job after another worker has changed its state.
        await self.db.commit()
        now = self._now()
        older_than = self._aware(older_than)
        await bind_tenant_context(self.db, user_id)
        candidate_ids = list(
            (
                await self.db.scalars(
                    select(MaterialJob.public_id)
                    .where(
                        MaterialJob.user_id == user_id,
                        or_(
                            (
                                (MaterialJob.status == MaterialJobStatus.QUEUED)
                                & (MaterialJob.available_at <= now)
                            ),
                            (
                                (MaterialJob.status == MaterialJobStatus.RUNNING)
                                & (MaterialJob.updated_at < older_than)
                            ),
                            (
                                (MaterialJob.status == MaterialJobStatus.FAILED)
                                & (
                                    MaterialJob.error_code
                                    == SAFE_INDEX_CLEANUP_ERROR_CODE
                                )
                            ),
                        ),
                    )
                    .order_by(MaterialJob.priority.desc(), MaterialJob.created_at)
                )
            ).all()
        )
        await self.db.commit()
        recovered = 0
        for job_id in candidate_ids:
            if await self._recover_one_job(
                user_id=user_id,
                job_id=job_id,
                older_than=older_than,
            ):
                recovered += 1
        return recovered

    async def _recover_one_job(
        self,
        *,
        user_id: int,
        job_id: str,
        older_than: datetime.datetime,
    ) -> bool:
        """Recover one candidate under a fresh tenant-bound lock window."""
        await self._lock_user(user_id)
        job = await self.db.scalar(
            select(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None:
            await self.db.rollback()
            return False
        now = self._now()
        is_due = job.status == MaterialJobStatus.QUEUED and self._aware(
            job.available_at
        ) <= now
        is_stale = job.status == MaterialJobStatus.RUNNING and self._aware(
            job.updated_at
        ) < older_than
        is_cleanup_retry = (
            job.status == MaterialJobStatus.FAILED
            and job.error_code == SAFE_INDEX_CLEANUP_ERROR_CODE
        )
        if not (is_due or is_stale or is_cleanup_retry):
            await self.db.rollback()
            return False

        material = await self.db.scalar(
            select(Material)
            .where(
                Material.id == job.material_id,
                Material.user_id == user_id,
                Material.course_id == job.course_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if material is None or material.storage_status != StorageStatus.AVAILABLE:
            job.status = MaterialJobStatus.FAILED
            job.current_step = "failed"
            job.error_code = "MATERIAL_UNAVAILABLE"
            job.error_message = SAFE_PROCESSING_ERROR
            job.completed_at = now
            await self.db.commit()
            return True

        if material.processing_status == ProcessingStatus.READY:
            job.status = MaterialJobStatus.SUCCEEDED
            job.progress_percent = 100
            job.current_step = "completed"
            job.completed_at = now
            job.error_code = None
            job.error_message = None
            material.processing_lease_id = None
            material.processing_lease_expires_at = None
            await self.db.commit()
            return True

        chunk_ids = list(
            (
                await self.db.scalars(
                    select(MaterialChunk.chunk_id).where(
                        MaterialChunk.material_id == material.id,
                        MaterialChunk.user_id == user_id,
                        MaterialChunk.course_id == material.course_id,
                    )
                )
            ).all()
        )
        if chunk_ids:
            # Commit the fence before the external deletion. A worker that
            # resumes after this point will fail its lease/attempt check.
            job.status = MaterialJobStatus.FAILED
            job.current_step = "cleanup_pending"
            job.completed_at = now
            job.error_code = SAFE_INDEX_CLEANUP_ERROR_CODE
            job.error_message = SAFE_INDEX_CLEANUP_PENDING
            material.processing_status = ProcessingStatus.FAILED
            material.processing_lease_id = None
            material.processing_lease_expires_at = None
            material.error_message = SAFE_INDEX_CLEANUP_PENDING
            material.parse_error = SAFE_INDEX_CLEANUP_PENDING
            await self.db.commit()
            if not await self._cleanup_material_index(
                user_id=user_id,
                material_id=material.id,
                course_id=material.course_id,
            ):
                return True
            await self._finish_cleanup_recovery(
                user_id=user_id,
                job_id=job.public_id,
            )
            return True

        if job.attempt_count >= job.max_attempts:
            job.status = MaterialJobStatus.FAILED
            job.current_step = "failed"
            job.error_code = "WORKER_INTERRUPTED"
            job.error_message = SAFE_PROCESSING_ERROR
            job.completed_at = now
            material.processing_status = ProcessingStatus.FAILED
            material.processing_lease_id = None
            material.processing_lease_expires_at = None
            material.error_message = SAFE_PROCESSING_ERROR
            material.parse_error = SAFE_PROCESSING_ERROR
            await self.db.commit()
            return True

        job.status = MaterialJobStatus.QUEUED
        job.progress_percent = 0
        job.current_step = "recovered"
        job.available_at = now
        job.started_at = None
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        material.processing_status = ProcessingStatus.PENDING
        material.processing_lease_id = None
        material.processing_lease_expires_at = None
        material.error_message = None
        material.parse_error = None
        await self.db.commit()
        await self._enqueue(job)
        return True

    async def list_jobs_for_admin(
        self,
        *,
        status: MaterialJobStatus | None = None,
        limit: int = 100,
    ) -> list[MaterialJob]:
        """Read every tenant through individually bound RLS transactions."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        await self.db.commit()
        owner_ids = list((await self.db.scalars(select(User.id))).all())
        jobs: list[MaterialJob] = []
        for owner_id in owner_ids:
            jobs.extend(await self.list_jobs(user_id=owner_id, status=status))
            # Keep scalar fields loaded while ending the tenant-bound
            # transaction; rollback would expire ORM instances before the
            # cross-tenant sort below.
            await self.db.commit()
        jobs.sort(key=lambda item: (-item.priority, item.created_at, item.id))
        return jobs[:limit]

    async def _find_job_for_admin(
        self, job_id: str
    ) -> tuple[int, MaterialJob] | None:
        await self.db.commit()
        owner_ids = list((await self.db.scalars(select(User.id))).all())
        for owner_id in owner_ids:
            await self.db.commit()
            await bind_tenant_context(self.db, owner_id)
            job = await self.db.scalar(
                select(MaterialJob).where(
                    MaterialJob.public_id == job_id,
                    MaterialJob.user_id == owner_id,
                )
            )
            if job is not None:
                return owner_id, job
        await self.db.commit()
        return None

    async def retry_job_for_admin(self, *, job_id: str) -> MaterialJob | None:
        found = await self._find_job_for_admin(job_id)
        if found is None:
            return None
        owner_id, _ = found
        return await self.retry_job(user_id=owner_id, job_id=job_id)

    async def set_priority_for_admin(
        self, *, job_id: str, priority: int
    ) -> MaterialJob | None:
        found = await self._find_job_for_admin(job_id)
        if found is None:
            return None
        owner_id, _ = found
        return await self.set_priority(
            job_id=job_id,
            priority=priority,
            user_id=owner_id,
        )

    async def set_priority(
        self, *, job_id: str, priority: int, user_id: int
    ) -> MaterialJob | None:
        await bind_tenant_context(self.db, user_id)
        statement = select(MaterialJob).where(
            MaterialJob.public_id == job_id,
            MaterialJob.user_id == user_id,
        )
        job = await self.db.scalar(statement.with_for_update())
        if job is None:
            await self.db.rollback()
            return None
        job.priority = priority
        await self.db.commit()
        return job
