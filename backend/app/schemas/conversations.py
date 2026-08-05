from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationResponse(BaseModel):
    id: int
    course_id: int
    available_minutes_override: int | None = None
    title: str
    summary: str | None = None
    message_count: int
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


class ConversationCreateRequest(BaseModel):
    course_id: int | None = None
    available_minutes_override: int | None = Field(default=None, ge=1, le=1440)


class ConversationMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    material_scope: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    conversation_id: int
    messages: list[ConversationMessageResponse]
