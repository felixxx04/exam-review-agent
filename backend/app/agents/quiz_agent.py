"""Quiz agent for interactive quiz generation and grading.

Orchestrates the quiz workflow: retrieval -> question generation ->
presentation, and delegates answer scoring to the TrackerAgent.
"""

from __future__ import annotations

from app.schemas.quiz import QuizResponse
from app.services.retrieval_service import SearchResult


class QuizAgent:
    """Orchestrates quiz generation from user materials.

    Workflow:
    1. Retrieves relevant content via RetrievalService
    2. Generates questions via QuizGenerator specialist
    3. Delegates answer grading to TrackerAgent
    """

    def __init__(self, retrieval_service, quiz_generator, tracker_agent=None):
        self.retrieval = retrieval_service
        self.generator = quiz_generator
        self.tracker = tracker_agent

    async def generate_quiz(
        self,
        user_id: str,
        topic: str,
        difficulty: float = 0.5,
        count: int = 5,
        material_scope: list[str] | None = None,
    ) -> QuizResponse:
        """Generate a quiz by retrieving content and creating questions.

        Args:
            user_id: The user requesting the quiz.
            topic: Quiz topic (used as search query).
            difficulty: Target difficulty (0.0-1.0).
            count: Number of questions.
            material_scope: Optional list of source filenames to restrict to.
        """
        metadata_filter = None
        if material_scope:
            metadata_filter = {"source": {"$in": material_scope}}

        chunks = await self.retrieval.search(
            user_id=user_id,
            query=topic,
            top_k=count,
            metadata_filter=metadata_filter,
        )

        if not chunks:
            return QuizResponse(questions=[], topic=topic)

        questions = await self.generator.generate(
            chunks=chunks,
            difficulty=difficulty,
            count=min(count, questions_allowance(chunks)),
        )

        return QuizResponse(questions=questions, topic=topic)

    async def grade_answer(
        self,
        user_id: str,
        question_id: str,
        correct_answer: str,
        student_answer: str,
        question_type: str,
        concept: str = "",
        topic: str = "",
    ):
        """Grade a single answer using the tracker agent."""
        if self.tracker is None:
            return None
        return await self.tracker.score_answer(
            user_id=user_id,
            question_id=question_id,
            correct_answer=correct_answer,
            student_answer=student_answer,
            question_type=question_type,
            concept=concept,
            topic=topic,
        )


def questions_allowance(chunks: list[SearchResult]) -> int:
    """Limit questions so we don't exceed available chunks."""
    return len(chunks)
