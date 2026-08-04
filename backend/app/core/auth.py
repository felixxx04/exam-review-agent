from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import bind_tenant_context, get_db
from app.services.auth_service import (
    AuthService,
    CsrfError,
    ForbiddenError,
    InvalidSessionError,
    hash_token,
)


ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    username: str
    role: str
    session_id: str

    @property
    def subject(self) -> str:
        return str(self.id)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    authorization = request.headers.get("Authorization", "")
    cookie_authenticated = False
    if authorization:
        if not authorization.startswith("Bearer ") or not authorization[7:].strip():
            raise InvalidSessionError()
        access_token = authorization[7:].strip()
    else:
        access_token = request.cookies.get(ACCESS_COOKIE_NAME, "")
        cookie_authenticated = True
    if not access_token:
        raise InvalidSessionError()

    user, payload = await AuthService(db).validate_access_token(access_token)
    if cookie_authenticated and request.method in UNSAFE_METHODS:
        cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME, "")
        header_csrf = request.headers.get(CSRF_HEADER_NAME, "")
        expected_hash = str(payload.get("csrf") or "")
        if (
            not cookie_csrf
            or not header_csrf
            or not secrets.compare_digest(cookie_csrf, header_csrf)
            or not secrets.compare_digest(hash_token(header_csrf), expected_hash)
        ):
            raise CsrfError()

    await bind_tenant_context(db, user.id)
    return AuthenticatedUser(
        id=user.id,
        username=user.username,
        role=user.role,
        session_id=str(payload["sid"]),
    )


async def require_admin(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if current_user.role != "admin":
        raise ForbiddenError()
    return current_user
