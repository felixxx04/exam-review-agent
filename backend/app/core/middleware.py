from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter with per-route limits.

    Limits:
    - /api/chat: 30 requests/minute
    - /api/materials POST: 10 requests/minute
    - All other: 100 requests/minute
    """

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method

        if path == "/api/chat":
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
                content={"detail": "请求过于频繁，请稍后再试"},
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
