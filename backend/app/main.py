import asyncio
import ipaddress
import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.account import router as account_router
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.courses import router as courses_router
from app.api.materials import router as materials_router
from app.api.memory import router as memory_router
from app.api.quiz import router as quiz_router
from app.api.review import router as review_router
from app.api.dependencies import get_object_storage
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.middleware import RateLimitMiddleware, UploadBodyLimitMiddleware
from app.db.database import engine
from app.schemas.common import ApiResponse
from app.services.health import (
    DatabaseReadinessProbe,
    ObjectStorageReadinessProbe,
    ReadinessProbe,
    RedisReadinessProbe,
)

logger = logging.getLogger(__name__)

READINESS_TIMEOUT_SECONDS = 3
MIN_JWT_SECRET_LENGTH = 32
INSECURE_JWT_SECRETS = frozenset(
    {
        "change-me-in-production",
        "replace-with-at-least-32-random-characters",
    }
)
S3_BUCKET_PATTERN = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")

EXCEPTION_STATUS: dict[str, int] = {
    "INSUFFICIENT_MATERIAL": 404,
    "LLM_PROVIDER_ERROR": 502,
    "FILE_PARSING_ERROR": 422,
    "RATE_LIMIT_EXCEEDED": 429,
    "AUTH_REQUIRED": 401,
    "INVALID_CREDENTIALS": 401,
    "INVALID_INVITE": 400,
    "CSRF_FAILED": 403,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "QUOTA_EXCEEDED": 409,
    "DUPLICATE_MATERIAL": 409,
    "ACCOUNT_DELETION_IN_PROGRESS": 409,
    "INVALID_FILE_TYPE": 400,
    "INVALID_FILE_SIGNATURE": 400,
    "UNSAFE_ARCHIVE": 400,
    "FILE_TOO_LARGE": 413,
    "INVALID_DOWNLOAD": 400,
    "OBJECT_VERIFICATION_FAILED": 502,
    "OBJECT_STORAGE_UNAVAILABLE": 503,
}


def _validate_settings_on_startup() -> None:
    missing: list[str] = []

    provider_attrs: dict[str, str] = {
        "deepseek": "deepseek_api_key",
        "glm": "glm_api_key",
        "minimax": "minimax_api_key",
        "volcengine": "volcengine_api_key",
    }
    default_provider = settings.default_llm_provider
    attr = provider_attrs.get(default_provider, provider_attrs["deepseek"])
    if not getattr(settings, attr, ""):
        missing.append(attr.upper())

    jwt_secret = settings.jwt_secret.strip()
    if jwt_secret in INSECURE_JWT_SECRETS or len(jwt_secret) < MIN_JWT_SECRET_LENGTH:
        missing.append("JWT_SECRET (must not be the default value)")
    s3_access_key_id = settings.s3_access_key_id
    s3_secret = settings.s3_secret_access_key.get_secret_value()
    if _is_missing_or_placeholder(s3_access_key_id):
        missing.append("S3_ACCESS_KEY_ID")
    if _is_missing_or_placeholder(s3_secret):
        missing.append("S3_SECRET_ACCESS_KEY")
    bucket = settings.s3_bucket.strip()
    if not S3_BUCKET_PATTERN.fullmatch(bucket):
        missing.append("S3_BUCKET")
    for name, endpoint in (
        ("S3_ENDPOINT_URL", settings.s3_endpoint_url),
        ("S3_PUBLIC_ENDPOINT_URL", settings.s3_public_endpoint_url),
    ):
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            missing.append(name)
        elif parsed.scheme == "http" and not _is_local_s3_endpoint(parsed):
            if name == "S3_ENDPOINT_URL" and settings.s3_allow_insecure_http:
                continue
            missing.append(name)
    if not 1 <= settings.s3_presigned_url_ttl_seconds <= 900:
        missing.append("S3_PRESIGNED_URL_TTL_SECONDS")
    if missing:
        msg = f"Missing or invalid required settings: {', '.join(missing)}"
        logger.critical(msg)
        raise SystemExit(msg)


def _is_local_s3_endpoint(parsed) -> bool:
    host = parsed.hostname
    if host == "localhost":
        return True
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_missing_or_placeholder(value: str) -> bool:
    normalized = value.strip()
    return not normalized or normalized.startswith("replace-with-")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_settings_on_startup()
    yield


app = FastAPI(
    title="Exam Review Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(UploadBodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth_router)
app.include_router(account_router)
app.include_router(courses_router)
app.include_router(materials_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(memory_router)
app.include_router(quiz_router)
app.include_router(review_router)


def get_readiness_probes() -> list[ReadinessProbe]:
    return [
        DatabaseReadinessProbe(engine),
        RedisReadinessProbe(settings.redis_url),
        ObjectStorageReadinessProbe(get_object_storage()),
    ]


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    status_code = EXCEPTION_STATUS.get(exc.code, 500)
    return JSONResponse(
        status_code=status_code,
        content=ApiResponse.fail(code=exc.code, message=exc.message).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse.fail(code="HTTP_ERROR", message=exc.detail).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=ApiResponse.fail(
            code="INTERNAL_ERROR", message="Internal server error"
        ).model_dump(),
    )


@app.get("/api/health")
async def health():
    return ApiResponse.ok(
        data={"status": "ok", "default_provider": settings.default_llm_provider}
    )


@app.get("/health/live")
async def liveness():
    return ApiResponse.ok(data={"status": "alive"})


@app.get("/health/ready")
async def readiness(
    probes: list[ReadinessProbe] = Depends(get_readiness_probes),
):
    checks: dict[str, str] = {}
    unavailable = False
    for probe in probes:
        try:
            async with asyncio.timeout(READINESS_TIMEOUT_SECONDS):
                await probe.check()
            checks[probe.name] = "ok"
        except Exception:
            logger.warning("Readiness probe failed: %s", probe.name, exc_info=True)
            checks[probe.name] = "unavailable"
            unavailable = True

    if unavailable:
        response = ApiResponse.fail(
            code="DEPENDENCY_UNAVAILABLE",
            message="One or more required dependencies are unavailable.",
        ).model_dump()
        response["data"] = {"status": "not_ready", "checks": checks}
        return JSONResponse(status_code=503, content=response)

    return ApiResponse.ok(data={"status": "ready", "checks": checks})
