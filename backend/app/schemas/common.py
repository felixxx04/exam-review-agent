"""Unified API response envelope."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: dict | None = None

    @classmethod
    def ok(cls, data: T, meta: dict | None = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, meta=meta)

    @classmethod
    def fail(cls, code: str, message: str) -> "ApiResponse":
        return cls(success=False, error=ErrorDetail(code=code, message=message))
