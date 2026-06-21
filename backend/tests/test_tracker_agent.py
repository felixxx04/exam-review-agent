"""Tests for TrackerAgent and MistakeSummarizer."""

import pytest
from unittest.mock import AsyncMock

from app.agents.tracker_agent import ScoreResult, TrackerAgent
from app.specialists.mistake_summarizer import MistakeSummarizer


# ---------------------------------------------------------------------------
# TrackerAgent tests
# ---------------------------------------------------------------------------


class TestTrackerScoring:
    """Tests for answer scoring logic."""

    @pytest.mark.asyncio
    async def test_tracker_scores_mc_and_records_mistake(self):
        """Multiple choice: wrong answer should be scored as incorrect
        and a mistake record should be persisted."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="test-user",
            question_id="q1",
            correct_answer="B",
            student_answer="A",
            question_type="multiple_choice",
            concept="特征值",
            topic="线性代数",
        )

        assert isinstance(result, ScoreResult)
        assert result.is_correct is False
        assert result.mistake_recorded is True
        assert result.score == 0.0

        # Verify the mistake was recorded
        mock_db.add.assert_called_once()
        call_args = mock_db.add.call_args[0][0]
        assert call_args["user_id"] == "test-user"
        assert call_args["question_id"] == "q1"
        assert call_args["concept"] == "特征值"
        assert call_args["topic"] == "线性代数"
        assert call_args["wrong_answer"] == "A"
        assert call_args["correct_answer"] == "B"

    @pytest.mark.asyncio
    async def test_correct_mc_does_not_record_mistake(self):
        """Correct multiple choice answer should not create a mistake record."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="test-user",
            question_id="q1",
            correct_answer="B",
            student_answer="B",
            question_type="multiple_choice",
            concept="特征值",
            topic="线性代数",
        )

        assert result.is_correct is True
        assert result.mistake_recorded is False
        assert result.score == 1.0
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_case_insensitive_mc_scoring(self):
        """Multiple choice scoring is case-insensitive."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="u1",
            question_id="q1",
            correct_answer="B",
            student_answer="b",
            question_type="multiple_choice",
            concept="测试",
            topic="测试",
        )

        assert result.is_correct is True

    @pytest.mark.asyncio
    async def test_whitespace_handling_mc_scoring(self):
        """Multiple choice scoring trims whitespace from the student answer."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="u1",
            question_id="q1",
            correct_answer="C",
            student_answer="  C  ",
            question_type="multiple_choice",
            concept="测试",
            topic="测试",
        )

        assert result.is_correct is True

    @pytest.mark.asyncio
    async def test_fill_blank_normalized_comparison(self):
        """Fill-in-the-blank uses lowercase-normalized comparison."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="u1",
            question_id="q1",
            correct_answer="Newton",
            student_answer="newton",
            question_type="fill_blank",
            concept="物理",
            topic="力学",
        )

        assert result.is_correct is True

    @pytest.mark.asyncio
    async def test_fill_blank_wrong_answer(self):
        """Fill-in-the-blank wrong answer records a mistake."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="u1",
            question_id="q1",
            correct_answer="光合作用",
            student_answer="呼吸作用",
            question_type="fill_blank",
            concept="光合作用",
            topic="生物学",
        )

        assert result.is_correct is False
        assert result.mistake_recorded is True

    @pytest.mark.asyncio
    async def test_essay_type_default_comparison(self):
        """Essay/short-answer uses exact comparison as fallback."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        result = await tracker.score_answer(
            user_id="u1",
            question_id="q1",
            correct_answer="some_answer",
            student_answer="some_answer",
            question_type="short_answer",
            concept="测试",
            topic="测试",
        )

        assert result.is_correct is True


class TestTrackerWeakConcepts:
    """Tests for weak concepts aggregation."""

    @pytest.mark.asyncio
    async def test_get_weak_concepts_aggregates_by_concept(self):
        """Weak concepts should be aggregated and sorted by mistake count."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_db.query = AsyncMock(
            return_value=[
                {"user_id": "u1", "concept": "特征值", "topic": "线性代数",
                 "wrong_answer": "A", "correct_answer": "B"},
                {"user_id": "u1", "concept": "特征值", "topic": "线性代数",
                 "wrong_answer": "C", "correct_answer": "D"},
                {"user_id": "u1", "concept": "导数", "topic": "微积分",
                 "wrong_answer": "1", "correct_answer": "2"},
            ]
        )
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        results = await tracker.get_weak_concepts(user_id="u1")

        assert len(results) == 2
        # 特征值 should come first (2 mistakes vs 1)
        assert results[0]["concept"] == "特征值"
        assert results[0]["topic"] == "线性代数"
        assert results[0]["accuracy"] == 0.0
        assert results[0]["attempt_count"] == 2
        assert results[1]["concept"] == "导数"
        assert results[1]["attempt_count"] == 1

    @pytest.mark.asyncio
    async def test_get_weak_concepts_empty(self):
        """No mistakes should return an empty list."""
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        tracker = TrackerAgent(db=mock_db, llm_service=mock_llm)

        results = await tracker.get_weak_concepts(user_id="u1")

        assert results == []


# ---------------------------------------------------------------------------
# MistakeSummarizer tests
# ---------------------------------------------------------------------------


