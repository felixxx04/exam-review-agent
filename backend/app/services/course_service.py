from __future__ import annotations

from collections.abc import Sequence
import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.db.models import Course, Exam, StudyAvailability, User
from app.schemas.courses import CourseCreate, CourseResponse, CourseUpdate


DEFAULT_COURSE_NAME = "默认课程"
DEFAULT_DAILY_AVAILABLE_MINUTES = 60


class CourseService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_courses(
        self, user_id: int, *, ids: Sequence[int] | None = None
    ) -> list[CourseResponse]:
        statement = (
            select(Course)
            .where(Course.user_id == user_id)
            .options(
                selectinload(Course.exam),
                selectinload(Course.study_availability),
            )
            .order_by(Course.created_at.asc(), Course.id.asc())
        )
        if ids is not None:
            statement = statement.where(Course.id.in_(ids))
        result = await self.db.execute(statement)
        return [self._to_response(course) for course in result.scalars().all()]

    async def get_course(self, user_id: int, course_id: int) -> CourseResponse:
        return self._to_response(await self.require_owned_course(user_id, course_id))

    async def create_course(
        self, user_id: int, payload: CourseCreate
    ) -> CourseResponse:
        await self._lock_user(user_id)
        await self._ensure_name_available(user_id, payload.name)
        existing_id = await self.db.scalar(
            select(Course.id).where(Course.user_id == user_id).limit(1)
        )
        course = Course(
            user_id=user_id,
            name=payload.name,
            description=payload.description,
            is_default=existing_id is None,
        )
        self.db.add(course)
        await self.db.flush()
        self.db.add_all(
            [
                Exam(
                    user_id=user_id,
                    course_id=course.id,
                    exam_date=payload.exam_date,
                    long_term_goal=payload.long_term_goal,
                ),
                StudyAvailability(
                    user_id=user_id,
                    course_id=course.id,
                    daily_available_minutes=payload.daily_available_minutes,
                ),
            ]
        )
        await self.db.commit()
        return await self.get_course(user_id, course.id)

    async def update_course(
        self, user_id: int, course_id: int, payload: CourseUpdate
    ) -> CourseResponse:
        await self._lock_user(user_id)
        course = await self.require_owned_course(user_id, course_id)
        fields = payload.model_fields_set
        if (
            "name" in fields
            and payload.name is not None
            and payload.name != course.name
        ):
            await self._ensure_name_available(
                user_id, payload.name, excluding_course_id=course.id
            )
            course.name = payload.name
        if "description" in fields:
            course.description = payload.description

        if course.exam is None:
            course.exam = Exam(user_id=user_id, course_id=course.id)
        if "exam_date" in fields:
            course.exam.exam_date = payload.exam_date
        if "long_term_goal" in fields:
            course.exam.long_term_goal = payload.long_term_goal

        if course.study_availability is None:
            course.study_availability = StudyAvailability(
                user_id=user_id,
                course_id=course.id,
                daily_available_minutes=DEFAULT_DAILY_AVAILABLE_MINUTES,
            )
        if (
            "daily_available_minutes" in fields
            and payload.daily_available_minutes is not None
        ):
            course.study_availability.daily_available_minutes = (
                payload.daily_available_minutes
            )

        if "is_default" in fields and payload.is_default is True:
            await self.db.execute(
                update(Course)
                .where(Course.user_id == user_id, Course.id != course.id)
                .values(is_default=False)
            )
            course.is_default = True
        elif (
            "is_default" in fields and payload.is_default is False and course.is_default
        ):
            replacement = await self.db.scalar(
                select(Course)
                .where(Course.user_id == user_id, Course.id != course.id)
                .order_by(Course.created_at.asc(), Course.id.asc())
                .limit(1)
            )
            if replacement is not None:
                course.is_default = False
                await self.db.flush()
                replacement.is_default = True

        await self.db.commit()
        return await self.get_course(user_id, course.id)

    async def delete_course(self, user_id: int, course_id: int) -> None:
        await self._lock_user(user_id)
        course = await self.require_owned_course(user_id, course_id)
        was_default = course.is_default
        await self.db.delete(course)
        await self.db.flush()
        if was_default:
            replacement = await self.db.scalar(
                select(Course)
                .where(Course.user_id == user_id)
                .order_by(Course.created_at.asc(), Course.id.asc())
                .limit(1)
            )
            if replacement is not None:
                replacement.is_default = True
        await self.db.commit()

    async def require_owned_course(self, user_id: int, course_id: int) -> Course:
        result = await self.db.execute(
            select(Course)
            .where(Course.id == course_id, Course.user_id == user_id)
            .options(
                selectinload(Course.exam),
                selectinload(Course.study_availability),
            )
        )
        course = result.scalar_one_or_none()
        if course is None:
            raise AppException("课程不存在", "NOT_FOUND")
        return course

    async def resolve_course(self, user_id: int, course_id: int | None) -> Course:
        if course_id is not None:
            return await self.require_owned_course(user_id, course_id)

        await self._lock_user(user_id)
        result = await self.db.execute(
            select(Course)
            .where(Course.user_id == user_id)
            .options(
                selectinload(Course.exam),
                selectinload(Course.study_availability),
            )
            .order_by(
                Course.is_default.desc(), Course.created_at.asc(), Course.id.asc()
            )
            .limit(1)
        )
        course = result.scalar_one_or_none()
        if course is not None:
            return course

        created = await self.create_course(
            user_id,
            CourseCreate(
                name=DEFAULT_COURSE_NAME,
                daily_available_minutes=DEFAULT_DAILY_AVAILABLE_MINUTES,
            ),
        )
        return await self.require_owned_course(user_id, created.id)

    async def _ensure_name_available(
        self,
        user_id: int,
        name: str,
        *,
        excluding_course_id: int | None = None,
    ) -> None:
        statement = select(Course.id).where(
            Course.user_id == user_id, Course.name == name
        )
        if excluding_course_id is not None:
            statement = statement.where(Course.id != excluding_course_id)
        if await self.db.scalar(statement) is not None:
            raise AppException("课程名称已存在", "CONFLICT")

    async def _lock_user(self, user_id: int) -> None:
        await self.db.execute(
            select(User.id).where(User.id == user_id).with_for_update()
        )

    @staticmethod
    def _to_response(course: Course) -> CourseResponse:
        exam = course.exam
        availability = course.study_availability
        return CourseResponse(
            id=course.id,
            name=course.name,
            description=course.description,
            exam_date=exam.exam_date if exam is not None else None,
            long_term_goal=exam.long_term_goal if exam is not None else None,
            daily_available_minutes=(
                availability.daily_available_minutes
                if availability is not None
                else DEFAULT_DAILY_AVAILABLE_MINUTES
            ),
            is_default=course.is_default,
            created_at=CourseService._as_utc(course.created_at),
            updated_at=CourseService._as_utc(course.updated_at),
        )

    @staticmethod
    def _as_utc(value: datetime.datetime) -> datetime.datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.UTC)
        return value.astimezone(datetime.UTC)
