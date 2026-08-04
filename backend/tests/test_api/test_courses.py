from __future__ import annotations

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.models import User
from app.main import app


COURSE_PAYLOAD = {
    "name": "数据库系统",
    "description": "期末复习课程",
    "exam_date": "2026-12-20",
    "long_term_goal": "掌握事务、索引和查询优化",
    "daily_available_minutes": 90,
}


@pytest.mark.asyncio
async def test_course_crud_exposes_exam_goal_and_daily_availability(
    client_with_db: AsyncClient,
):
    created_response = await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)

    assert created_response.status_code == 200
    created = created_response.json()["data"]
    assert created["name"] == "数据库系统"
    assert created["exam_date"] == "2026-12-20"
    assert created["long_term_goal"] == "掌握事务、索引和查询优化"
    assert created["daily_available_minutes"] == 90
    assert created["is_default"] is True

    second_response = await client_with_db.post(
        "/api/courses",
        json={
            "name": "计算机网络",
            "exam_date": "2026-12-28",
            "daily_available_minutes": 45,
        },
    )
    assert second_response.status_code == 200
    second = second_response.json()["data"]
    assert second["is_default"] is False

    listed_response = await client_with_db.get("/api/courses")
    assert listed_response.status_code == 200
    listed = listed_response.json()["data"]
    assert listed["total"] == 2
    assert [course["name"] for course in listed["courses"]] == [
        "数据库系统",
        "计算机网络",
    ]

    updated_response = await client_with_db.patch(
        f"/api/courses/{second['id']}",
        json={
            "long_term_goal": "完成五套模拟题",
            "daily_available_minutes": 60,
            "is_default": True,
        },
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["data"]
    assert updated["long_term_goal"] == "完成五套模拟题"
    assert updated["daily_available_minutes"] == 60
    assert updated["is_default"] is True

    fetched_response = await client_with_db.get(f"/api/courses/{second['id']}")
    assert fetched_response.status_code == 200
    assert fetched_response.json()["data"] == updated

    deleted_response = await client_with_db.delete(f"/api/courses/{created['id']}")
    assert deleted_response.status_code == 200
    assert (
        await client_with_db.get(f"/api/courses/{created['id']}")
    ).status_code == 404


@pytest.mark.asyncio
async def test_course_input_boundaries_are_validated(client_with_db: AsyncClient):
    empty_name = await client_with_db.post(
        "/api/courses",
        json={**COURSE_PAYLOAD, "name": "   "},
    )
    invalid_minutes = await client_with_db.post(
        "/api/courses",
        json={**COURSE_PAYLOAD, "daily_available_minutes": 0},
    )
    invalid_exam_date = await client_with_db.post(
        "/api/courses",
        json={**COURSE_PAYLOAD, "exam_date": "not-a-date"},
    )

    assert empty_name.status_code == 422
    assert invalid_minutes.status_code == 422
    assert invalid_exam_date.status_code == 422


@pytest.mark.asyncio
async def test_course_names_are_unique_within_one_private_tenant(
    client_with_db: AsyncClient,
):
    assert (
        await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)
    ).status_code == 200

    duplicate = await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_course_ids_and_bulk_lists_are_scoped_to_authenticated_user(
    client_with_db: AsyncClient,
    db_session,
    authenticated_user: User,
):
    owner_course = (
        await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)
    ).json()["data"]
    other_user = User(
        username="other_course_user",
        email=None,
        hashed_password="test-password-hash",
        display_name="Other Course User",
        role="user",
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=other_user.id,
        username=other_user.username,
        role=other_user.role,
        session_id="other-session",
    )

    try:
        own_course_response = await client_with_db.post(
            "/api/courses",
            json={
                "name": "操作系统",
                "exam_date": datetime.date(2026, 12, 25).isoformat(),
                "daily_available_minutes": 30,
            },
        )
        assert own_course_response.status_code == 200
        own_course = own_course_response.json()["data"]

        guessed = await client_with_db.get(f"/api/courses/{owner_course['id']}")
        bulk = await client_with_db.get(
            "/api/courses",
            params=[("ids", owner_course["id"]), ("ids", own_course["id"])],
        )
        patched = await client_with_db.patch(
            f"/api/courses/{owner_course['id']}",
            json={"name": "越权修改"},
        )
        deleted = await client_with_db.delete(f"/api/courses/{owner_course['id']}")
        foreign_conversation = await client_with_db.post(
            "/api/conversations",
            json={"course_id": owner_course["id"]},
        )
        foreign_materials = await client_with_db.get(
            "/api/materials", params={"course_id": owner_course["id"]}
        )
        foreign_quiz = await client_with_db.post(
            "/api/quiz/generate",
            json={"topic": "越权课程", "course_id": owner_course["id"]},
        )
        foreign_memory = await client_with_db.get(
            "/api/memory/profile", params={"course_id": owner_course["id"]}
        )
        foreign_study_plan = await client_with_db.post(
            "/api/review/study-plan",
            params={"course_id": owner_course["id"]},
            json={"exam_date": "2026-12-31"},
        )

        assert guessed.status_code == 404
        assert patched.status_code == 404
        assert deleted.status_code == 404
        assert foreign_conversation.status_code == 404
        assert foreign_materials.status_code == 404
        assert foreign_quiz.status_code == 404
        assert foreign_memory.status_code == 404
        assert foreign_study_plan.status_code == 404
        assert [item["id"] for item in bulk.json()["data"]["courses"]] == [
            own_course["id"]
        ]
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=authenticated_user.id,
            username=authenticated_user.username,
            role=authenticated_user.role,
            session_id="test-session",
        )


