from __future__ import annotations

import asyncio
import datetime
import hashlib
import secrets
import uuid
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.db.models import InviteCode, RefreshToken, User


JWT_ALGORITHM = "HS256"
DEFAULT_INVITE_LIFETIME = datetime.timedelta(days=7)
PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("timing-only-password")


class InvalidCredentialsError(AppException):
    def __init__(self, message: str = "Invalid username or password") -> None:
        super().__init__(message, "INVALID_CREDENTIALS")


class UsernameUnavailableError(InvalidCredentialsError):
    def __init__(self) -> None:
        super().__init__("Username is unavailable")
        self.code = "CONFLICT"


class InvalidInviteError(AppException):
    def __init__(self) -> None:
        super().__init__("Invite code is invalid or unavailable", "INVALID_INVITE")


class InvalidSessionError(AppException):
    def __init__(self) -> None:
        super().__init__("Session is invalid or expired", "AUTH_REQUIRED")


class CsrfError(AppException):
    def __init__(self) -> None:
        super().__init__("CSRF validation failed", "CSRF_FAILED")


class ForbiddenError(AppException):
    def __init__(self) -> None:
        super().__init__("Insufficient permissions", "FORBIDDEN")


class ResourceNotFoundError(AppException):
    def __init__(self) -> None:
        super().__init__("Resource not found", "NOT_FOUND")


@dataclass(frozen=True)
class CreatedInvite:
    invite: InviteCode
    code: str


