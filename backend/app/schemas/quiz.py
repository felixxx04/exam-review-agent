"""Quiz schemas for request/response serialization."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Question:
    """A single quiz question generated from source material."""

    question: str
    options: list[str]
    correct: str
    explanation: str
    source_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class QuizRequest:
    """Request to generate a quiz."""

    topic: str
    difficulty: float = 0.5
    count: int = 5
    material_scope: list[str] | None = None


@dataclass
class QuizResponse:
    """Response containing generated quiz questions."""

    questions: list[Question]
    topic: str = ""
    total: int = 0

    def __post_init__(self) -> None:
        self.total = len(self.questions)
