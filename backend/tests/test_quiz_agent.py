"""Tests for QuizAgent and QuizGenerator."""

from unittest.mock import AsyncMock

import pytest

from app.agents.quiz_agent import QuizAgent
from app.schemas.quiz import Question, QuizRequest, QuizResponse
from app.services.retrieval_service import SearchResult
from app.specialists.quiz_generator import QuizGenerator


# ---------------------------------------------------------------------------
# QuizGenerator tests
# ---------------------------------------------------------------------------


class ChunkStub:
    """Stub that mimics a retrieved chunk with id and text."""

    def __init__(self, chunk_id: str, text: str):
        self.id = chunk_id
        self.text = text


@pytest.mark.asyncio
async def test_quiz_generator_produces_questions_with_source_ids():
    """QuizGenerator should parse LLM JSON and return Question objects."""
    generator = QuizGenerator(llm_service=AsyncMock())
    generator.llm_service.invoke = AsyncMock(
        return_value=(
            '[{"question":"以下哪个是薛定谔方程?",'
            '"options":["A. E=mc²","B. iℏ∂ψ/∂t=Ĥψ",'
            '"C. F=ma","D. ∇²φ=ρ/ε₀"],'
            '"correct":"B",'
            '"explanation":"薛定谔方程是量子力学基本方程",'
            '"source_chunk_ids":["chunk-1"]}]'
        )
    )

    questions = await generator.generate(
        chunks=[ChunkStub(chunk_id="chunk-1", text="薛定谔方程相关内容")],
        difficulty=0.5,
        count=1,
    )

    assert len(questions) == 1
    assert questions[0].source_chunk_ids == ["chunk-1"]
    assert questions[0].correct == "B"


@pytest.mark.asyncio
async def test_quiz_generator_returns_empty_on_invalid_json():
    """If the LLM returns invalid JSON, return an empty list."""
    generator = QuizGenerator(llm_service=AsyncMock())
    generator.llm_service.invoke = AsyncMock(return_value="not valid json")

    questions = await generator.generate(
        chunks=[ChunkStub(chunk_id="c1", text="some text")],
        difficulty=0.5,
        count=1,
    )

    assert questions == []


@pytest.mark.asyncio
async def test_quiz_generator_prompt_includes_chunk_content():
    """The LLM prompt should include chunk text content."""
    generator = QuizGenerator(llm_service=AsyncMock())
    generator.llm_service.invoke = AsyncMock(return_value="[]")

    await generator.generate(
        chunks=[ChunkStub(chunk_id="c1", text="量子力学基础")],
        difficulty=0.3,
        count=2,
    )

    prompt = generator.llm_service.invoke.call_args[0][0][0]["content"]
    assert "量子力学基础" in prompt
    assert "简单" in prompt


@pytest.mark.asyncio
async def test_quiz_generator_difficulty_labels():
    """Difficulty is translated to Chinese labels in the prompt."""
    generator = QuizGenerator(llm_service=AsyncMock())
    generator.llm_service.invoke = AsyncMock(return_value="[]")

    await generator.generate(
        chunks=[ChunkStub(chunk_id="c1", text="t")],
        difficulty=0.8,
        count=1,
    )

    prompt = generator.llm_service.invoke.call_args[0][0][0]["content"]
    assert "困难" in prompt