@pytest.mark.asyncio
async def test_conversation_can_override_default_course_session_minutes(
    client_with_db: AsyncClient,
    db_session,
):
    course = (await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)).json()[
        "data"
    ]

    response = await client_with_db.post(
        "/api/conversations",
        json={"course_id": course["id"], "available_minutes_override": 25},
    )

    assert response.status_code == 200
    conversation = response.json()["data"]
    assert conversation["course_id"] == course["id"]
    assert conversation["available_minutes_override"] == 25

    from app.db import models

    persisted = await db_session.scalar(
        select(models.Conversation).where(models.Conversation.id == conversation["id"])
    )
    assert persisted is not None
    assert persisted.course_id == course["id"]
    assert persisted.available_minutes_override == 25


@pytest.mark.asyncio
async def test_course_update_can_clear_exam_fields_and_preserve_a_default(
    client_with_db: AsyncClient,
):
    first = (await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)).json()[
        "data"
    ]
    second = (
        await client_with_db.post(
            "/api/courses",
            json={"name": "软件工程", "daily_available_minutes": 40},
        )
    ).json()["data"]

    updated_response = await client_with_db.patch(
        f"/api/courses/{first['id']}",
        json={
            "name": "数据库原理",
            "description": None,
            "exam_date": None,
            "long_term_goal": None,
            "is_default": False,
        },
    )

    assert updated_response.status_code == 200
    updated = updated_response.json()["data"]
    assert updated["name"] == "数据库原理"
    assert updated["description"] is None
    assert updated["exam_date"] is None
    assert updated["long_term_goal"] is None
    assert updated["is_default"] is True

    duplicate = await client_with_db.patch(
        f"/api/courses/{second['id']}",
        json={"name": "数据库原理"},
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_legacy_client_recreates_default_after_last_course_is_deleted(
    client_with_db: AsyncClient,
):
    course = (await client_with_db.post("/api/courses", json=COURSE_PAYLOAD)).json()[
        "data"
    ]
    assert (
        await client_with_db.delete(f"/api/courses/{course['id']}")
    ).status_code == 200

    conversation_response = await client_with_db.post("/api/conversations")

    assert conversation_response.status_code == 200
    conversation = conversation_response.json()["data"]
    listed = (await client_with_db.get("/api/courses")).json()["data"]
    assert listed["total"] == 1
    assert listed["courses"][0]["name"] == "默认课程"
    assert listed["courses"][0]["is_default"] is True
    assert conversation["course_id"] == listed["courses"][0]["id"]
