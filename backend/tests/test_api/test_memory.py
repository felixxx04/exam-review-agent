from __future__ import annotations

import pytest

from app.services.memory_service import MemoryService


def _data(response):
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.asyncio
async def test_get_memory_profile(client_with_db):
    response = await client_with_db.get("/api/memory/profile")

    assert response.status_code == 200
    data = _data(response)
    assert data["weak_concepts"] == []
    assert data["frequent_questions"] == []
    assert data["active_materials"] == []
    assert data["preferences"] == {}


@pytest.mark.asyncio
async def test_memory_profiles_are_independent_per_course(
    client_with_db, db_session, authenticated_user
):
    first = (
        await client_with_db.post(
            "/api/courses", json={"name": "数据库", "daily_available_minutes": 60}
        )
    ).json()["data"]
    second = (
        await client_with_db.post(
            "/api/courses", json={"name": "网络", "daily_available_minutes": 45}
        )
    ).json()["data"]

    service = MemoryService(db_session)
    second_profile = await service.get_or_create_learning_profile(
        authenticated_user.id, second["id"]
    )
    second_profile.current_subject = "TCP 拥塞控制"
    await db_session.commit()

    first_response = await client_with_db.get(
        "/api/memory/profile", params={"course_id": first["id"]}
    )
    second_response = await client_with_db.get(
        "/api/memory/profile", params={"course_id": second["id"]}
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["data"]["course_id"] == first["id"]
    assert first_response.json()["data"]["current_subject"] is None
    assert second_response.json()["data"]["course_id"] == second["id"]
    assert second_response.json()["data"]["current_subject"] == "TCP 拥塞控制"
