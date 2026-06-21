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
    question_id: str
    concept: str
    topic: str
    wrong_answer: str
    correct_answer: str


@dataclass
class MistakeListResponse:
    mistakes: list[MistakeRecord]
    total: int = 0

    def __post_init__(self) -> None:
        self.total = len(self.mistakes)


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
