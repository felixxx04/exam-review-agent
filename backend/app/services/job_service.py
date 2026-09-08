"""Durable material job state and the Redis delivery boundary."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import bind_tenant_context
from app.db.models import Material, MaterialJob, MaterialJobStatus, ProcessingStatus
from app.tasks.worker import WorkerConfig


logger = logging.getLogger(__name__)
SAFE_PROCESSING_ERROR = "Material processing failed"
SAFE_PROCESSING_CANCELLED = "Material processing cancelled"


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

    async def create_material_job(
        self,
        *,
        user_id: int,
        material_id: int,
        course_id: int,
        priority: int = 0,
    ) -> MaterialJob:
        await bind_tenant_context(self.db, user_id)
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

        material = await self.db.scalar(
            select(Material).where(
                Material.id == material_id,
                Material.user_id == user_id,
                Material.course_id == course_id,
            )
        )
        if material is None:
            raise LookupError("material not found")

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
        await self.db.commit()
        await self.db.refresh(job)
        await self._enqueue(job)
        return job

    async def _enqueue(self, job: MaterialJob) -> bool:
        queue = self.queue
        owns_queue = queue is None
        if queue is None:
            try:
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

    async def cancel_material_job(self, *, user_id: int, material_id: int) -> MaterialJob:
        await bind_tenant_context(self.db, user_id)
        job = await self.get_material_job(user_id=user_id, material_id=material_id)
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
            .where(Material.id == material_id, Material.user_id == user_id)
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

    async def retry_material_job(self, *, user_id: int, material_id: int) -> MaterialJob:
        await bind_tenant_context(self.db, user_id)
        job = await self.get_material_job(user_id=user_id, material_id=material_id)
        if job.status == MaterialJobStatus.SUCCEEDED:
            return job
        if job.status in {MaterialJobStatus.QUEUED, MaterialJobStatus.RUNNING}:
            return job
        delay = min(3600, 2 ** max(job.attempt_count, 0))
        job.status = MaterialJobStatus.QUEUED
        job.current_step = "queued"
        job.available_at = self._now() + datetime.timedelta(seconds=delay)
        job.completed_at = None
        job.error_code = None
        job.error_message = None
        await self.db.execute(
            update(Material)
            .where(Material.id == material_id, Material.user_id == user_id)
            .values(
                processing_status=ProcessingStatus.PENDING,
                error_message=None,
                parse_error=None,
            )
        )
        await self.db.commit()
        await self._enqueue(job)
        return job

    async def update_progress(
        self,
        *,
        user_id: int,
        job_id: str,
        percent: int,
        step: str,
    ) -> None:
        await bind_tenant_context(self.db, user_id)
        await self.db.execute(
            update(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
                MaterialJob.status == MaterialJobStatus.RUNNING,
            )
            .values(progress_percent=max(0, min(100, percent)), current_step=step)
        )
        await self.db.commit()

    async def claim_job(self, *, user_id: int, job_id: str) -> MaterialJob | None:
        await bind_tenant_context(self.db, user_id)
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
        if job.available_at > now:
            await self.db.rollback()
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

    async def is_cancelled(self, *, user_id: int, job_id: str) -> bool:
        await bind_tenant_context(self.db, user_id)
        job = await self.db.scalar(
            select(MaterialJob.status).where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
            )
        )
        return job == MaterialJobStatus.CANCELLED

    async def mark_succeeded(
        self, *, user_id: int, job_id: str, progress_percent: int = 100
    ) -> None:
        await bind_tenant_context(self.db, user_id)
        await self.db.execute(
            update(MaterialJob)
            .where(
                MaterialJob.public_id == job_id,
                MaterialJob.user_id == user_id,
                MaterialJob.status == MaterialJobStatus.RUNNING,
            )
            .values(
                status=MaterialJobStatus.SUCCEEDED,
                progress_percent=progress_percent,
                current_step="completed",
                completed_at=self._now(),
                error_code=None,
                error_message=None,
            )
        )
        await self.db.commit()

    async def mark_failed(
        self,
        *,
        user_id: int,
        job_id: str,
        error_code: str = "PROCESSING_FAILED",
    ) -> MaterialJob | None:
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
            await self.db.rollback()
            return None
        now = self._now()
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
        await self.db.commit()
        return job

    async def recover_jobs(
        self,
        *,
        older_than: datetime.datetime,
        user_id: int | None = None,
    ) -> int:
        if user_id is not None:
            await bind_tenant_context(self.db, user_id)
        now = self._now()
        conditions = []
        if user_id is not None:
            conditions.append(MaterialJob.user_id == user_id)
        result = await self.db.execute(
            select(MaterialJob)
            .where(
                *conditions,
                (
                    (MaterialJob.status == MaterialJobStatus.QUEUED)
                    & (MaterialJob.available_at <= now)
                )
                | (
                    (MaterialJob.status == MaterialJobStatus.RUNNING)
                    & (MaterialJob.updated_at < older_than)
                ),
            )
            .order_by(MaterialJob.priority.desc(), MaterialJob.created_at)
        )
        jobs = list(result.scalars().all())
        recovered = 0
        for job in jobs:
            if job.status == MaterialJobStatus.RUNNING:
                if job.attempt_count >= job.max_attempts:
                    job.status = MaterialJobStatus.FAILED
                    job.current_step = "failed"
                    job.error_code = "WORKER_INTERRUPTED"
                    job.error_message = SAFE_PROCESSING_ERROR
                    job.completed_at = now
                    continue
                job.status = MaterialJobStatus.QUEUED
                job.current_step = "recovered"
                job.available_at = now
                job.started_at = None
            await self.db.commit()
            await self._enqueue(job)
            recovered += 1
        return recovered

    async def set_priority(
        self, *, job_id: str, priority: int, user_id: int | None = None
    ) -> MaterialJob | None:
        if user_id is not None:
            await bind_tenant_context(self.db, user_id)
        statement = select(MaterialJob).where(MaterialJob.public_id == job_id)
        if user_id is not None:
            statement = statement.where(MaterialJob.user_id == user_id)
        job = await self.db.scalar(statement.with_for_update())
        if job is None:
            await self.db.rollback()
            return None
        job.priority = priority
        await self.db.commit()
        return job
