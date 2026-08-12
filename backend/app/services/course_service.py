from __future__ import annotations

from collections.abc import Sequence
import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.db.models import (
    Course,
    Exam,
    Material,
    MaterialChunk,
    ProcessingStatus,
    StorageStatus,
    StudyAvailability,
    User,
)
from app.schemas.courses import CourseCreate, CourseResponse, CourseUpdate
from app.services.material_storage_cleanup import (
    delete_legacy_material,
    delete_material_chunks,
    is_processing_lease_active,
)
from app.services.object_storage import ObjectStorage, ObjectStorageError
from app.services.quota_service import QuotaService


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

    async def delete_course(
        self, user_id: int, course_id: int, *, storage: ObjectStorage
    ) -> None:
        # This is the same user-row serialization boundary used by uploads and
        # account deletion. Persist cleanup intent before making remote calls.
        await QuotaService(self.db).lock_upload(user_id)
        course = await self.require_owned_course(user_id, course_id, lock=True)
        materials = await self._materials_pending_course_cleanup(
            user_id=user_id, course_id=course.id
        )
        if any(
            material.storage_status == StorageStatus.RESERVED
            or material.object_write_uncertain
            or (
                material.processing_status == ProcessingStatus.PROCESSING
                and is_processing_lease_active(material.processing_lease_expires_at)
            )
            for material in materials
        ):
            # A timed-out object write or active index may still create an
            # external artifact. Keep its PostgreSQL cleanup metadata intact
            # until recovery or the active upload reaches a terminal state.
            await self.db.rollback()
            raise ObjectStorageError(
                "Material cleanup is pending", "OBJECT_STORAGE_UNAVAILABLE"
            )
        if materials:
            for material in materials:
                material.storage_status = StorageStatus.DELETING
                material.processing_lease_id = None
                material.processing_lease_expires_at = None
                material.error_message = "Material cleanup is pending"
            await self.db.commit()

        try:
            # The earlier commit makes a crash recoverable; reacquire the lock
            # so uploads and account deletion remain serialized while artifacts
            # are deleted from their external stores.
            await QuotaService(self.db).lock_upload(user_id)
            course = await self.require_owned_course(user_id, course_id, lock=True)
            materials = await self._materials_pending_course_cleanup(
                user_id=user_id, course_id=course.id
            )
            for material in materials:
                await self._delete_material_object(material, storage=storage)
                await delete_material_chunks(self.db, material=material)
                material.storage_status = StorageStatus.DELETED
                material.error_message = None

            await self._delete_course_collection(user_id=user_id, course_id=course.id)
            await self._delete_course_material_metadata(
                user_id=user_id, course_id=course.id
            )
            await self._delete_course_record(course, user_id=user_id)
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise

    async def _materials_pending_course_cleanup(
        self, *, user_id: int, course_id: int
    ) -> list[Material]:
        result = await self.db.execute(
            select(Material)
            .where(
                Material.user_id == user_id,
                Material.course_id == course_id,
                Material.storage_status != StorageStatus.DELETED,
            )
            .order_by(Material.id)
            .with_for_update()
        )
        return list(result.scalars().all())

    async def _delete_course_material_metadata(
        self, *, user_id: int, course_id: int
    ) -> None:
        # PostgreSQL cascades these rows too, but deleting them explicitly keeps
        # the cleanup contract identical in local SQLite tests and avoids relying
        # on a database cascade after remote artifact deletion has succeeded.
        await self.db.execute(
            delete(MaterialChunk).where(
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == course_id,
            )
        )
        await self.db.execute(
            delete(Material).where(
                Material.user_id == user_id,
                Material.course_id == course_id,
            )
        )

    @staticmethod
    async def _delete_material_object(
        material: Material, *, storage: ObjectStorage
    ) -> None:
        if material.storage_backend == "legacy_local":
            await delete_legacy_material(material)
            return
        if material.object_key is None:
            raise ObjectStorageError(
                "Material storage metadata is unavailable", "OBJECT_STORAGE_UNAVAILABLE"
            )
        await storage.delete_object(
            key=material.object_key,
            version_id=material.object_version_id,
        )

    @staticmethod
    async def _delete_course_collection(*, user_id: int, course_id: int) -> None:
        from app.services.retrieval_service import RetrievalService

        await RetrievalService().delete_collection(
            user_id=str(user_id), course_id=course_id
        )

    async def _delete_course_record(self, course: Course, *, user_id: int) -> None:
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

    async def require_owned_course(
        self, user_id: int, course_id: int, *, lock: bool = False
    ) -> Course:
        statement = (
            select(Course)
            .where(Course.id == course_id, Course.user_id == user_id)
            .options(
                selectinload(Course.exam),
                selectinload(Course.study_availability),
            )
        )
        if lock:
            statement = statement.with_for_update()
        result = await self.db.execute(statement)
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
