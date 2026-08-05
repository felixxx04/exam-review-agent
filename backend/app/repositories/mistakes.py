from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Protocol, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import bind_tenant_context
from app.db.models import MistakeRecord
from app.repositories.users import UserRepository
from app.services.course_service import CourseService


class MistakeData(TypedDict):
    id: str
    user_id: str
    course_id: int
    question_id: str
    question_text: str
    question_type: str
    concept: str
    topic: str
    wrong_answer: str
    correct_answer: str
    explanation: str | None
    source_chunk_ids: list[str]
    source_material: str | None
    status: str
    attempt_count: int
    last_wrong_at: str
    correction_note: str
    mastered_at: str | None
    next_review_at: str | None
    review_history: list[dict[str, Any]]


class MistakeRepository(Protocol):
    async def create(self, values: Mapping[str, Any]) -> MistakeData: ...

    async def list_for_user(
        self,
        user_id: str,
        *,
        course_id: int | None = None,
        concept: str | None = None,
        status: str | None = None,
        topic: str | None = None,
        question_type: str | None = None,
    ) -> list[MistakeData]: ...

    async def get(self, user_id: str, mistake_id: str) -> MistakeData | None: ...

    async def update(
        self,
        user_id: str,
        mistake_id: str,
        updates: Mapping[str, Any],
    ) -> MistakeData | None: ...

    async def delete(self, user_id: str, mistake_id: str) -> bool: ...