# ---------------------------------------------------------------------------
# QuizAgent tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quiz_agent_returns_quiz_response():
    """QuizAgent should retrieve chunks, generate questions, and return a response."""
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=QuizGenerator(llm_service=AsyncMock()),
    )

    agent.retrieval.search = AsyncMock(
        return_value=[
            SearchResult(text="量子力学基本概念", score=0.9, metadata={"source": "physics.pdf"}),
        ]
    )
    agent.generator.llm_service.invoke = AsyncMock(
        return_value=(
            '[{"question":"以下哪个是量子力学概念?",'
            '"options":["A. 牛顿定律","B. 波函数","C. 加速度","D. 引力"],'
            '"correct":"B",'
            '"explanation":"波函数是量子力学的核心概念",'
            '"source_chunk_ids":["chunk-0"]}]'
        )
    )

    result = await agent.generate_quiz(
        user_id="test-user",
        topic="量子力学",
        difficulty=0.5,
        count=1,
    )

    assert isinstance(result, QuizResponse)
    assert len(result.questions) == 1
    assert result.questions[0].correct == "B"
    agent.retrieval.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_quiz_agent_empty_retrieval_returns_empty_quiz():
    """When no chunks are found, return an empty QuizResponse."""
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=QuizGenerator(llm_service=AsyncMock()),
    )
    agent.retrieval.search = AsyncMock(return_value=[])

    result = await agent.generate_quiz(
        user_id="test-user",
        topic="不存在的话题",
        count=3,
    )

    assert len(result.questions) == 0
    assert result.topic == "不存在的话题"
    agent.retrieval.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_quiz_agent_does_not_fallback_without_material_scope():
    """Generic quiz requests without selected material should not silently use all files."""
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=QuizGenerator(llm_service=AsyncMock()),
    )
    agent.retrieval.search = AsyncMock(return_value=[])

    result = await agent.generate_quiz(
        user_id="test-user",
        topic="核心概念 重点知识",
        count=3,
        material_scope=None,
    )

    assert len(result.questions) == 0
    agent.retrieval.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_quiz_agent_falls_back_to_scoped_material_when_topic_is_generic():
    """Scoped quiz requests should still use selected material if topic search is too generic."""
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=AsyncMock(),
    )
    fallback_chunks = [
        SearchResult(text="MQ 消息队列可以用于解耦、异步和削峰", score=0.1, metadata={"source": "MQ.docx"}),
    ]
    agent.retrieval.search = AsyncMock(side_effect=[[], fallback_chunks])
    agent.generator.generate = AsyncMock(return_value=[])

    await agent.generate_quiz(
        user_id="test-user",
        topic="核心概念 重点知识",
        material_scope=["MQ.docx"],
    )

    assert agent.retrieval.search.await_count == 2
    fallback_call = agent.retrieval.search.await_args_list[1].kwargs
    assert fallback_call["metadata_filter"] == {"source": {"$in": ["MQ.docx"]}}
    assert fallback_call["apply_quality_gate"] is False
    agent.generator.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_quiz_agent_passes_material_scope():
    """Material scope should be converted to metadata filter."""
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=QuizGenerator(llm_service=AsyncMock()),
    )
    agent.retrieval.search = AsyncMock(
        return_value=[
            SearchResult(text="t", score=0.5, metadata={"source": "notes.pdf"}),
        ]
    )
    agent.generator.llm_service.invoke = AsyncMock(return_value="[]")

    await agent.generate_quiz(
        user_id="test-user",
        topic="测试",
        material_scope=["notes.pdf", "slides.pdf"],
    )

    call_kwargs = agent.retrieval.search.call_args.kwargs
    assert call_kwargs["metadata_filter"] == {"source": {"$in": ["notes.pdf", "slides.pdf"]}}


@pytest.mark.asyncio
async def test_quiz_agent_grade_answer_delegates_to_tracker():
    """Grading a quiz answer should delegate to TrackerAgent."""
    mock_tracker = AsyncMock()
    mock_tracker.score_answer = AsyncMock(return_value=None)
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=QuizGenerator(llm_service=AsyncMock()),
        tracker_agent=mock_tracker,
    )

    await agent.grade_answer(
        user_id="u1",
        question_id="q1",
        correct_answer="B",
        student_answer="A",
        question_type="multiple_choice",
        concept="测试概念",
        topic="测试主题",
    )

    mock_tracker.score_answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_quiz_agent_grade_answer_no_tracker_returns_none():
    """Grading without a tracker agent should return None."""
    agent = QuizAgent(
        retrieval_service=AsyncMock(),
        quiz_generator=QuizGenerator(llm_service=AsyncMock()),
    )

    result = await agent.grade_answer(
        user_id="u1",
        question_id="q1",
        correct_answer="B",
        student_answer="B",
        question_type="multiple_choice",
    )

    assert result is None


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_question_dataclass_defaults():
    """Question should have sensible defaults."""
    q = Question(
        question="q",
        options=["A", "B", "C", "D"],
        correct="A",
        explanation="expl",
    )
    assert q.source_chunk_ids == []
    assert q.correct == "A"


def test_quiz_request_defaults():
    """QuizRequest should have sensible defaults."""
    req = QuizRequest(topic="测试")
    assert req.difficulty == 0.5
    assert req.count == 5
    assert req.material_scope is None


def test_quiz_response_total_computed():
    """QuizResponse total is computed from the questions list."""
    q1 = Question(question="q1", options=["A", "B"], correct="A", explanation="e")
    q2 = Question(question="q2", options=["A", "B"], correct="B", explanation="e")
    resp = QuizResponse(questions=[q1, q2], topic="测试")
    assert resp.total == 2


def test_quiz_response_empty():
    """Empty QuizResponse should have total 0."""
    resp = QuizResponse(questions=[], topic="测试")
    assert resp.total == 0
