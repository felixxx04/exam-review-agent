from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.database import get_db
from app.db.models import LearningProfile
from app.schemas.common import ApiResponse
from app.schemas.memory import LearningProfileResponse
from app.services.course_service import CourseService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/profile")
async def get_memory_profile(
    course_id: int | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).resolve_course(current_user.id, course_id)
    service = MemoryService(db)
    profile = await service.get_or_create_learning_profile(current_user.id, course.id)
    return ApiResponse.ok(data=LearningProfileResponse.model_validate(profile))


@router.delete("/profile")
async def delete_memory_profile(
    course_id: int | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).resolve_course(current_user.id, course_id)
    result = await db.execute(
        select(LearningProfile).where(
            LearningProfile.user_id == current_user.id,
            LearningProfile.course_id == course.id,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Learning profile not found")
    await db.delete(profile)
    await db.commit()
    return ApiResponse.ok(data={"detail": "已删除"})
