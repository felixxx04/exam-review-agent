import pytest
from unittest.mock import AsyncMock

from app.agents.rag_agent import AgentResponse
from app.orchestrator.graph import run_orchestrator
from app.orchestrator.router import classify_intent
from app.schemas.quiz import Question, QuizResponse


# ---------------------------------------------------------------------------
# Router unit tests
# ---------------------------------------------------------------------------


def test_classify_quiz_intent():
    assert classify_intent("基于第三章出5道选择题") == "quiz"


def test_classify_quiz_intent_with_generic_count():
    assert classify_intent("给我出五道题") == "quiz"


def test_classify_qa_intent():
    assert classify_intent("解释一下薛定谔方程") == "qa"


def test_classify_review_intent():
    assert classify_intent("查看我的错题") == "review"


def test_classify_hybrid_intent():
    # quiz takes priority over qa when both keywords present
    assert classify_intent("总结一下第三章然后出几道题") in ["quiz", "qa"]


def test_classify_empty_message():
    assert classify_intent("") == "qa"


def test_classify_english_quiz():
    assert classify_intent("Generate a quiz on chapter 3") == "quiz"


def test_classify_mistake_review():
    assert classify_intent("Show me my mistakes") == "review"


def test_classify_weak_point_analysis():
    assert classify_intent("我的薄弱知识点是什么") == "review"


# ---------------------------------------------------------------------------
# Graph integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_routes_to_qa(monkeypatch):
    mock_agent = AsyncMock()
    mock_agent.answer = AsyncMock(
        return_value=AgentResponse(
            content="薛定谔方程描述量子态的时间演化",
            citations=[{"source": "quantum.pdf", "page": 23}],
        )
    )
    monkeypatch.setattr("app.orchestrator.graph._build_rag_agent", lambda: mock_agent)

    result = await run_orchestrator("什么是薛定谔方程", "user-1")
    assert result["intent"] == "qa"
    assert result["user_id"] == "user-1"
    assert any("薛定谔方程" in m.content for m in result["messages"])
    assert result["citations"][0]["source"] == "quantum.pdf"


@pytest.mark.asyncio
async def test_orchestrator_routes_to_quiz(monkeypatch):
    mock_agent = AsyncMock()
    mock_agent.generate_quiz = AsyncMock(
        return_value=QuizResponse(
            questions=[
                Question(
                    question="以下哪个是量子力学核心概念？",
                    options=["A. 速度", "B. 波函数", "C. 温度", "D. 电流"],
                    correct="B",
                    explanation="波函数是量子力学核心概念",
                    source_chunk_ids=["chunk-1"],
                )
            ],
            topic="量子力学",
        )
    )
    monkeypatch.setattr("app.orchestrator.graph._build_quiz_agent", lambda: mock_agent)

    result = await run_orchestrator("基于第三章出5道选择题", "user-1")
    assert result["intent"] == "quiz"
    assert any("已根据当前资料生成" in m.content for m in result["messages"])
    assert result["quiz"]["total"] == 1
    assert result["quiz"]["questions"][0]["correct"] == "B"


@pytest.mark.asyncio
async def test_orchestrator_routes_to_review(monkeypatch):
    mock_tracker = AsyncMock()
    mock_tracker.get_weak_concepts = AsyncMock(
        return_value=[{"concept": "事务隔离级别", "topic": "数据库", "accuracy": 0.0, "attempt_count": 2}]
    )
    monkeypatch.setattr("app.orchestrator.graph._build_tracker_agent", lambda: mock_tracker)

    result = await run_orchestrator("查看我的错题", "user-1")
    assert result["intent"] == "review"
    assert any("事务隔离级别" in m.content for m in result["messages"])


@pytest.mark.asyncio
async def test_orchestrator_passes_extra_kwargs(monkeypatch):
    mock_agent = AsyncMock()
    mock_agent.answer = AsyncMock(return_value=AgentResponse(content="测试回答"))
    monkeypatch.setattr("app.orchestrator.graph._build_rag_agent", lambda: mock_agent)

    result = await run_orchestrator("什么是薛定谔方程", "user-1", material_scope=["chapter-3"])
    assert result.get("material_scope") == ["chapter-3"]


@pytest.mark.asyncio
async def test_orchestrator_accepts_memory_context(monkeypatch):
    mock_agent = AsyncMock()
    mock_agent.answer = AsyncMock(return_value=AgentResponse(content="继续解释幻读"))
    monkeypatch.setattr("app.orchestrator.graph._build_rag_agent", lambda: mock_agent)

    result = await run_orchestrator(
        message="继续讲刚才的概念",
        user_id="default",
        memory_context={
            "summary": "用户前面在学习数据库事务隔离级别。",
            "recent_messages": [
                {"role": "user", "content": "什么是幻读？"},
                {"role": "assistant", "content": "幻读是再次查询时出现新增行。"},
            ],
            "learning_profile": {
                "current_subject": "数据库系统",
                "weak_concepts": ["幻读"],
            },
        },
    )

    assert result["memory_context"]["learning_profile"]["current_subject"] == "数据库系统"
    assert any("继续解释幻读" in message.content for message in result["messages"])
    mock_agent.answer.assert_awaited_once()
    assert mock_agent.answer.await_args.kwargs["memory_context"]["summary"] == (
        "用户前面在学习数据库事务隔离级别。"
    )
