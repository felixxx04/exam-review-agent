"""Scoring and mistake-tracking agent.

The tracker records every answer, marks correct/incorrect, and
persists mistake records for later weak-point analysis.  It also
provides aggregated weak-concept statistics per user.
"""

from __future__ import annotations

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
