from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage


class TestChatSSE:

    @pytest.mark.asyncio
    async def test_chat_returns_sse_stream(self, client, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="测试回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client.post(
            "/api/chat",
            json={"message": "什么是量子力学"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_chat_sends_data_events(self, client, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="测试回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client.post(
            "/api/chat",
            json={"message": "解释薛定谔方程"},
        )
        body = response.text
        assert "data:" in body

    @pytest.mark.asyncio
    async def test_chat_empty_message(self, client, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {"messages": [AIMessage(content="空消息回复")]}

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client.post(
            "/api/chat",
            json={"message": ""},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_with_material_scope(self, client, monkeypatch):
        async def fake_run_orchestrator(*args, **kwargs):
            return {
                "messages": [AIMessage(content="带资料范围的回复")],
                "citations": [{"source": "quantum.pdf", "page": 1}],
            }

        monkeypatch.setattr("app.api.chat.run_orchestrator", fake_run_orchestrator)
        response = await client.post(
            "/api/chat",
            json={
                "message": "量子力学基础",
                "material_scope": ["quantum.pdf"],
            },
        )
        assert response.status_code == 200
