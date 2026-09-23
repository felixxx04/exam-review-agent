from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_job_service
from app.core.auth import AuthenticatedUser, require_admin
from app.db.database import get_db
from app.db.models import MaterialJobStatus
from app.schemas.common import ApiResponse
from app.schemas.material_jobs import MaterialJobPriorityRequest, MaterialJobResponse
from app.services.job_service import JobService


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/material-jobs")
async def list_material_jobs(
    status: MaterialJobStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    _current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    jobs: JobService = Depends(get_job_service),
):
    service = jobs if isinstance(jobs, JobService) else JobService(db)
    result = await service.list_jobs_for_admin(status=status, limit=limit)
    data = [MaterialJobResponse.model_validate(job) for job in result]
    return ApiResponse.ok(data=data, meta={"total": len(data)})


@router.patch("/material-jobs/{job_id}/priority")
async def set_material_job_priority(
    job_id: str,
    payload: MaterialJobPriorityRequest,
    _current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    jobs: JobService = Depends(get_job_service),
):
    service = jobs if isinstance(jobs, JobService) else JobService(db)
    job = await service.set_priority_for_admin(
        job_id=job_id,
        priority=payload.priority,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse.ok(data=MaterialJobResponse.model_validate(job))


@router.post("/material-jobs/{job_id}/retry")
async def retry_material_job(
    job_id: str,
    _current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    jobs: JobService = Depends(get_job_service),
):
    service = jobs if isinstance(jobs, JobService) else JobService(db)
    job = await service.retry_job_for_admin(job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse.ok(data=MaterialJobResponse.model_validate(job))
