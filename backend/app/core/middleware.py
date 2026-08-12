from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from app.core.config import settings


MULTIPART_ENVELOPE_ALLOWANCE_BYTES = 64 * 1024


class _UploadBodyTooLarge(BaseException):
    """Internal control flow that must bypass the application's error handler."""


class UploadBodyLimitMiddleware:
    """Bound uploads before FastAPI can spool multipart data to temporary storage."""

    def __init__(self, app, max_size_bytes: int | None = None) -> None:
        self.app = app
        self._max_size_bytes = max_size_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_material_upload(scope):
            await self.app(scope, receive, send)
            return

        maximum_size = self._maximum_size_bytes(scope)
        content_length = self._content_length(scope)
        if content_length is not None and content_length > maximum_size:
            await self._send_too_large(scope, receive, send)
            return

        received_size = 0

        async def limited_receive() -> Message:
            nonlocal received_size
            message = await receive()
            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))
                if received_size > maximum_size:
                    raise _UploadBodyTooLarge
            return message

        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _UploadBodyTooLarge:
            if response_started:
                raise
            await self._send_too_large(scope, receive, send)

    def _maximum_size_bytes(self, scope: Scope) -> int:
        if self._max_size_bytes is not None:
            return self._max_size_bytes
        configured_file_size = max(settings.max_upload_size_mb, 0) * 1024 * 1024
        if self._is_multipart_form_data(scope):
            return configured_file_size + MULTIPART_ENVELOPE_ALLOWANCE_BYTES
        return configured_file_size

    @staticmethod
    def _is_material_upload(scope: Scope) -> bool:
        return (
            scope.get("method") == "POST"
            and scope.get("path", "").rstrip("/") == "/api/materials"
        )

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                parsed = int(value)
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
        return None

    @staticmethod
    def _is_multipart_form_data(scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-type":
                return value.lower().startswith(b"multipart/form-data")
        return False

    @staticmethod
    async def _send_too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": "上传请求超过允许的文件大小",
                },
                "meta": None,
            },
        )
        await response(scope, receive, send)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter with per-route limits.

    Limits:
    - /api/chat: 30 requests/minute
    - /api/materials POST: 10 requests/minute
    - All other: 100 requests/minute
    """

    _instance: "RateLimitMiddleware | None" = None

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)
        RateLimitMiddleware._instance = self

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance._requests.clear()

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method

        if path in {"/api/auth/login", "/api/auth/register"} and method == "POST":
            limit, window = 5, 60
        elif path == "/api/auth/refresh" and method == "POST":
            limit, window = 20, 60
        elif path == "/api/chat":
            limit, window = 30, 60
        elif path == "/api/materials" and method == "POST":
            limit, window = 10, 60
        else:
            limit, window = 100, 60

        key = f"{client_ip}:{path}:{method}"
        now = time.time()
        cutoff = now - window

        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

        if len(self._requests[key]) >= limit:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "请求过于频繁，请稍后再试",
                    },
                    "meta": None,
                },
            )

        self._requests[key].append(now)
        return await call_next(request)


class PromptInjectionGuard:
    """Lightweight prompt injection detection."""

    SUSPICIOUS_PATTERNS = [
        "ignore previous instructions",
        "ignore all instructions",
        "system prompt",
        "<|im_start|>",
        "<|im_end|>",
        "</system>",
        "你是一个",
        "你的角色是",
    ]

    @classmethod
    def check(cls, text: str) -> bool:
        """Return True if text appears safe, False if suspicious."""
        text_lower = text.lower()
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if pattern.lower() in text_lower:
                return False
        return True
