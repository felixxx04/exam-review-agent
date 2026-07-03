from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    material_scope: list[str] | None = None


class SSEMessage(BaseModel):
    event: str
    data: str = ""
    citations: list[dict] | None = None
    quiz: dict | None = None
    error: str | None = None
