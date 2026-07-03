from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LearningProfileResponse(BaseModel):
    current_subject: str | None = None
    review_goal: str | None = None
    weak_concepts: list[str]
    frequent_questions: list[str]
    active_materials: list[str]
    preferences: dict
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
