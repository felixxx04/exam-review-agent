import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.exceptions import RateLimitExceededError


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds

        self.hits[client_ip] = [
            t for t in self.hits[client_ip] if t > window_start
        ]

        if len(self.hits[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": RateLimitExceededError().message},
            )

        self.hits[client_ip].append(now)
        return await call_next(request)
