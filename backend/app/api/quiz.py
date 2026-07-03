from __future__ import annotations

from fastapi import APIRouter

from app.agents.quiz_agent import QuizAgent
from app.agents.tracker_agent import TrackerAgent
from app.core.store import get_shared_store
from app.schemas.common import ApiResponse
from app.schemas.quiz import QuizRequest, to_quiz_payload
from app.services.llm_service import get_default_llm_service
from app.services.retrieval_service import RetrievalService
from app.specialists.quiz_generator import QuizGenerator

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


def _build_quiz_agent() -> QuizAgent:
    llm = get_default_llm_service()
    retrieval = RetrievalService()
    generator = QuizGenerator(llm)
    return QuizAgent(retrieval, generator)


@router.post("/generate")
async def generate_quiz(request: QuizRequest):
    agent = _build_quiz_agent()
    response = await agent.generate_quiz(
        user_id="default",
        topic=request.topic,
        difficulty=request.difficulty,
        count=request.count,
        material_scope=request.material_scope,
    )
    return ApiResponse.ok(data=to_quiz_payload(response, difficulty=request.difficulty))


@router.post("/submit")
async def submit_answer(
    question_id: str,
    correct_answer: str,
    student_answer: str,
    question_type: str = "multiple_choice",
    concept: str = "",
    topic: str = "",
):
    llm = get_default_llm_service()
    tracker = TrackerAgent(db=get_shared_store(), llm_service=llm)
    result = await tracker.score_answer(
        user_id="default",
        question_id=question_id,
        correct_answer=correct_answer,
        student_answer=student_answer,
        question_type=question_type,
        concept=concept,
        topic=topic,
    )
    return ApiResponse.ok(data={
        "is_correct": result.is_correct,
        "mistake_recorded": result.mistake_recorded,
        "score": result.score,
        "feedback": result.feedback,
    })

