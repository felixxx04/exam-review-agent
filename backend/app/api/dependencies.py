from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories.mistakes import MistakeRepository, SqlAlchemyMistakeRepository
from app.services.object_storage import ObjectStorage, S3ObjectStorage
from app.services.job_service import JobService
from app.core.config import settings


def get_mistake_repository(
    db: AsyncSession = Depends(get_db),
) -> MistakeRepository:
    return SqlAlchemyMistakeRepository(db)


def get_object_storage() -> ObjectStorage:
    """Build the S3-compatible storage adapter for one request or background task."""
    return S3ObjectStorage(
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        public_endpoint_url=settings.s3_public_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        connect_timeout_seconds=settings.s3_connect_timeout_seconds,
        read_timeout_seconds=settings.s3_read_timeout_seconds,
    )


def get_job_service(
    db: AsyncSession = Depends(get_db),
) -> JobService:
    return JobService(db)
