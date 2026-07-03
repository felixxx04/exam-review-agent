from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.db.models import ConversationMessage


class TestChatSSE:

    @pytest.mark.asyncio
    async def test_chat_returns_sse_stream(self, client_with_db, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="测试回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client_with_db.post(
            "/api/chat",
            json={"message": "什么是量子力学"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_chat_sends_data_events(self, client_with_db, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="测试回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client_with_db.post(
            "/api/chat",
            json={"message": "解释薛定谔方程"},
        )
        body = response.text
        assert "data:" in body

    @pytest.mark.asyncio
    async def test_chat_empty_message(self, client_with_db, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="空消息回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client_with_db.post(
            "/api/chat",
            json={"message": ""},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_with_material_scope(self, client_with_db, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {
                "messages": [AIMessage(content="带资料范围的回复")],
                "citations": [{"source": "quantum.pdf", "page": 1}],
            }

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client_with_db.post(
            "/api/chat",
            json={
                "message": "量子力学基础",
                "material_scope": ["quantum.pdf"],
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_persists_user_and_assistant_messages(
        self,
        client_with_db,
        db_session,
        monkeypatch,
    ):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="可以，继续解释幻读。")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)

        response = await client_with_db.post(
            "/api/chat",
            json={
                "message": "刚才那个概念再举个例子",
                "material_scope": ["database.pdf"],
            },
        )

        assert response.status_code == 200
        rows = (
            await db_session.execute(
                select(ConversationMessage).order_by(ConversationMessage.created_at.asc())
            )
        ).scalars().all()
        roles = [
            row.role.value if hasattr(row.role, "value") else str(row.role)
            for row in rows
        ]
        assert roles == ["user", "assistant"]
        assert rows[0].content == "刚才那个概念再举个例子"
        assert rows[1].content == "可以，继续解释幻读。"

    @pytest.mark.asyncio
    async def test_chat_stream_includes_conversation_id(
        self,
        client_with_db,
        monkeypatch,
    ):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="测试回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)

        response = await client_with_db.post("/api/chat", json={"message": "继续"})

        assert response.status_code == 200
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert any(
            event["event"] == "conversation" and event["data"]["id"] > 0
            for event in events
        )
