"""Tests for the RAG Agent."""

from unittest.mock import AsyncMock

import pytest

from app.agents.rag_agent import AgentResponse, RAGAgent
from app.services.retrieval_service import SearchResult


@pytest.mark.asyncio
async def test_rag_agent_returns_answer_with_citations():
    """The agent should retrieve chunks, call the LLM, and return citations."""
    agent = RAGAgent(llm_service=AsyncMock(), retrieval_service=AsyncMock())

    agent.retrieval.search = AsyncMock(
        return_value=[
            SearchResult(
                text="薛定谔方程: ihbar partial_psi/partial_t = H_hat psi",
                score=0.92,
                metadata={"source": "quantum.pdf", "page": 23},
            ),
        ]
    )
    agent.llm.invoke = AsyncMock(
        return_value=(
            "薛定谔方程描述量子态随时间演化"
            "[ihbar partial_psi/partial_t = H_hat psi]"
            "【来源: quantum.pdf P.23】"
        )
    )

    result = await agent.answer("什么是薛定谔方程", user_id="test")

    assert "薛定谔" in result.content
    assert len(result.citations) >= 1
    agent.retrieval.search.assert_awaited_once()
    agent.llm.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_rag_agent_returns_empty_when_no_chunks_found():
    """When retrieval returns nothing, the agent should still respond."""
    agent = RAGAgent(llm_service=AsyncMock(), retrieval_service=AsyncMock())

    agent.retrieval.search = AsyncMock(return_value=[])
    agent.llm.invoke = AsyncMock(
        return_value="抱歉，没有找到相关资料来回答您的问题。"
    )

    result = await agent.answer("什么是暗物质", user_id="test")

    assert len(result.citations) == 0
    assert len(result.retrieved_chunks) == 0
    assert "抱歉" in result.content


@pytest.mark.asyncio
async def test_rag_agent_passes_material_scope_as_metadata_filter():
    """When material_scope is given, it should be converted to metadata_filter."""
    agent = RAGAgent(llm_service=AsyncMock(), retrieval_service=AsyncMock())

    agent.retrieval.search = AsyncMock(
        return_value=[
            SearchResult(
                text="量子力学基本概念",
                score=0.85,
                metadata={"source": "physics.pdf", "page": 5},
            ),
        ]
    )
    agent.llm.invoke = AsyncMock(return_value="量子力学是...【来源: physics.pdf P.5】")

    await agent.answer(
        "什么是量子力学",
        user_id="test",
        material_scope=["physics.pdf", "quantum.pdf"],
    )

    call_kwargs = agent.retrieval.search.call_args.kwargs
    assert call_kwargs["metadata_filter"] == {"source": {"$in": ["physics.pdf", "quantum.pdf"]}}


@pytest.mark.asyncio
async def test_rag_agent_includes_memory_context_in_prompt():
    """The prompt should carry recent memory so follow-up questions have context."""
    agent = RAGAgent(llm_service=AsyncMock(), retrieval_service=AsyncMock())

    agent.retrieval.search = AsyncMock(return_value=[])
    agent.llm.invoke = AsyncMock(return_value="幻读是事务中再次查询看到新增行。")

    await agent.answer(
        "继续解释刚才的概念",
        user_id="test",
        memory_context={
            "summary": "用户正在复习数据库事务隔离级别。",
            "recent_messages": [
                {"role": "user", "content": "什么是幻读？"},
                {"role": "assistant", "content": "幻读是再次查询出现新增行。"},
            ],
            "learning_profile": {
                "current_subject": "数据库系统",
                "weak_concepts": ["幻读"],
            },
        },
    )

    prompt = agent.llm.invoke.await_args.args[0][0]["content"]
    assert "会话记忆" in prompt
    assert "什么是幻读？" in prompt
    assert "数据库系统" in prompt


@pytest.mark.asyncio
async def test_extract_citations_finds_source_references():
    """_extract_citations should detect source mentions in the response."""
    agent = RAGAgent(llm_service=AsyncMock(), retrieval_service=AsyncMock())

    chunks = [
        SearchResult(
            text="牛顿第一定律：任何物体都保持静止或匀速直线运动状态...",
            score=0.9,
            metadata={"source": "mechanics.pdf", "page": 10},
        ),
        SearchResult(
            text="动能公式: E_k = 1/2 mv^2",
            score=0.8,
            metadata={"source": "mechanics.pdf", "page": 15},
        ),
    ]

    response = "根据牛顿第一定律【来源: mechanics.pdf P.10】，动能可以表示为E_k = 1/2 mv^2（见mechanics.pdf P.15）。"

    citations = agent._extract_citations(response, chunks)

    assert len(citations) == 2
    sources = {c["source"] for c in citations}
    assert "mechanics.pdf" in sources


@pytest.mark.asyncio
async def test_agent_response_dataclass_defaults():
    """AgentResponse should have sensible defaults for citations and retrieved_chunks."""
    resp = AgentResponse(content="test")
    assert resp.citations == []
    assert resp.retrieved_chunks == []
    assert resp.content == "test"
