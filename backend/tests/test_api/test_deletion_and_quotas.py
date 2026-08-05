from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.api import materials as materials_api
from app.db.models import (
    Course,
    LearningProfile,
    Material,
    QuizSession,
    User,
)
from app.repositories.mistakes import SqlAlchemyMistakeRepository


async def _course(db_session, user_id: int, name: str = "Task 1.4") -> Course:
    course = Course(user_id=user_id, name=name, is_default=True)
    db_session.add(course)
    await db_session.commit()
    await db_session.refresh(course)
    return course


@pytest.mark.asyncio
async def test_quiz_mistake_and_memory_deletion_are_private(
    client_with_db, db_session, authenticated_user
):
    course = await _course(db_session, authenticated_user.id)
    quiz = QuizSession(user_id=authenticated_user.id, course_id=course.id)
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)

    repository = SqlAlchemyMistakeRepository(db_session)
    mistake = await repository.create(
        {
            "id": "delete-me",
            "user_id": str(authenticated_user.id),
            "course_id": course.id,
            "question_id": "source-question",
            "wrong_answer": "A",
            "correct_answer": "B",
        }
    )
    profile = LearningProfile(user_id=authenticated_user.id, course_id=course.id)
    db_session.add(profile)
    await db_session.commit()

    other = User(
        username="deletion_other",
        hashed_password="hash",
        display_name="Other",
    )
    db_session.add(other)
    await db_session.flush()
    other_course = Course(user_id=other.id, name="Other", is_default=True)
    db_session.add(other_course)
    await db_session.flush()
    other_quiz = QuizSession(user_id=other.id, course_id=other_course.id)
    db_session.add(other_quiz)
    await db_session.commit()

    foreign = await client_with_db.delete(f"/api/quiz/{other_quiz.id}")
    deleted_quiz = await client_with_db.delete(f"/api/quiz/{quiz.id}")
    deleted_mistake = await client_with_db.delete(
        f"/api/review/mistakes/{mistake['id']}"
    )
    deleted_memory = await client_with_db.delete(
        "/api/memory/profile", params={"course_id": course.id}
    )

    assert foreign.status_code == 404
    assert deleted_quiz.status_code == 200
    assert deleted_mistake.status_code == 200
    assert deleted_memory.status_code == 200
    assert await db_session.get(QuizSession, quiz.id) is None
    assert await repository.get(str(authenticated_user.id), mistake["id"]) is None
    assert (
        await db_session.scalar(
            select(LearningProfile).where(LearningProfile.id == profile.id)
        )
        is None
    )
    assert await db_session.get(QuizSession, other_quiz.id) is not None


@pytest.mark.asyncio
async def test_upload_quota_reports_usage_and_rejects_count_or_storage_overflow(
    client_with_db, db_session, authenticated_user, tmp_path, monkeypatch
):
    monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)
    course = await _course(db_session, authenticated_user.id)
    authenticated_user.file_limit = 1
    authenticated_user.storage_limit_bytes = 10
    existing = Material(
        user_id=authenticated_user.id,
        course_id=course.id,
        filename="existing.pdf",
        original_filename="existing.pdf",
        file_type="pdf",
        file_size=5,
    )
    db_session.add(existing)
    await db_session.commit()

    usage = await client_with_db.get("/api/account/quota")
    count_rejected = await client_with_db.post(
        "/api/materials",
        params={"course_id": course.id},
        files={"file": ("count.pdf", b"x", "application/pdf")},
    )

    authenticated_user.file_limit = 10
    await db_session.commit()
    storage_rejected = await client_with_db.post(
        "/api/materials",
        params={"course_id": course.id},
        files={"file": ("storage.pdf", b"123456", "application/pdf")},
    )

    assert usage.status_code == 200
    assert usage.json()["data"] == {
        "file_limit": 1,
        "files_used": 1,
        "storage_limit_bytes": 10,
        "storage_used_bytes": 5,
    }
    for response in (count_rejected, storage_rejected):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert list(Path(tmp_path).iterdir()) == []


@pytest.mark.asyncio
async def test_admin_can_override_user_quotas(
    client_with_db, db_session, authenticated_user
):
    authenticated_user.role = "admin"
    target = User(
        username="quota_target",
        hashed_password="hash",
        display_name="Quota Target",
    )
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    response = await client_with_db.patch(
        f"/api/auth/users/{target.id}",
        json={"file_limit": 12, "storage_limit_bytes": 34_000_000},
    )

    assert response.status_code == 200
    assert response.json()["data"]["file_limit"] == 12
    assert response.json()["data"]["storage_limit_bytes"] == 34_000_000
    await db_session.refresh(target)
    assert target.file_limit == 12
    assert target.storage_limit_bytes == 34_000_000
