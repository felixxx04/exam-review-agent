from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class QuotaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_limit: int
    files_used: int
    storage_limit_bytes: int
    storage_used_bytes: int


class AccountDeletionCreatedResponse(BaseModel):
    job_id: str
    status: str
    status_token: str
    attempt_count: int
    error_code: str | None
    error_message: str | None


class AccountDeletionStatusResponse(BaseModel):
    job_id: str
    status: str
    attempt_count: int
    error_code: str | None
    error_message: str | None
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    updated_at: datetime.datetime
