"""Scoring and mistake-tracking agent.

The tracker records every answer, marks correct/incorrect, and
persists mistake records for later weak-point analysis.  It also
provides aggregated weak-concept statistics per user, adaptive
difficulty signals, wrong-answer explanations, and study plans.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreResult:
    """Result of scoring a single student answer."""

    is_correct: bool
    mistake_recorded: bool
    score: float
    feedback: str = ""


class TrackerAgent:
    """Scores answers and tracks mistakes at the concept level.

    Uses a two-level knowledge model: **topic > concept**.  Concepts
    belong to topics.  Mistakes are tracked at the concept level so
    that weak-point analysis can surface both fine-grained (concept)
    and coarse-grained (topic) gaps.
    """

    def __init__(self, db, llm_service):
        self.db = db
        self.llm = llm_service

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    async def score_answer(
        self,
        user_id: str,
        question_id: str,
        correct_answer: str,
        student_answer: str,
        question_type: str,
        concept: str = "",
        topic: str = "",
    ) -> ScoreResult:
        """Score a student answer and record a mistake if incorrect.

        Scoring rules:
        - ``multiple_choice``: case-insensitive, whitespace-trimmed comparison.
        - ``fill_blank``: lowercase-normalized, whitespace-trimmed comparison.
        - other types: exact string comparison (fallback).

        When the answer is wrong, a mistake record is persisted via
        ``self.db.add(...)``.
        """
        if question_type == "multiple_choice":
            is_correct = (
                student_answer.strip().upper()
                == correct_answer.strip().upper()
            )
        elif question_type == "fill_blank":
            is_correct = (
                student_answer.strip().lower()
                == correct_answer.strip().lower()
            )
        else:
            is_correct = student_answer == correct_answer

        mistake_recorded = False
        if not is_correct:
            await self.db.add(
                {
                    "type": "mistake_records",
                    "user_id": user_id,
                    "question_id": question_id,
                    "concept": concept,
                    "topic": topic,
                    "wrong_answer": student_answer,
                    "correct_answer": correct_answer,
                }
            )
            mistake_recorded = True

        return ScoreResult(
            is_correct=is_correct,
            mistake_recorded=mistake_recorded,
            score=1.0 if is_correct else 0.0,
        )

    # ------------------------------------------------------------------
    # Weak-point analysis
    # ------------------------------------------------------------------

    async def get_weak_concepts(self, user_id: str) -> list[dict]:
        """Return weak concepts for a user sorted by mistake count (descending).

        Queries mistake records from the database, aggregates them by
        concept, and returns a sorted list with accuracy and attempt
        counts.
        """
        mistakes = await self.db.query(
            {"user_id": user_id, "type": "mistake_records"}
        )

        concept_stats: dict[str, dict] = {}
        for m in mistakes:
            key = m["concept"]
            if key not in concept_stats:
                concept_stats[key] = {
                    "total": 0,
                    "wrong": 0,
                    "topic": m.get("topic", ""),
                }
            concept_stats[key]["wrong"] += 1

        return [
            {
                "concept": k,
                "topic": v["topic"],
                "accuracy": 0.0,
                "attempt_count": v["wrong"],
            }
            for k, v in sorted(
                concept_stats.items(), key=lambda x: -x[1]["wrong"]
            )
        ]

    # ------------------------------------------------------------------
    # Adaptive difficulty
    # ------------------------------------------------------------------

    async def get_adaptive_difficulty(self, user_id: str, concept: str) -> float:
        """Return a difficulty signal based on the user's mistake history.

        - 3+ consecutive wrong answers on a concept -> difficulty drops to 0.2 (easy)
        - 1-2 wrong -> difficulty stays at 0.5 (medium)
        - 0 wrong (all correct) -> difficulty rises to 0.8 (hard)
        """
        mistakes = await self.db.query(
            {"user_id": user_id, "concept": concept}
        )
        wrong_count = len(mistakes)
        if wrong_count >= 3:
            return 0.2
        elif wrong_count >= 1:
            return 0.5
        else:
            return 0.8

    # ------------------------------------------------------------------
    # Wrong-answer explanation
    # ------------------------------------------------------------------

    async def explain_wrong_answer(
        self,
        question: str,
        correct_answer: str,
        student_answer: str,
        source_chunks: list[str] | None = None,
    ) -> str:
        """Generate an explanation for why the correct answer is right
        and why the student's answer is wrong, using LLM with source citations."""
        context = ""
        if source_chunks:
            context = "\n\n参考资料:\n" + "\n".join(source_chunks)

        prompt = (
            f"学生在以下题目中选择了错误答案。\n\n"
            f"题目: {question}\n"
            f"正确答案: {correct_answer}\n"
            f"学生答案: {student_answer}\n\n"
            f"请解释:\n"
            f"1. 为什么正确答案是对的\n"
            f"2. 为什么学生的答案是错的\n"
            f"3. 这个知识点需要注意什么\n"
            f"{context}\n\n"
            f"回答:"
        )
        return await self.llm.invoke([{"role": "user", "content": prompt}])

    # ------------------------------------------------------------------
    # Study plan generation
    # ------------------------------------------------------------------

    async def generate_study_plan(
        self,
        user_id: str,
        exam_date: str,
        days_before_exam: int = 7,
    ) -> dict:
        """Generate a day-by-day study plan based on weak concepts and exam date."""
        weak_concepts = await self.get_weak_concepts(user_id)

        if not weak_concepts:
            return {"plan": [], "message": "暂无薄弱知识点，建议全面复习"}

        concept_list = "\n".join(
            f"- {c['concept']} (主题: {c['topic']}, 错误次数: {c['attempt_count']})"
            for c in weak_concepts
        )

        prompt = (
            f"考试日期: {exam_date}，距考试还有{days_before_exam}天。\n\n"
            f"学生的薄弱知识点:\n{concept_list}\n\n"
            f"请生成一个{days_before_exam}天的复习计划，每天安排1-2个薄弱知识点重点复习，"
            f"最后一天安排全面回顾。\n\n"
            f"返回JSON格式:\n"
            f'[{{"day": 1, "topics": ["知识点1"], "tasks": ["重做错题", "阅读教材相关章节"]}}]\n\n'
            f"请直接返回JSON数组:"
        )
        response = await self.llm.invoke([{"role": "user", "content": prompt}])

        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            return {"plan": json.loads(text), "raw_response": response}
        except json.JSONDecodeError:
            return {"plan": [], "raw_response": response}
