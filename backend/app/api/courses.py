from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.courses import CourseCreate, CourseListResponse, CourseUpdate
from app.services.course_service import CourseService
from app.api.dependencies import get_object_storage
from app.services.object_storage import ObjectStorage


router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("")
async def list_courses(
    ids: list[int] | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    courses = await CourseService(db).list_courses(current_user.id, ids=ids)
    return ApiResponse.ok(
        data=CourseListResponse(courses=courses, total=len(courses)),
        meta={"total": len(courses)},
    )


@router.post("")
async def create_course(
    payload: CourseCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).create_course(current_user.id, payload)
    return ApiResponse.ok(data=course)


@router.get("/{course_id}")
async def get_course(
    course_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).get_course(current_user.id, course_id)
    return ApiResponse.ok(data=course)


@router.patch("/{course_id}")
async def update_course(
    course_id: int,
    payload: CourseUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).update_course(current_user.id, course_id, payload)
    return ApiResponse.ok(data=course)


@router.delete("/{course_id}")
async def delete_course(
    course_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    await CourseService(db).delete_course(current_user.id, course_id, storage=storage)
    return ApiResponse.ok(data={"detail": "已删除"})
