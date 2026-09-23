from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class MaterialJobResponse(BaseModel):
    public_id: str
    material_id: int
    status: str
    progress_percent: int
    current_step: str | None = None
    attempt_count: int
    max_attempts: int
    priority: int
    available_at: datetime.datetime
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None

    model_config = {"from_attributes": True}


class MaterialJobPriorityRequest(BaseModel):
    priority: int = Field(ge=-100, le=100)
