from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.repositories.mistakes as mistakes_module
from app.db.models import Base, User
from app.repositories.mistakes import (
    SessionFactoryMistakeRepository,
    SqlAlchemyMistakeRepository,
)


@pytest.mark.asyncio
async def test_mistake_repository_persists_across_sessions(tmp_path):
    database_path = tmp_path / "mistakes.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as first_session:
            user = User(
                username="mistake-user",
                email=None,
                hashed_password="test-hash",
                display_name="Mistake User",
            )
            first_session.add(user)
            await first_session.commit()
            await first_session.refresh(user)
            user_id = str(user.id)
            first_repository = SqlAlchemyMistakeRepository(first_session)
            created = await first_repository.create(
                {
                    "id": "mistake-persisted",
                    "user_id": user_id,
                    "question_id": "question-external-id",
                    "question_text": "事务隔离级别是什么？",
                    "question_type": "multiple_choice",
                    "concept": "事务隔离",
                    "topic": "数据库",
                    "wrong_answer": "A",
                    "correct_answer": "B",
                    "source_chunk_ids": ["chunk-1"],
                    "status": "unreviewed",
                    "attempt_count": 1,
                }
            )

        async with session_factory() as second_session:
            second_repository = SqlAlchemyMistakeRepository(second_session)
            records = await second_repository.list_for_user(
                user_id, concept="事务隔离"
            )
            updated = await second_repository.update(
                user_id,
                "mistake-persisted",
                {"status": "corrected", "correction_note": "重新核对定义"},
            )

        assert created["id"] == "mistake-persisted"
        assert records[0]["question_id"] == "question-external-id"
        assert records[0]["source_chunk_ids"] == ["chunk-1"]
        assert updated is not None
        assert updated["status"] == "corrected"
        assert updated["correction_note"] == "重新核对定义"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_factory_repository_binds_each_tenant_operation(monkeypatch):
    bindings: list[tuple[object, str]] = []
    session = object()

    async def record_binding(bound_session, user_id):
        bindings.append((bound_session, str(user_id)))

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeRepository:
        def __init__(self, bound_session):
            assert bound_session is session

        async def create(self, values):
            return values

        async def list_for_user(self, user_id, **filters):
            return []

        async def get(self, user_id, mistake_id):
            return None

        async def update(self, user_id, mistake_id, updates):
            return None

    monkeypatch.setattr(mistakes_module, "bind_tenant_context", record_binding)
    monkeypatch.setattr(
        mistakes_module, "SqlAlchemyMistakeRepository", FakeRepository
    )
    repository = SessionFactoryMistakeRepository(lambda: SessionContext())

    await repository.create({"user_id": "11"})
    await repository.list_for_user("12")
    await repository.get("13", "mistake")
    await repository.update("14", "mistake", {})

    assert bindings == [
        (session, "11"),
        (session, "12"),
        (session, "13"),
        (session, "14"),
    ]


@pytest.mark.asyncio
async def test_session_factory_repository_supports_graph_callers(tmp_path):
    database_path = tmp_path / "graph-mistakes.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    repository = SessionFactoryMistakeRepository(session_factory)
    try:
        assert await repository.list_for_user("missing-user") == []
        assert await repository.get("missing-user", "missing") is None
        assert await repository.update("missing-user", "missing", {}) is None

        async with session_factory() as session:
            user = User(
                username="graph-user",
                email=None,
                hashed_password="test-hash",
                display_name="Graph User",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            user_id = str(user.id)

        await repository.create(
            {
                "id": "graph-mistake",
                "user_id": user_id,
                "question_id": "graph-question",
                "wrong_answer": "A",
                "correct_answer": "B",
                "concept": "事务",
                "topic": "数据库",
                "question_type": "multiple_choice",
            }
        )
        records = await repository.list_for_user(
            user_id,
            concept="事务",
            status="unreviewed",
            topic="数据库",
            question_type="multiple_choice",
        )
        found = await repository.get(user_id, "graph-mistake")
        updated = await repository.update(
            user_id,
            "graph-mistake",
            {"next_review_at": "2026-08-04T12:00:00Z", "unknown": "ignored"},
        )

        assert len(records) == 1
        assert found is not None
        assert found["question_id"] == "graph-question"
        assert updated is not None
        assert updated["next_review_at"] == "2026-08-04T12:00:00+00:00"
    finally:
        await engine.dispose()
