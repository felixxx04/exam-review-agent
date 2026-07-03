from __future__ import annotations

from fastapi import APIRouter

from app.agents.tracker_agent import TrackerAgent
from app.core.store import get_shared_store
from app.schemas.common import ApiResponse
from app.schemas.review import MistakeListResponse, MistakeRecord, StudyDay, StudyPlanRequest, StudyPlanResponse, WeakConcept, WeakPointsResponse
from app.services.llm_service import get_default_llm_service

router = APIRouter(prefix="/api/review", tags=["review"])


def _build_tracker() -> TrackerAgent:
    llm = get_default_llm_service()
    return TrackerAgent(db=get_shared_store(), llm_service=llm)


@router.get("/weak-points")
async def get_weak_points():
    tracker = _build_tracker()
    concepts = await tracker.get_weak_concepts("default")
    return ApiResponse.ok(data=WeakPointsResponse(
        weak_concepts=[
            WeakConcept(
                concept=c["concept"],
                topic=c.get("topic", ""),
                accuracy=c["accuracy"],
                attempt_count=c["attempt_count"],
            )
            for c in concepts
        ]
    ))


@router.post("/study-plan")
async def generate_study_plan(request: StudyPlanRequest):
    tracker = _build_tracker()
    result = await tracker.generate_study_plan(
        user_id="default",
        exam_date=request.exam_date,
        days_before_exam=request.days_before_exam,
    )
    return ApiResponse.ok(data=StudyPlanResponse(
        plan=[
            StudyDay(
                day=item["day"],
                topics=item.get("topics", []),
                tasks=item.get("tasks", []),
            )
            for item in result.get("plan", [])
        ],
        message=result.get("message", ""),
    ))

