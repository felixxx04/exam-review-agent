from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class WeakConcept:
    concept: str
    topic: str
    accuracy: float
    attempt_count: int


@dataclass
class WeakPointsResponse:
    weak_concepts: list[WeakConcept]
    total: int = 0

    def __post_init__(self) -> None:
        self.total = len(self.weak_concepts)


@dataclass
class MistakeRecord:
    id: str
    question_id: str
    question_text: str
    question_type: str
    concept: str
    topic: str
    wrong_answer: str
    correct_answer: str
    explanation: str | None = None
    source_material: str | None = None
    source_chunk_ids: list[str] = field(default_factory=list)
    status: str = "unreviewed"
    attempt_count: int = 1
    last_wrong_at: str = ""
    correction_note: str = ""
    mastered_at: str | None = None
    next_review_at: str | None = None
    review_history: list[dict] = field(default_factory=list)


@dataclass
class ReviewSummary:
    total_count: int = 0
    pending_count: int = 0
    mastered_count: int = 0
    corrected_count: int = 0
    needs_requiz_count: int = 0


@dataclass
class MistakeListResponse:
    mistakes: list[MistakeRecord]
    summary: ReviewSummary = field(default_factory=ReviewSummary)
    total: int = 0

    def __post_init__(self) -> None:
        self.total = len(self.mistakes)


class MistakeUpdateRequest(BaseModel):
    correction_note: str | None = None
    status: str | None = None
    mastered: bool | None = None


class DailySessionRequest(BaseModel):
    limit: int = 5


@dataclass
class DailySessionResponse:
    mistakes: list[MistakeRecord]
    total: int = 0
    message: str = ""

    def __post_init__(self) -> None:
        self.total = len(self.mistakes)


@dataclass
class MistakeExplanationResponse:
    explanation: str


@dataclass
class StudyDay:
    day: int
    topics: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)


class StudyPlanRequest(BaseModel):
    exam_date: str
    days_before_exam: int = 7


@dataclass
class StudyPlanResponse:
    plan: list[StudyDay] = field(default_factory=list)
    message: str = ""