@dataclass(frozen=True)
class IssuedSession:
    user: User
    session_id: str
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime.datetime
    refresh_expires_at: datetime.datetime


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not 3 <= len(normalized) <= 32:
        raise InvalidCredentialsError("Username must contain 3 to 32 characters")
    if not all(character.isalnum() or character in "_-." for character in normalized):
        raise InvalidCredentialsError("Username contains unsupported characters")
    return normalized


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidSessionError() from exc
    if payload.get("type") != "access":
        raise InvalidSessionError()
    return payload


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_invite(
        self,
        *,
        actor: User,
        max_uses: int = 1,
        expires_at: datetime.datetime | None = None,
    ) -> CreatedInvite:
        self._require_admin(actor)
        if not 1 <= max_uses <= 100:
            raise InvalidInviteError()
        now = self._now()
        expiry = (
            self._aware(expires_at) if expires_at else now + DEFAULT_INVITE_LIFETIME
        )
        if expiry <= now:
            raise InvalidInviteError()

        code = secrets.token_urlsafe(24)
        invite = InviteCode(
            code_hash=hash_token(code),
            created_by_user_id=actor.id,
            max_uses=max_uses,
            use_count=0,
            expires_at=expiry,
        )
        self.db.add(invite)
        await self.db.commit()
        await self.db.refresh(invite)
        return CreatedInvite(invite=invite, code=code)

    async def set_invite_disabled(
        self, *, actor: User, invite_id: int, disabled: bool
    ) -> InviteCode:
        self._require_admin(actor)
        invite = await self.db.get(InviteCode, invite_id)
        if invite is None:
            raise ResourceNotFoundError()
        invite.disabled_at = self._now() if disabled else None
        await self.db.commit()
        await self.db.refresh(invite)
        return invite

    async def register(
        self,
        *,
        username: str,
        password: str,
        invite_code: str,
        display_name: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedSession:
        normalized = normalize_username(username)
        self._validate_password(password)
        now = self._now()
        try:
            result = await self.db.execute(
                select(InviteCode)
                .where(InviteCode.code_hash == hash_token(invite_code))
                .with_for_update()
            )
            invite = result.scalar_one_or_none()
            if not self._invite_is_available(invite, now):
                raise InvalidInviteError()

            existing = await self.db.execute(
                select(User.id).where(User.username == normalized)
            )
            if existing.scalar_one_or_none() is not None:
                raise UsernameUnavailableError()

            user = User(
                username=normalized,
                email=None,
                hashed_password=await hash_password_async(password),
                display_name=(display_name or username).strip()[:100] or normalized,
                role="user",
            )
            self.db.add(user)
            await self.db.flush()
            invite.use_count += 1
            invite.last_used_at = now
            issued = await self._issue_session(
                user,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            await self.db.commit()
            return issued
        except (InvalidInviteError, UsernameUnavailableError):
            raise
        except IntegrityError as exc:
            await self.db.rollback()
            raise UsernameUnavailableError() from exc

    async def login(
        self,
        *,
        username: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedSession:
        normalized = username.strip().casefold()
        result = await self.db.execute(select(User).where(User.username == normalized))
        user = result.scalar_one_or_none()
        password_hash = (
            user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
        )
        valid_password = await verify_password_async(password, password_hash)
        if user is None or not valid_password or user.is_disabled:
            raise InvalidCredentialsError()

        issued = await self._issue_session(
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.db.commit()
        return issued

    async def rotate_refresh_token(
        self,
        *,
        refresh_token: str,
        csrf_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedSession:
        now = self._now()
        result = await self.db.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_token))
            .with_for_update()
        )
        current = result.scalar_one_or_none()
        if current is None:
            raise InvalidSessionError()
        if current.revoked_at is not None:
            await self._revoke_session(current.session_id, now)
            await self.db.commit()
            raise InvalidSessionError()
        if current.expires_at is None or self._aware(current.expires_at) <= now:
            await self._revoke_session(current.session_id, now)
            await self.db.commit()
            raise InvalidSessionError()
        if not secrets.compare_digest(current.csrf_token_hash, hash_token(csrf_token)):
            raise CsrfError()

        user = await self.db.get(User, current.user_id)
        if user is None or user.is_disabled:
            await self._revoke_session(current.session_id, now)
            await self.db.commit()
            raise InvalidSessionError()

        current.revoked_at = now
        current.last_used_at = now
        issued, replacement = await self._build_session(
            user,
            session_id=current.session_id,
            user_agent=user_agent or current.user_agent,
            ip_address=ip_address or current.ip_address,
        )
        await self.db.flush()
        current.replaced_by_token_id = replacement.id
        await self.db.commit()
        return issued

    async def logout(self, *, refresh_token: str, csrf_token: str) -> None:
        result = await self.db.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_token))
            .with_for_update()
        )
        token = result.scalar_one_or_none()
        if token is None or token.revoked_at is not None:
            raise InvalidSessionError()
        if not secrets.compare_digest(token.csrf_token_hash, hash_token(csrf_token)):
            raise CsrfError()
        await self._revoke_session(token.session_id, self._now())
        await self.db.commit()

    async def validate_access_token(self, token: str) -> tuple[User, dict]:
        payload = decode_access_token(token)
        try:
            user_id = int(payload["sub"])
            session_id = str(payload["sid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidSessionError() from exc

        user = await self.db.get(User, user_id)
        if user is None or user.is_disabled:
            raise InvalidSessionError()
        active = await self.db.execute(
            select(RefreshToken.id).where(
                RefreshToken.user_id == user.id,
                RefreshToken.session_id == session_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > self._now(),
            )
        )
        if active.scalar_one_or_none() is None:
            raise InvalidSessionError()
        return user, payload

    async def set_user_disabled(
        self, *, actor: User, user_id: int, disabled: bool
    ) -> User:
        return await self.update_user(
            actor=actor,
            user_id=user_id,
            disabled=disabled,
        )

    async def update_user(
        self,
        *,
        actor: User,
        user_id: int,
        disabled: bool | None = None,
        file_limit: int | None = None,
        storage_limit_bytes: int | None = None,
    ) -> User:
        self._require_admin(actor)
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ResourceNotFoundError()

        if file_limit is not None:
            user.file_limit = file_limit
        if storage_limit_bytes is not None:
            user.storage_limit_bytes = storage_limit_bytes
        if disabled is not None:
            now = self._now()
            user.is_disabled = disabled
            user.disabled_at = now if disabled else None
        if disabled is True:
            await self.db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def _issue_session(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> IssuedSession:
        issued, _ = await self._build_session(
            user,
            session_id=uuid.uuid4().hex,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return issued

    async def _build_session(
        self,
        user: User,
        *,
        session_id: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> tuple[IssuedSession, RefreshToken]:
        now = self._now()
        access_expires_at = now + datetime.timedelta(
            minutes=settings.access_token_minutes
        )
        refresh_expires_at = now + datetime.timedelta(days=settings.refresh_token_days)
        raw_refresh = secrets.token_urlsafe(48)
        raw_csrf = secrets.token_urlsafe(32)
        csrf_hash = hash_token(raw_csrf)
        refresh = RefreshToken(
            user_id=user.id,
            session_id=session_id,
            token_hash=hash_token(raw_refresh),
            csrf_token_hash=csrf_hash,
            expires_at=refresh_expires_at,
            user_agent=(user_agent or "")[:512] or None,
            ip_address=(ip_address or "")[:64] or None,
        )
        self.db.add(refresh)
        access = jwt.encode(
            {
                "sub": str(user.id),
                "username": user.username,
                "role": user.role,
                "sid": session_id,
                "csrf": csrf_hash,
                "type": "access",
                "jti": uuid.uuid4().hex,
                "iat": now,
                "exp": access_expires_at,
            },
            settings.jwt_secret,
            algorithm=JWT_ALGORITHM,
        )
        return (
            IssuedSession(
                user=user,
                session_id=session_id,
                access_token=access,
                refresh_token=raw_refresh,
                csrf_token=raw_csrf,
                access_expires_at=access_expires_at,
                refresh_expires_at=refresh_expires_at,
            ),
            refresh,
        )

    async def _revoke_session(
        self, session_id: str, revoked_at: datetime.datetime
    ) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.session_id == session_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    @staticmethod
    def _invite_is_available(invite: InviteCode | None, now: datetime.datetime) -> bool:
        return bool(
            invite is not None
            and invite.disabled_at is None
            and invite.use_count < invite.max_uses
            and AuthService._aware(invite.expires_at) > now
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        if not 10 <= len(password) <= 128:
            raise InvalidCredentialsError("Password must contain 10 to 128 characters")

    @staticmethod
    def _require_admin(user: User) -> None:
        if user.role != "admin" or user.is_disabled:
            raise ForbiddenError()

    @staticmethod
    def _now() -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)

    @staticmethod
    def _aware(value: datetime.datetime | None) -> datetime.datetime:
        if value is None:
            return datetime.datetime.min.replace(tzinfo=datetime.UTC)
        return value if value.tzinfo else value.replace(tzinfo=datetime.UTC)
