from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO

from fastapi import APIRouter, HTTPException

from app.agents.tracker_agent import TrackerAgent
from app.core.exceptions import LLMProviderError
from app.core.store import get_shared_store
from app.schemas.common import ApiResponse
from app.schemas.review import (
    DailySessionRequest,
    DailySessionResponse,
    MistakeExportResponse,
    MistakeExplanationResponse,
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


class _UnavailableLLMService:
    def __init__(self, error: LLMProviderError):
        self._error = error

    async def invoke(self, *_args, **_kwargs):
        raise self._error


def _build_tracker() -> TrackerAgent:
    try:
        llm = get_default_llm_service()
    except LLMProviderError as exc:
        llm = _UnavailableLLMService(exc)
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


async def _find_mistake_record(mistake_id: str) -> dict | None:
    return next(
        (record for record in await _mistake_records() if _record_id(record) == mistake_id),
        None,
    )


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


def _next_review_at(status: str, now: datetime) -> str | None:
    if status == "needs_requiz":
        return (now + timedelta(days=1)).isoformat()
    if status == "corrected":
        return (now + timedelta(days=3)).isoformat()
    return None


def _markdown_export(mistakes: list[MistakeRecord]) -> str:
    lines = ["# 错题导出", ""]
    for mistake in mistakes:
        lines.extend([
            f"## {mistake.question_text}",
            "",
            f"- 知识点: {mistake.concept}",
            f"- 主题: {mistake.topic}",
            f"- 错误答案: {mistake.wrong_answer}",
            f"- 正确答案: {mistake.correct_answer}",
            f"- 状态: {mistake.status}",
            f"- 订正: {mistake.correction_note or '未填写'}",
            "",
        ])
    return "\n".join(lines)


def _csv_export(mistakes: list[MistakeRecord]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "question",
        "concept",
        "topic",
        "wrong_answer",
        "correct_answer",
        "status",
        "correction_note",
    ])
    for mistake in mistakes:
        writer.writerow([
            mistake.question_text,
            mistake.concept,
            mistake.topic,
            mistake.wrong_answer,
            mistake.correct_answer,
            mistake.status,
            mistake.correction_note,
        ])
    return output.getvalue()


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
    record = await _find_mistake_record(mistake_id)
    if record is not None:
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
        updates["next_review_at"] = None
    elif request.mastered is False:
        updates["status"] = request.status or "corrected"
        updates["mastered_at"] = None

    target_status = updates.get("status")
    if target_status in {"corrected", "needs_requiz"}:
        updates["next_review_at"] = _next_review_at(target_status, datetime.fromisoformat(now))

    store = get_shared_store()

    def matches(record: dict) -> bool:
        return (
            record.get("user_id") == "default"
            and record.get("type") == "mistake_records"
            and _record_id(record) == mistake_id
        )

    existing = await _find_mistake_record(mistake_id)
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


@router.get("/export")
async def export_mistakes(format: str = "markdown"):
    mistakes = [_normalize_mistake(record) for record in await _mistake_records()]
    if format == "csv":
        content = _csv_export(mistakes)
        filename = "mistakes.csv"
    else:
        format = "markdown"
        content = _markdown_export(mistakes)
        filename = "mistakes.md"
    return ApiResponse.ok(data=MistakeExportResponse(
        format=format,
        filename=filename,
        content=content,
    ))


@router.post("/daily-session")
async def create_daily_session(request: DailySessionRequest):
    records = await _mistake_records()
    mistakes = [_normalize_mistake(record) for record in records]
    reviewable = [mistake for mistake in mistakes if mistake.status != "mastered"]
    selected = _sort_mistakes(reviewable, "priority")[: max(request.limit, 1)]
    return ApiResponse.ok(data=DailySessionResponse(
        mistakes=selected,
        message="今日复习已准备好" if selected else "暂无需要复习的错题",
    ))


@router.post("/mistakes/{mistake_id}/similar-quiz")
async def create_similar_quiz(mistake_id: str):
    record = await _find_mistake_record(mistake_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Mistake not found")

    mistake = _normalize_mistake(record)
    question = {
        "id": f"similar-{mistake.id}-1",
        "question": f"围绕“{mistake.concept}”的相似练习：{mistake.question_text}",
        "question_type": "multiple_choice",
        "options": [
            f"A. {mistake.wrong_answer or '容易混淆的说法'}",
            f"B. {mistake.correct_answer or '正确说法'}",
            "C. 与题干无关的干扰项",
            "D. 只适用于特殊情况的说法",
        ],
        "correct": "B",
        "explanation": mistake.explanation or f"复习“{mistake.concept}”时，先回到定义再判断选项。",
        "difficulty": 0.4,
        "topic": mistake.concept,
        "source_chunk_ids": mistake.source_chunk_ids,
    }
    return ApiResponse.ok(data={
        "questions": [question],
        "topic": mistake.concept,
        "total": 1,
    })


@router.post("/mistakes/{mistake_id}/explanation")
async def explain_mistake(mistake_id: str):
    record = await _find_mistake_record(mistake_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Mistake not found")

    mistake = _normalize_mistake(record)
    explanation = mistake.explanation or (
        f"正确答案是“{mistake.correct_answer}”。"
        f"你的答案是“{mistake.wrong_answer}”，说明“{mistake.concept}”这个知识点还需要回到定义和适用条件重新确认。"
        "下次先判断题目考查的概念，再排除与定义不一致的选项。"
    )

    store = get_shared_store()

    def matches(candidate: dict) -> bool:
        return (
            candidate.get("user_id") == "default"
            and candidate.get("type") == "mistake_records"
            and _record_id(candidate) == mistake_id
        )

    await store.update(matches, {"explanation": explanation})
    return ApiResponse.ok(data=MistakeExplanationResponse(explanation=explanation))


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