class TestMistakeSummarizer:
    """Tests for the MistakeSummarizer specialist."""

    @pytest.mark.asyncio
    async def test_summarize_empty_mistakes(self):
        """Empty mistake list returns a fallback Chinese message."""
        mock_llm = AsyncMock()
        summarizer = MistakeSummarizer(llm_service=mock_llm)

        result = await summarizer.summarize([])

        assert "暂无错题记录" in result
        mock_llm.invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarize_few_mistakes_full_mode(self):
        """Fewer than 5 mistakes triggers full rewrite mode."""
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value="薄弱点：特征值理解不深，需要加强练习。")
        summarizer = MistakeSummarizer(llm_service=mock_llm)

        mistakes = [
            {"concept": "特征值", "topic": "线性代数",
             "wrong_answer": "A", "correct_answer": "B"},
            {"concept": "导数", "topic": "微积分",
             "wrong_answer": "1", "correct_answer": "2"},
        ]

        result = await summarizer.summarize(mistakes, mode="full")

        assert "特征值" in result or "薄弱点" in result
        mock_llm.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_many_mistakes_incremental_mode(self):
        """Five or more mistakes defaults to incremental summary."""
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value="新增薄弱点：概率论基础概念混淆。")
        summarizer = MistakeSummarizer(llm_service=mock_llm)

        mistakes = [
            {"concept": f"概念{i}", "topic": "测试",
             "wrong_answer": "X", "correct_answer": "Y"}
            for i in range(5)
        ]

        result = await summarizer.summarize(mistakes, mode="full")

        mock_llm.invoke.assert_called_once()
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_summarize_incremental_mode_only_latest(self):
        """Incremental mode should only use the most recent 5 mistakes."""
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value="新增薄弱点：高级概念。")
        summarizer = MistakeSummarizer(llm_service=mock_llm)

        mistakes = [
            {"concept": f"概念{i}", "topic": "测试",
             "wrong_answer": "X", "correct_answer": "Y"}
            for i in range(10)
        ]

        result = await summarizer.summarize(mistakes, mode="incremental")

        mock_llm.invoke.assert_called_once()
        # The prompt should only contain the last 5 concepts
        call_content = mock_llm.invoke.call_args[0][0][0]["content"]
        assert "概念0" not in call_content
        assert "概念9" in call_content
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_auto_mode_selection_few_mistakes(self):
        """Auto mode selection: fewer than 5 mistakes -> full mode."""
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value="总结：主要薄弱点...")
        summarizer = MistakeSummarizer(llm_service=mock_llm)

        mistakes = [
            {"concept": "概念1", "topic": "测试",
             "wrong_answer": "A", "correct_answer": "B"},
        ]

        result = await summarizer.summarize(mistakes)

        assert len(result) > 0
        # Full mode prompt should include all mistakes
        call_content = mock_llm.invoke.call_args[0][0][0]["content"]
        assert "概念1" in call_content

    @pytest.mark.asyncio
    async def test_auto_mode_selection_many_mistakes(self):
        """Auto mode selection: 5+ mistakes -> incremental mode."""
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value="新增薄弱点：测试。")
        summarizer = MistakeSummarizer(llm_service=mock_llm)

        mistakes = [
            {"concept": f"概念{i}", "topic": "测试",
             "wrong_answer": "X", "correct_answer": "Y"}
            for i in range(7)
        ]

        result = await summarizer.summarize(mistakes)

        assert len(result) > 0
        # Incremental mode should only include last 5
        call_content = mock_llm.invoke.call_args[0][0][0]["content"]
        assert "概念0" not in call_content


class TestScoreResultDataclass:
    """Tests for the ScoreResult value object."""

    def test_score_result_correct(self):
        """A correct ScoreResult has expected defaults."""
        sr = ScoreResult(is_correct=True, mistake_recorded=False, score=1.0)
        assert sr.is_correct is True
        assert sr.mistake_recorded is False
        assert sr.score == 1.0
        assert sr.feedback == ""

    def test_score_result_incorrect_with_feedback(self):
        """An incorrect ScoreResult can carry feedback."""
        sr = ScoreResult(
            is_correct=False,
            mistake_recorded=True,
            score=0.0,
            feedback="请复习特征值的定义。"
        )
        assert sr.is_correct is False
        assert sr.mistake_recorded is True
        assert sr.score == 0.0
        assert sr.feedback == "请复习特征值的定义。"

    def test_score_result_immutability(self):
        """ScoreResult is frozen (immutable)."""
        sr = ScoreResult(is_correct=True, mistake_recorded=False, score=1.0)
        with pytest.raises(Exception):
            sr.is_correct = False  # type: ignore[misc]


class TestAdaptiveDifficulty:

    @pytest.mark.asyncio
    async def test_adaptive_difficulty_easy_after_many_wrong(self):
        """3+ wrong answers on a concept should produce easy difficulty."""
        tracker = TrackerAgent(db=AsyncMock(), llm_service=AsyncMock())
        tracker.db.query = AsyncMock(return_value=[
            {"concept": "特征值", "topic": "线性代数"},
            {"concept": "特征值", "topic": "线性代数"},
            {"concept": "特征值", "topic": "线性代数"},
        ])
        signal = await tracker.get_adaptive_difficulty("test-user", "特征值")
        assert signal <= 0.3

    @pytest.mark.asyncio
    async def test_adaptive_difficulty_hard_when_no_mistakes(self):
        """0 wrong answers should produce hard difficulty."""
        tracker = TrackerAgent(db=AsyncMock(), llm_service=AsyncMock())
        tracker.db.query = AsyncMock(return_value=[])
        signal = await tracker.get_adaptive_difficulty("test-user", "量子力学")
        assert signal >= 0.7