class SqlAlchemyMistakeRepository:
    _UPDATE_FIELDS = frozenset(
        {
            "correction_note",
            "status",
            "mastered_at",
            "next_review_at",
            "review_history",
            "explanation",
            "reviewed_at",
            "review_count",
            "ease_factor",
            "attempt_count",
        }
    )
    _DATETIME_FIELDS = frozenset(
        {"last_wrong_at", "mastered_at", "next_review_at", "reviewed_at"}
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def create(self, values: Mapping[str, Any]) -> MistakeData:
        user_reference = str(values["user_id"])
        user = await self._users.get_by_subject(user_reference)
        if user is None:
            raise ValueError("Authenticated user does not exist")
        requested_course_id = values.get("course_id")
        course = await CourseService(self._session).resolve_course(
            user.id,
            int(requested_course_id) if requested_course_id is not None else None,
        )
        question_reference = str(values.get("question_id") or "")
        record = MistakeRecord(
            public_id=str(values.get("id") or question_reference),
            user_id=user.id,
            course_id=course.id,
            question_id=values.get("persisted_question_id"),
            source_question_id=question_reference,
            question_text=str(values.get("question_text") or ""),
            question_type=str(values.get("question_type") or "multiple_choice"),
            concept=str(values.get("concept") or ""),
            topic=str(values.get("topic") or ""),
            wrong_answer=str(values.get("wrong_answer") or ""),
            correct_answer=str(values.get("correct_answer") or ""),
            explanation=self._optional_string(values.get("explanation")),
            source_chunk_ids=list(values.get("source_chunk_ids") or []),
            source_material=self._optional_string(values.get("source_material")),
            status=str(values.get("status") or "unreviewed"),
            attempt_count=int(values.get("attempt_count") or 1),
            last_wrong_at=self._datetime(values.get("last_wrong_at"))
            or datetime.datetime.now(datetime.UTC),
            correction_note=str(values.get("correction_note") or ""),
            mastered_at=self._datetime(values.get("mastered_at")),
            next_review_at=self._datetime(values.get("next_review_at")),
            review_history=list(values.get("review_history") or []),
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return self._to_data(record, user_reference)

    async def list_for_user(
        self,
        user_id: str,
        *,
        course_id: int | None = None,
        concept: str | None = None,
        status: str | None = None,
        topic: str | None = None,
        question_type: str | None = None,
    ) -> list[MistakeData]:
        user = await self._users.get_by_subject(user_id)
        if user is None:
            return []

        statement = select(MistakeRecord).where(MistakeRecord.user_id == user.id)
        if course_id is not None:
            statement = statement.where(MistakeRecord.course_id == course_id)
        for column, value in (
            (MistakeRecord.concept, concept),
            (MistakeRecord.status, status),
            (MistakeRecord.topic, topic),
            (MistakeRecord.question_type, question_type),
        ):
            if value is not None:
                statement = statement.where(column == value)
        statement = statement.order_by(
            MistakeRecord.last_wrong_at.desc(), MistakeRecord.id.desc()
        )
        result = await self._session.execute(statement)
        return [self._to_data(record, user_id) for record in result.scalars().all()]

    async def get(self, user_id: str, mistake_id: str) -> MistakeData | None:
        user = await self._users.get_by_subject(user_id)
        if user is None:
            return None
        result = await self._session.execute(
            select(MistakeRecord).where(
                MistakeRecord.user_id == user.id,
                MistakeRecord.public_id == mistake_id,
            )
        )
        record = result.scalar_one_or_none()
        return self._to_data(record, user_id) if record is not None else None

    async def update(
        self,
        user_id: str,
        mistake_id: str,
        updates: Mapping[str, Any],
    ) -> MistakeData | None:
        user = await self._users.get_by_subject(user_id)
        if user is None:
            return None
        result = await self._session.execute(
            select(MistakeRecord).where(
                MistakeRecord.user_id == user.id,
                MistakeRecord.public_id == mistake_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        for field, value in updates.items():
            if field not in self._UPDATE_FIELDS:
                continue
            if field in self._DATETIME_FIELDS:
                value = self._datetime(value)
            elif field == "review_history":
                value = list(value or [])
            setattr(record, field, value)
        await self._session.commit()
        await self._session.refresh(record)
        return self._to_data(record, user_id)

    async def delete(self, user_id: str, mistake_id: str) -> bool:
        user = await self._users.get_by_subject(user_id)
        if user is None:
            return False
        result = await self._session.execute(
            select(MistakeRecord).where(
                MistakeRecord.user_id == user.id,
                MistakeRecord.public_id == mistake_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.commit()
        return True

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _datetime(value: Any) -> datetime.datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime.datetime):
            return value
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def _isoformat(value: datetime.datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.UTC)
        return value.isoformat()

    @classmethod
    def _to_data(cls, record: MistakeRecord, user_id: str) -> MistakeData:
        return MistakeData(
            id=record.public_id,
            user_id=user_id,
            course_id=record.course_id,
            question_id=record.source_question_id,
            question_text=record.question_text,
            question_type=record.question_type,
            concept=record.concept or "",
            topic=record.topic or "",
            wrong_answer=record.wrong_answer,
            correct_answer=record.correct_answer,
            explanation=record.explanation,
            source_chunk_ids=list(record.source_chunk_ids or []),
            source_material=record.source_material,
            status=record.status,
            attempt_count=record.attempt_count,
            last_wrong_at=cls._isoformat(record.last_wrong_at) or "",
            correction_note=record.correction_note,
            mastered_at=cls._isoformat(record.mastered_at),
            next_review_at=cls._isoformat(record.next_review_at),
            review_history=list(record.review_history or []),
        )


class SessionFactoryMistakeRepository:
    """Repository adapter for non-request code such as LangGraph nodes."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, values: Mapping[str, Any]) -> MistakeData:
        async with self._session_factory() as session:
            await bind_tenant_context(session, str(values["user_id"]))
            return await SqlAlchemyMistakeRepository(session).create(values)

    async def list_for_user(
        self,
        user_id: str,
        *,
        course_id: int | None = None,
        concept: str | None = None,
        status: str | None = None,
        topic: str | None = None,
        question_type: str | None = None,
    ) -> list[MistakeData]:
        async with self._session_factory() as session:
            await bind_tenant_context(session, user_id)
            return await SqlAlchemyMistakeRepository(session).list_for_user(
                user_id,
                course_id=course_id,
                concept=concept,
                status=status,
                topic=topic,
                question_type=question_type,
            )

    async def get(self, user_id: str, mistake_id: str) -> MistakeData | None:
        async with self._session_factory() as session:
            await bind_tenant_context(session, user_id)
            return await SqlAlchemyMistakeRepository(session).get(user_id, mistake_id)

    async def update(
        self,
        user_id: str,
        mistake_id: str,
        updates: Mapping[str, Any],
    ) -> MistakeData | None:
        async with self._session_factory() as session:
            await bind_tenant_context(session, user_id)
            return await SqlAlchemyMistakeRepository(session).update(
                user_id, mistake_id, updates
            )

    async def delete(self, user_id: str, mistake_id: str) -> bool:
        async with self._session_factory() as session:
            await bind_tenant_context(session, user_id)
            return await SqlAlchemyMistakeRepository(session).delete(
                user_id, mistake_id
            )
