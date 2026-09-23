"""ARQ entrypoints for durable material processing jobs."""

from __future__ import annotations

import logging
import datetime
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_object_storage
from app.api.materials import MaterialProcessingCancelled, _process_material
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Material, ProcessingStatus, StorageStatus, User
from app.services.job_service import JobService
from app.services.material_storage_cleanup import (
    recover_stale_material_reservations_for_user,
)
from app.services.object_storage import ObjectStorage


logger = logging.getLogger(__name__)


@asynccontextmanager
async def _job_session(ctx: dict[str, Any]):
    supplied = ctx.get("db_session")
    if supplied is not None:
        yield supplied
        return
    async with AsyncSessionLocal() as session:
        yield session


async def process_material_job(
    ctx: dict[str, Any], job_id: str, user_id: int
) -> None:
    """Claim and execute one material job, keeping PostgreSQL authoritative."""
    async with _job_session(ctx) as db:
        queue = ctx.get("redis")
        jobs = JobService(db, queue=queue if hasattr(queue, "enqueue_job") else None)
        job = await jobs.claim_job(user_id=user_id, job_id=job_id)
        if job is None:
            return
        attempt_count = job.attempt_count

        material = await db.scalar(
            select(Material).where(
                Material.id == job.material_id,
                Material.user_id == user_id,
                Material.course_id == job.course_id,
            )
        )
        if material is None or material.storage_status != StorageStatus.AVAILABLE:
            await jobs.mark_failed(
                user_id=user_id,
                job_id=job_id,
                error_code="MATERIAL_UNAVAILABLE",
                attempt_count=attempt_count,
            )
            return

        storage: ObjectStorage = ctx.get("object_storage") or get_object_storage()

        async def progress(percent: int, step: str) -> None:
            try:
                await jobs.update_progress(
                    user_id=user_id,
                    job_id=job_id,
                    percent=percent,
                    step=step,
                    attempt_count=attempt_count,
                )
            except SQLAlchemyError:
                await db.rollback()
                raise
            except Exception:
                await db.rollback()
                logger.warning("Could not persist material job progress")

        async def cancellation_check() -> bool:
            return await jobs.is_cancelled(
                user_id=user_id,
                job_id=job_id,
                attempt_count=attempt_count,
            )

        try:
            await _process_material(
                db,
                storage=storage,
                material=material,
                user_subject=str(user_id),
                course_id=job.course_id,
                progress=progress,
                cancellation_check=cancellation_check,
            )
            await db.refresh(material)
            if await jobs.is_cancelled(
                user_id=user_id,
                job_id=job_id,
                attempt_count=attempt_count,
            ):
                await jobs.mark_cancelled(
                    user_id=user_id,
                    job_id=job_id,
                    attempt_count=attempt_count,
                )
                return
            if material.processing_status == ProcessingStatus.READY:
                await jobs.mark_succeeded(
                    user_id=user_id,
                    job_id=job_id,
                    attempt_count=attempt_count,
                )
            else:
                await jobs.mark_failed(
                    user_id=user_id,
                    job_id=job_id,
                    attempt_count=attempt_count,
                )
        except MaterialProcessingCancelled:
            await db.rollback()
            await jobs.mark_cancelled(
                user_id=user_id,
                job_id=job_id,
                attempt_count=attempt_count,
            )
        except Exception:
            await db.rollback()
            await jobs.mark_failed(
                user_id=user_id,
                job_id=job_id,
                attempt_count=attempt_count,
            )


# Keep the old import name available to worker discovery code.
parse_material = process_material_job


async def recover_material_jobs(ctx: dict[str, Any]) -> int:
    """Requeue jobs whose DB state outlived Redis or a worker process."""
    async with _job_session(ctx) as db:
        queue = ctx.get("redis")
        jobs = JobService(db, queue=queue if hasattr(queue, "enqueue_job") else None)
        user_id = ctx.get("user_id")
        older_than = jobs._now() - datetime.timedelta(
            seconds=settings.material_job_stale_seconds
        )
        owner_ids = (
            [int(user_id)]
            if user_id is not None
            else list((await db.scalars(select(User.id))).all())
        )
        recovered = await jobs.recover_jobs(
            user_id=int(user_id) if user_id is not None else None,
            older_than=older_than,
        )
        storage: ObjectStorage = ctx.get("object_storage") or get_object_storage()
        for owner_id in owner_ids:
            try:
                await recover_stale_material_reservations_for_user(
                    db,
                    storage,
                    user_id=owner_id,
                    older_than=older_than,
                )
            except Exception:
                logger.warning(
                    "Could not recover material storage for tenant", exc_info=True
                )
        return recovered
