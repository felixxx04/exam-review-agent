from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.agents.tracker_agent import TrackerAgent
from app.core.store import get_shared_store
from app.schemas.common import ApiResponse
from app.schemas.review import (
    MistakeListResponse,
    MistakeRecord,
    MistakeUpdateRequest,
    ReviewSummary,
    StudyDay,
    StudyPlanRequest,
    StudyPlanResponse,
    WeakConcept,
    WeakPointsResponse,
)
from app.services.llm_service import get_default_llm_service

router = APIRouter(prefix="/api/review", tags=["review"])


def _build_tracker() -> TrackerAgent:
    llm = get_default_llm_service()
    return TrackerAgent(db=get_shared_store(), llm_service=llm)


def _record_id(record: dict) -> str:
    return str(record.get("id") or record.get("question_id") or "")


def _normalize_mistake(record: dict) -> MistakeRecord:
    status = record.get("status") or "unreviewed"
    mastered_at = record.get("mastered_at")
    if mastered_at:
        status = "mastered"

    return MistakeRecord(
        id=_record_id(record),
        question_id=str(record.get("question_id", "")),
        question_text=record.get("question_text") or "暂无题干",
        question_type=record.get("question_type") or "multiple_choice",
        concept=record.get("concept") or "未归类知识点",
        topic=record.get("topic") or "综合",
        wrong_answer=record.get("wrong_answer") or "",
        correct_answer=record.get("correct_answer") or "",
        explanation=record.get("explanation") or None,
        source_material=record.get("source_material") or None,
        source_chunk_ids=list(record.get("source_chunk_ids") or []),
        status=status,
        attempt_count=int(record.get("attempt_count") or 1),
        last_wrong_at=record.get("last_wrong_at") or "",
        correction_note=record.get("correction_note") or "",
        mastered_at=mastered_at,
        next_review_at=record.get("next_review_at"),
        review_history=list(record.get("review_history") or []),
    )


async def _mistake_records() -> list[dict]:
    store = get_shared_store()
    return await store.query({"user_id": "default", "type": "mistake_records"})


def _summary(mistakes: list[MistakeRecord]) -> ReviewSummary:
    return ReviewSummary(
        total_count=len(mistakes),
        pending_count=len([
            m for m in mistakes
            if m.status in {"unreviewed", "needs_requiz", "corrected"}
        ]),
        mastered_count=len([m for m in mistakes if m.status == "mastered"]),
        corrected_count=len([m for m in mistakes if m.status == "corrected"]),
        needs_requiz_count=len([m for m in mistakes if m.status == "needs_requiz"]),
    )


def _sort_mistakes(mistakes: list[MistakeRecord], sort: str) -> list[MistakeRecord]:
    if sort == "latest":
        return sorted(mistakes, key=lambda m: m.last_wrong_at, reverse=True)
    if sort == "mistake_count":
        return sorted(mistakes, key=lambda m: m.attempt_count, reverse=True)

    rank = {"unreviewed": 0, "needs_requiz": 1, "corrected": 2, "mastered": 3}
    return sorted(
        mistakes,
        key=lambda m: (
            rank.get(m.status, 4),
            -m.attempt_count,
            m.last_wrong_at,
        ),
    )


def _matches_search(mistake: MistakeRecord, search: str) -> bool:
    text = search.lower().strip()
    if not text:
        return True
    haystack = " ".join([
        mistake.question_text,
        mistake.concept,
        mistake.topic,
        mistake.wrong_answer,
        mistake.correct_answer,
    ]).lower()
    return text in haystack


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


@router.get("/mistakes")
async def list_mistakes(
    status: str | None = None,
    concept: str | None = None,
    topic: str | None = None,
    question_type: str | None = None,
    search: str = "",
    sort: str = "priority",
    limit: int = 50,
    offset: int = 0,
):
    records = await _mistake_records()
    mistakes = [_normalize_mistake(record) for record in records]

    if status:
        mistakes = [m for m in mistakes if m.status == status]
    if concept:
        mistakes = [m for m in mistakes if m.concept == concept]
    if topic:
        mistakes = [m for m in mistakes if m.topic == topic]
    if question_type:
        mistakes = [m for m in mistakes if m.question_type == question_type]
    if search:
        mistakes = [m for m in mistakes if _matches_search(m, search)]

    mistakes = _sort_mistakes(mistakes, sort)
    paged = mistakes[offset: offset + limit]
    return ApiResponse.ok(data=MistakeListResponse(
        mistakes=paged,
        summary=_summary(mistakes),
    ))


@router.get("/mistakes/{mistake_id}")
async def get_mistake(mistake_id: str):
    for record in await _mistake_records():
        if _record_id(record) == mistake_id:
            return ApiResponse.ok(data=_normalize_mistake(record))
    raise HTTPException(status_code=404, detail="Mistake not found")


@router.patch("/mistakes/{mistake_id}")
async def update_mistake(mistake_id: str, request: MistakeUpdateRequest):
    updates: dict = {}
    now = datetime.now(timezone.utc).isoformat()

    if request.correction_note is not None:
        updates["correction_note"] = request.correction_note
    if request.status is not None:
        updates["status"] = request.status
    if request.mastered is True:
        updates["status"] = "mastered"
        updates["mastered_at"] = now
    elif request.mastered is False:
        updates["status"] = request.status or "corrected"
        updates["mastered_at"] = None

    store = get_shared_store()

    def matches(record: dict) -> bool:
        return (
            record.get("user_id") == "default"
            and record.get("type") == "mistake_records"
            and _record_id(record) == mistake_id
        )

    existing = next((record for record in await _mistake_records() if matches(record)), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Mistake not found")

    history = list(existing.get("review_history") or [])
    if updates:
        history.append({
            "event": updates.get("status", existing.get("status", "updated")),
            "at": now,
        })
        updates["review_history"] = history

    updated = await store.update(matches, updates)
    return ApiResponse.ok(data=_normalize_mistake(updated or existing))


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

