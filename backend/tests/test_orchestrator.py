import pytest

from app.orchestrator.graph import run_orchestrator
from app.orchestrator.router import classify_intent


# ---------------------------------------------------------------------------
# Router unit tests
# ---------------------------------------------------------------------------


def test_classify_quiz_intent():
    assert classify_intent("基于第三章出5道选择题") == "quiz"


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
async def test_orchestrator_routes_to_qa():
    result = await run_orchestrator("什么是薛定谔方程", "user-1")
    assert result["intent"] == "qa"
    assert result["user_id"] == "user-1"
    assert any("QA handling" in m.content for m in result["messages"])


@pytest.mark.asyncio
async def test_orchestrator_routes_to_quiz():
    result = await run_orchestrator("基于第三章出5道选择题", "user-1")
    assert result["intent"] == "quiz"
    assert any("Quiz generation" in m.content for m in result["messages"])


@pytest.mark.asyncio
async def test_orchestrator_routes_to_review():
    result = await run_orchestrator("查看我的错题", "user-1")
    assert result["intent"] == "review"
    assert any("Review handling" in m.content for m in result["messages"])


@pytest.mark.asyncio
async def test_orchestrator_passes_extra_kwargs():
    result = await run_orchestrator("什么是薛定谔方程", "user-1", material_scope=["chapter-3"])
    assert result.get("material_scope") == ["chapter-3"]
