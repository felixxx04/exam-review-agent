"""Quiz schemas for request/response serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


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


class QuizSubmitRequest(BaseModel):
    question_id: str
    correct_answer: str
    student_answer: str
    question_type: str = "multiple_choice"
    concept: str = ""
    topic: str = ""
    question_text: str = ""
    explanation: str = ""
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_material: str | None = None


def to_quiz_payload(response: QuizResponse, difficulty: float = 0.5) -> dict[str, Any]:
    questions = []
    for index, question in enumerate(response.questions, start=1):
        questions.append(
            {
                "id": f"q-{index}",
                "question": question.question,
                "question_type": "multiple_choice" if question.options else "fill_blank",
                "options": question.options,
                "correct": question.correct,
                "explanation": question.explanation,
                "difficulty": difficulty,
                "topic": response.topic,
                "source_chunk_ids": question.source_chunk_ids,
            }
        )

    return {
        "questions": questions,
        "topic": response.topic,
        "total": len(questions),
    }
