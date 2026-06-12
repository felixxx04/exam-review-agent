from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    material_scope: list[str] | None = None


class ChatEvent:
    content: str
    event: str
    citations: list[dict] | None = None
    error: str | None = None
