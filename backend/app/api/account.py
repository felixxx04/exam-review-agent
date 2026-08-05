from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import materials as materials_api
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.database import get_db
from app.db.models import AccountDeletionJob
from app.db.vector_store import VectorStore
from app.schemas.account import (
    AccountDeletionCreatedResponse,
    AccountDeletionStatusResponse,
    QuotaResponse,
)
from app.schemas.common import ApiResponse
from app.services.account_deletion_service import (
    AccountArtifactCleaner,
    AccountDeletionService,
)
from app.services.quota_service import QuotaService


router = APIRouter(prefix="/api/account", tags=["account"])


def _cleaner() -> AccountArtifactCleaner:
    return AccountArtifactCleaner(materials_api.UPLOAD_DIR, VectorStore())


def _status_response(job: AccountDeletionJob) -> AccountDeletionStatusResponse:
    return AccountDeletionStatusResponse(
        job_id=job.public_id,
        status=job.status,
        attempt_count=job.attempt_count,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


@router.get("/quota")
async def get_quota(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    usage = await QuotaService(db).get_usage(current_user.id)
    return ApiResponse.ok(data=QuotaResponse.model_validate(usage))


@router.post("/deletion", status_code=status.HTTP_202_ACCEPTED)
async def request_account_deletion(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await AccountDeletionService(db, _cleaner()).request(current_user.id)
    return ApiResponse.ok(
        data=AccountDeletionCreatedResponse(
            job_id=result.job.public_id,
            status=result.job.status,
            status_token=result.status_token,
            attempt_count=result.job.attempt_count,
            error_code=result.job.error_code,
            error_message=result.job.error_message,
        )
    )


@router.get("/deletions/{job_id}")
async def get_account_deletion(
    job_id: str,
    status_token: str = Header(default="", alias="X-Deletion-Status-Token"),
    db: AsyncSession = Depends(get_db),
):
    job = await AccountDeletionService(db, _cleaner()).get_status(job_id, status_token)
    return ApiResponse.ok(data=_status_response(job))


@router.post("/deletions/{job_id}/retry")
async def retry_account_deletion(
    job_id: str,
    status_token: str = Header(default="", alias="X-Deletion-Status-Token"),
    db: AsyncSession = Depends(get_db),
):
    job = await AccountDeletionService(db, _cleaner()).retry(job_id, status_token)
    return ApiResponse.ok(data=_status_response(job))
