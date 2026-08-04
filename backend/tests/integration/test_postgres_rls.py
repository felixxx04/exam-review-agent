from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import bind_tenant_context
from app.db.models import (
    AnswerRecord,
    Conversation,
    Course,
    MistakeRecord,
    Question,
    QuizSession,
    User,
)
from app.repositories.mistakes import SessionFactoryMistakeRepository


POSTGRES_INTEGRATION_URL = os.getenv("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_URL,
    reason="POSTGRES_INTEGRATION_URL is required for PostgreSQL RLS tests",
)


@pytest.mark.asyncio
async def test_postgres_rls_survives_commits_and_session_factory_calls():
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user_ids: list[int] = []
    course_id: int | None = None

    try:
        async with session_factory() as session:
            users = [
                User(
                    username=f"rls_owner_{suffix}",
                    email=None,
                    hashed_password="integration-test-hash",
                    display_name="RLS Owner",
                ),
                User(
                    username=f"rls_other_{suffix}",
                    email=None,
                    hashed_password="integration-test-hash",
                    display_name="RLS Other",
                ),
            ]
            session.add_all(users)
            await session.commit()
            user_ids = [user.id for user in users]

        owner_id, other_id = user_ids
        async with session_factory() as owner_session:
            await bind_tenant_context(owner_session, owner_id)
            course = Course(
                user_id=owner_id,
                name=f"RLS course {suffix}",
                is_default=True,
            )
            owner_session.add(course)
            await owner_session.commit()
            await owner_session.refresh(course)
            course_id = course.id
            conversation = Conversation(
                user_id=owner_id,
                course_id=course_id,
                title="RLS integration",
            )
            owner_session.add(conversation)
            await owner_session.commit()
            await owner_session.refresh(conversation)
            conversation_id = conversation.id
            await owner_session.commit()

            visible = await owner_session.scalars(select(Conversation))
            assert [item.id for item in visible] == [conversation_id]
            visible_courses = await owner_session.scalars(select(Course))
            assert [item.id for item in visible_courses] == [course_id]

        async with session_factory() as other_session:
            await bind_tenant_context(other_session, other_id)
            assert list(await other_session.scalars(select(Conversation))) == []
            assert list(await other_session.scalars(select(Course))) == []
            other_session.add(
                Conversation(
                    user_id=owner_id,
                    course_id=course_id,
                    title="Cross-tenant write",
                )
            )
            with pytest.raises(DBAPIError):
                await other_session.commit()
            await other_session.rollback()

        async with session_factory() as unbound_session:
            assert list(await unbound_session.scalars(select(Conversation))) == []
            unbound_session.add(
                Conversation(
                    user_id=owner_id,
                    course_id=course_id,
                    title="Unbound tenant write",
                )
            )
            with pytest.raises(DBAPIError):
                await unbound_session.commit()
            await unbound_session.rollback()

        repository = SessionFactoryMistakeRepository(session_factory)
        created = await repository.create(
            {
                "id": f"rls-mistake-{suffix}",
                "user_id": str(owner_id),
                "course_id": course_id,
                "question_id": f"rls-question-{suffix}",
                "wrong_answer": "A",
                "correct_answer": "B",
                "concept": "RLS",
                "topic": "PostgreSQL",
            }
        )
        assert created["user_id"] == str(owner_id)
        assert created["course_id"] == course_id
        assert (
            len(await repository.list_for_user(str(owner_id), course_id=course_id)) == 1
        )
        assert await repository.list_for_user(str(other_id)) == []
        updated = await repository.update(
            str(owner_id),
            created["id"],
            {"status": "corrected"},
        )
        assert updated is not None
        assert updated["status"] == "corrected"
    finally:
        for user_id in user_ids:
            async with session_factory() as session:
                await bind_tenant_context(session, user_id)
                await session.execute(
                    delete(MistakeRecord).where(MistakeRecord.user_id == user_id)
                )
                await session.execute(
                    delete(Conversation).where(Conversation.user_id == user_id)
                )
                await session.execute(delete(Course).where(Course.user_id == user_id))
                await session.commit()
        if user_ids:
            async with session_factory() as session:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_course_children_are_private_and_foreign_keys_are_scoped():
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user_ids: list[int] = []

    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname IN "
                    "('conversation_messages', 'material_chunks', 'questions')"
                )
            )
            rls_state = {
                name: (enabled, forced) for name, enabled, forced in rows.all()
            }
        assert rls_state == {
            "conversation_messages": (True, True),
            "material_chunks": (True, True),
            "questions": (True, True),
        }

        async with session_factory() as session:
            users = [
                User(
                    username=f"rls_child_owner_{suffix}",
                    hashed_password="integration-test-hash",
                    display_name="RLS Child Owner",
                ),
                User(
                    username=f"rls_child_other_{suffix}",
                    hashed_password="integration-test-hash",
                    display_name="RLS Child Other",
                ),
            ]
            session.add_all(users)
            await session.commit()
            user_ids = [user.id for user in users]

        owner_id, other_id = user_ids
        resources: dict[int, tuple[int, int, int]] = {}
        for user_id in user_ids:
            async with session_factory() as session:
                await bind_tenant_context(session, user_id)
                course = Course(
                    user_id=user_id,
                    name=f"Scoped course {user_id} {suffix}",
                    is_default=True,
                )
                session.add(course)
                await session.flush()
                quiz = QuizSession(user_id=user_id, course_id=course.id)
                session.add(quiz)
                await session.flush()
                question = Question(
                    user_id=user_id,
                    course_id=course.id,
                    quiz_session_id=quiz.id,
                    question_text="Only the owner may read this answer",
                    question_type="multiple_choice",
                    correct_answer="B",
                )
                session.add(question)
                await session.commit()
                resources[user_id] = (course.id, quiz.id, question.id)

        owner_course_id, owner_quiz_id, owner_question_id = resources[owner_id]
        other_course_id, other_quiz_id, other_question_id = resources[other_id]

        async with session_factory() as other_session:
            await bind_tenant_context(other_session, other_id)
            visible_questions = list(await other_session.scalars(select(Question)))
            assert [question.id for question in visible_questions] == [
                other_question_id
            ]

            other_session.add(
                AnswerRecord(
                    user_id=other_id,
                    course_id=other_course_id,
                    quiz_session_id=other_quiz_id,
                    question_id=owner_question_id,
                    student_answer="A",
                )
            )
            with pytest.raises(DBAPIError):
                await other_session.commit()
            await other_session.rollback()

            other_session.add(
                AnswerRecord(
                    user_id=other_id,
                    course_id=other_course_id,
                    quiz_session_id=owner_quiz_id,
                    question_id=other_question_id,
                    student_answer="A",
                )
            )
            with pytest.raises(DBAPIError):
                await other_session.commit()
            await other_session.rollback()

            other_session.add(
                MistakeRecord(
                    public_id=f"cross-question-{suffix}",
                    user_id=other_id,
                    course_id=other_course_id,
                    question_id=owner_question_id,
                    source_question_id="cross-question",
                    wrong_answer="A",
                    correct_answer="B",
                )
            )
            with pytest.raises(DBAPIError):
                await other_session.commit()
            await other_session.rollback()

        async with session_factory() as owner_session:
            await bind_tenant_context(owner_session, owner_id)
            owner_session.add(
                Course(
                    user_id=owner_id,
                    name=f"Second default {suffix}",
                    is_default=True,
                )
            )
            with pytest.raises(DBAPIError):
                await owner_session.commit()
            await owner_session.rollback()
    finally:
        for user_id in user_ids:
            async with session_factory() as session:
                await bind_tenant_context(session, user_id)
                await session.execute(delete(Course).where(Course.user_id == user_id))
                await session.commit()
        if user_ids:
            async with session_factory() as session:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
        await engine.dispose()
