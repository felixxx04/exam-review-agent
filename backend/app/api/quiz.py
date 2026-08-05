from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.quiz_agent import QuizAgent
from app.agents.tracker_agent import TrackerAgent
from app.api.dependencies import get_mistake_repository
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.database import get_db
from app.repositories.mistakes import MistakeRepository
from app.schemas.common import ApiResponse
from app.schemas.quiz import QuizRequest, QuizSubmitRequest, to_quiz_payload
from app.services.llm_service import get_default_llm_service
from app.services.retrieval_service import RetrievalService
from app.services.course_service import CourseService
from app.specialists.quiz_generator import QuizGenerator

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


def _build_quiz_agent() -> QuizAgent:
    llm = get_default_llm_service()
    retrieval = RetrievalService()
    generator = QuizGenerator(llm)
    return QuizAgent(retrieval, generator)


@router.post("/generate")
async def generate_quiz(
    request: QuizRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).resolve_course(current_user.id, request.course_id)
    agent = _build_quiz_agent()
    response = await agent.generate_quiz(
        user_id=current_user.subject,
        topic=request.topic,
        course_id=course.id,
        difficulty=request.difficulty,
        count=request.count,
        material_scope=request.material_scope,
    )
    return ApiResponse.ok(data=to_quiz_payload(response, difficulty=request.difficulty))


@router.post("/submit")
async def submit_answer(
    payload: QuizSubmitRequest | None = Body(default=None),
    question_id: str | None = None,
    correct_answer: str | None = None,
    student_answer: str | None = None,
    question_type: str = "multiple_choice",
    concept: str = "",
    topic: str = "",
    course_id: int | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    mistake_repository: MistakeRepository = Depends(get_mistake_repository),
    db: AsyncSession = Depends(get_db),
):
    if payload is None:
        if question_id is None or correct_answer is None or student_answer is None:
            raise HTTPException(
                status_code=422, detail="Missing quiz submission fields"
            )
        payload = QuizSubmitRequest(
            question_id=question_id,
            correct_answer=correct_answer,
            student_answer=student_answer,
            question_type=question_type,
            concept=concept,
            topic=topic,
            course_id=course_id,
        )

    course = await CourseService(db).resolve_course(current_user.id, payload.course_id)

    tracker = TrackerAgent(
        mistake_repository=mistake_repository,
        llm_service=None,
    )
    result = await tracker.score_answer(
        user_id=current_user.subject,
        question_id=payload.question_id,
        correct_answer=payload.correct_answer,
        student_answer=payload.student_answer,
        question_type=payload.question_type,
        course_id=course.id,
        concept=payload.concept,
        topic=payload.topic,
        question_text=payload.question_text,
        explanation=payload.explanation,
        source_chunk_ids=payload.source_chunk_ids,
        source_material=payload.source_material,
    )
    return ApiResponse.ok(
        data={
            "is_correct": result.is_correct,
            "mistake_recorded": result.mistake_recorded,
            "score": result.score,
            "feedback": result.feedback,
        }
    )
