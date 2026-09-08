"""ARQ entrypoints for durable material processing jobs."""

from __future__ import annotations

import logging
import datetime
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select

from app.api.dependencies import get_object_storage
from app.api.materials import MaterialProcessingCancelled, _process_material
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Material, ProcessingStatus, StorageStatus
from app.services.job_service import JobService
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
        jobs = JobService(db)
        job = await jobs.claim_job(user_id=user_id, job_id=job_id)
        if job is None:
            return

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
                )
            except Exception:
                await db.rollback()
                logger.warning("Could not persist material job progress")

        async def cancellation_check() -> bool:
            return await jobs.is_cancelled(user_id=user_id, job_id=job_id)

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
            if material.processing_status == ProcessingStatus.READY:
                await jobs.mark_succeeded(user_id=user_id, job_id=job_id)
            else:
                await jobs.mark_failed(user_id=user_id, job_id=job_id)
        except MaterialProcessingCancelled:
            await db.rollback()
            await jobs.mark_cancelled(user_id=user_id, job_id=job_id)
        except Exception:
            await db.rollback()
            await jobs.mark_failed(user_id=user_id, job_id=job_id)


# Keep the old import name available to worker discovery code.
parse_material = process_material_job


async def recover_material_jobs(ctx: dict[str, Any]) -> int:
    """Requeue jobs whose DB state outlived Redis or a worker process."""
    async with _job_session(ctx) as db:
        jobs = JobService(db)
        user_id = ctx.get("user_id")
        return await jobs.recover_jobs(
            user_id=int(user_id) if user_id is not None else None,
            older_than=jobs._now()
            - datetime.timedelta(seconds=settings.material_job_stale_seconds),
        )
