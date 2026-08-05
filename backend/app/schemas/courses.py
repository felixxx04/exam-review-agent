from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, field_validator


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("课程名称不能为空")
    return normalized


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    exam_date: datetime.date | None = None
    long_term_goal: str | None = Field(default=None, max_length=2000)
    daily_available_minutes: int = Field(default=60, ge=1, le=1440)

    _normalize_name = field_validator("name")(_strip_required)
    _normalize_optional = field_validator("description", "long_term_goal")(
        _strip_optional
    )


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    exam_date: datetime.date | None = None
    long_term_goal: str | None = Field(default=None, max_length=2000)
    daily_available_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_default: bool | None = None

    _normalize_name = field_validator("name")(
        lambda value: _strip_required(value) if value is not None else None
    )
    _normalize_optional = field_validator("description", "long_term_goal")(
        _strip_optional
    )


class CourseResponse(BaseModel):
    id: int
    name: str
    description: str | None
    exam_date: datetime.date | None
    long_term_goal: str | None
    daily_available_minutes: int
    is_default: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CourseListResponse(BaseModel):
    courses: list[CourseResponse]
    total: int
