from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    REFRESH_COOKIE_NAME,
    AuthenticatedUser,
    get_current_user,
    require_admin,
)
from app.core.config import settings
from app.db.database import get_db
from app.db.models import User
from app.schemas.auth import (
    CreateInviteRequest,
    InviteResponse,
    InviteUpdateRequest,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
    UserStatusRequest,
)
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService, CsrfError, IssuedSession


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


def _session_response(issued: IssuedSession) -> SessionResponse:
    return SessionResponse(
        user=UserResponse.model_validate(issued.user),
        access_expires_at=issued.access_expires_at,
        refresh_expires_at=issued.refresh_expires_at,
    )


def _set_session_cookies(response: Response, issued: IssuedSession) -> None:
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
    }
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        issued.access_token,
        httponly=True,
        path="/",
        max_age=settings.access_token_minutes * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        issued.refresh_token,
        httponly=True,
        path="/api/auth",
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        issued.csrf_token,
        httponly=False,
        path="/",
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        **common,
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(
        ACCESS_COOKIE_NAME,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user_agent, ip_address = _request_metadata(request)
    issued = await AuthService(db).register(
        username=payload.username,
        password=payload.password,
        invite_code=payload.invite_code,
        display_name=payload.display_name,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_session_cookies(response, issued)
    return ApiResponse.ok(data=_session_response(issued))


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user_agent, ip_address = _request_metadata(request)
    issued = await AuthService(db).login(
        username=payload.username,
        password=payload.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_session_cookies(response, issued)
    return ApiResponse.ok(data=_session_response(issued))


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME, "")
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get(CSRF_HEADER_NAME, "")
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(
        csrf_cookie, csrf_header
    ):
        raise CsrfError()
    user_agent, ip_address = _request_metadata(request)
    issued = await AuthService(db).rotate_refresh_token(
        refresh_token=refresh_token,
        csrf_token=csrf_header,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_session_cookies(response, issued)
    return ApiResponse.ok(data=_session_response(issued))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME, "")
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get(CSRF_HEADER_NAME, "")
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(
        csrf_cookie, csrf_header
    ):
        raise CsrfError()
    await AuthService(db).logout(
        refresh_token=refresh_token,
        csrf_token=csrf_header,
    )
    _clear_session_cookies(response)
    return ApiResponse.ok(data={"status": "logged_out"})


@router.get("/me")
async def current_user(
    current: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, current.id)
    return ApiResponse.ok(data=UserResponse.model_validate(user))


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    payload: CreateInviteRequest,
    current: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    actor = await db.get(User, current.id)
    created = await AuthService(db).create_invite(
        actor=actor,
        max_uses=payload.max_uses,
        expires_at=payload.expires_at,
    )
    return ApiResponse.ok(
        data=InviteResponse(
            id=created.invite.id,
            code=created.code,
            max_uses=created.invite.max_uses,
            use_count=created.invite.use_count,
            expires_at=created.invite.expires_at,
            disabled_at=created.invite.disabled_at,
        )
    )


@router.patch("/invites/{invite_id}")
async def update_invite(
    invite_id: int,
    payload: InviteUpdateRequest,
    current: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    actor = await db.get(User, current.id)
    invite = await AuthService(db).set_invite_disabled(
        actor=actor,
        invite_id=invite_id,
        disabled=payload.disabled,
    )
    return ApiResponse.ok(
        data={
            "id": invite.id,
            "disabled": invite.disabled_at is not None,
        }
    )


@router.patch("/users/{user_id}")
async def update_user_status(
    user_id: int,
    payload: UserStatusRequest,
    current: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    actor = await db.get(User, current.id)
    user = await AuthService(db).set_user_disabled(
        actor=actor,
        user_id=user_id,
        disabled=payload.disabled,
    )
    return ApiResponse.ok(data=UserResponse.model_validate(user))
