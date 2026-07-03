from __future__ import annotations

import pytest


def _data(response):
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.asyncio
async def test_get_active_conversation(client_with_db):
    response = await client_with_db.get("/api/conversations/active")

    assert response.status_code == 200
    data = _data(response)
    assert data["id"] > 0
    assert data["title"] == "默认复习会话"
    assert data["message_count"] == 0


@pytest.mark.asyncio
async def test_get_conversation_messages(client_with_db):
    active = await client_with_db.get("/api/conversations/active")
    conversation_id = _data(active)["id"]

    response = await client_with_db.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    data = _data(response)
    assert data["conversation_id"] == conversation_id
    assert data["messages"] == []
