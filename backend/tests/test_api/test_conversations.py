from __future__ import annotations

import pytest

from app.db.models import Conversation, ConversationMessage, MessageRole


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
async def test_create_conversation_starts_empty_session(client_with_db):
    response = await client_with_db.post("/api/conversations")

    assert response.status_code == 200
    data = _data(response)
    assert data["id"] > 0
    assert data["title"] == "新的复习会话"
    assert data["message_count"] == 0

    messages = await client_with_db.get(f"/api/conversations/{data['id']}/messages")
    assert _data(messages)["messages"] == []


@pytest.mark.asyncio
async def test_list_conversations_returns_recent_first(client_with_db):
    first = await client_with_db.post("/api/conversations")
    second = await client_with_db.post("/api/conversations")

    response = await client_with_db.get("/api/conversations")

    assert response.status_code == 200
    data = _data(response)
    assert data["total"] == 2
    assert [item["id"] for item in data["conversations"]] == [
        _data(second)["id"],
        _data(first)["id"],
    ]


@pytest.mark.asyncio
async def test_list_conversations_names_legacy_default_title_from_first_user_message(
    client_with_db,
    db_session,
):
    created = await client_with_db.post("/api/conversations")
    conversation_id = _data(created)["id"]
    db_session.add(
        ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content="请解释二叉树遍历的区别。",
            material_scope=None,
            message_metadata={},
        )
    )
    await db_session.commit()

    response = await client_with_db.get("/api/conversations")

    assert response.status_code == 200
    data = _data(response)
    assert data["conversations"][0]["title"] == "解释二叉树遍历的区别"


@pytest.mark.asyncio
async def test_list_conversations_repairs_legacy_ellipsized_title(
    client_with_db,
    db_session,
):
    created = await client_with_db.post("/api/conversations")
    conversation_id = _data(created)["id"]
    conversation = await db_session.get(Conversation, conversation_id)
    conversation.title = "马上要面试了，给我出一道..."
    db_session.add(
        ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content="我马上要面试了，给我出一道最可能考到的数据库事务题。",
            material_scope=None,
            message_metadata={},
        )
    )
    await db_session.commit()

    response = await client_with_db.get("/api/conversations")

    assert response.status_code == 200
    data = _data(response)
    assert data["conversations"][0]["title"] == "马上要面试了，给我出一道最可能考到的数据库事务题"


@pytest.mark.asyncio
async def test_delete_conversation_removes_messages(client_with_db, db_session):
    created = await client_with_db.post("/api/conversations")
    conversation_id = _data(created)["id"]
    db_session.add(
        ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content="要删除的历史消息",
            material_scope=["MQ.docx"],
            message_metadata={},
        )
    )
    await db_session.commit()

    response = await client_with_db.delete(f"/api/conversations/{conversation_id}")

    assert response.status_code == 200
    messages = await client_with_db.get(f"/api/conversations/{conversation_id}/messages")
    assert messages.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_messages(client_with_db):
    active = await client_with_db.get("/api/conversations/active")
    conversation_id = _data(active)["id"]

    response = await client_with_db.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    data = _data(response)
    assert data["conversation_id"] == conversation_id
    assert data["messages"] == []
