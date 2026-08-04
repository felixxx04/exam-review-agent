from __future__ import annotations

import asyncio
import datetime

import pytest
from jose import jwt
from sqlalchemy import select

from app.core.config import settings
from app.db.models import InviteCode, RefreshToken, User
from app.services.auth_service import (
    AuthService,
    CsrfError,
    ForbiddenError,
    InvalidCredentialsError,
    InvalidInviteError,
    InvalidSessionError,
    ResourceNotFoundError,
    decode_access_token,
    hash_password,
    hash_password_async,
    hash_token,
    normalize_username,
    verify_password,
    verify_password_async,
)


async def _admin(db_session) -> User:
    user = User(
        username="admin",
        email=None,
        hashed_password=hash_password("Admin-pass-123"),
        display_name="Admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_register_consumes_invite_and_hashes_password(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    created = await service.create_invite(
        actor=admin,
        max_uses=1,
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
    )

    issued = await service.register(
        username="student_one",
        password="Student-pass-123",
        invite_code=created.code,
        display_name="Student One",
        user_agent="pytest",
        ip_address="127.0.0.1",
    )

    invite = await db_session.get(InviteCode, created.invite.id)
    assert issued.user.username == "student_one"
    assert issued.user.role == "user"
    assert issued.user.hashed_password.startswith("$argon2id$")
    assert verify_password("Student-pass-123", issued.user.hashed_password)
    assert invite is not None
    assert invite.use_count == 1
    assert invite.code_hash == hash_token(created.code)
    assert created.code not in invite.code_hash


@pytest.mark.asyncio
async def test_invite_constraints_and_failed_registration_are_transactional(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    first = await service.create_invite(actor=admin, max_uses=1)

    await service.register(
        username="existing_user",
        password="Student-pass-123",
        invite_code=first.code,
    )
    with pytest.raises(InvalidInviteError):
        await service.register(
            username="second_user",
            password="Student-pass-123",
            invite_code=first.code,
        )

    second = await service.create_invite(actor=admin, max_uses=2)
    with pytest.raises(InvalidCredentialsError):
        await service.register(
            username="existing_user",
            password="Another-pass-123",
            invite_code=second.code,
        )
    invite = await db_session.get(InviteCode, second.invite.id)
    assert invite is not None
    assert invite.use_count == 0


@pytest.mark.asyncio
async def test_expired_and_disabled_invites_are_rejected(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    expired = await service.create_invite(actor=admin)
    expired.invite.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        seconds=1
    )
    await db_session.commit()

    with pytest.raises(InvalidInviteError):
        await service.register(
            username="expired_invite_user",
            password="Student-pass-123",
            invite_code=expired.code,
        )

    disabled = await service.create_invite(actor=admin)
    await service.set_invite_disabled(
        actor=admin,
        invite_id=disabled.invite.id,
        disabled=True,
    )
    with pytest.raises(InvalidInviteError):
        await service.register(
            username="disabled_invite_user",
            password="Student-pass-123",
            invite_code=disabled.code,
        )

    await service.set_invite_disabled(
        actor=admin,
        invite_id=disabled.invite.id,
        disabled=False,
    )
    issued = await service.register(
        username="reenabled_invite_user",
        password="Student-pass-123",
        invite_code=disabled.code,
    )
    assert issued.user.username == "reenabled_invite_user"


@pytest.mark.asyncio
async def test_refresh_rotation_stores_only_hashes_and_rejects_reuse(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin, max_uses=1)
    initial = await service.register(
        username="rotate_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )

    stored = (
        await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(initial.refresh_token)
            )
        )
    ).scalar_one()
    assert stored.token_hash != initial.refresh_token
    assert stored.csrf_token_hash == hash_token(initial.csrf_token)

    rotated = await service.rotate_refresh_token(
        refresh_token=initial.refresh_token,
        csrf_token=initial.csrf_token,
    )
    await db_session.refresh(stored)
    assert rotated.refresh_token != initial.refresh_token
    assert rotated.csrf_token != initial.csrf_token
    assert stored.revoked_at is not None
    assert stored.replaced_by_token_id is not None

    with pytest.raises(InvalidSessionError):
        await service.rotate_refresh_token(
            refresh_token=initial.refresh_token,
            csrf_token=initial.csrf_token,
        )

    active = (
        await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.session_id == initial.session_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    assert active == []


@pytest.mark.asyncio
async def test_refresh_rejects_invalid_csrf_token(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin)
    initial = await service.register(
        username="csrf_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )

    with pytest.raises(CsrfError):
        await service.rotate_refresh_token(
            refresh_token=initial.refresh_token,
            csrf_token="incorrect-csrf-token",
        )


@pytest.mark.asyncio
async def test_unknown_user_login_does_not_rehash_dummy_password(
    db_session, monkeypatch
):
    service = AuthService(db_session)

    def fail_if_called(_password: str) -> str:
        raise AssertionError("dummy password hash must be precomputed")

    monkeypatch.setattr(
        "app.services.auth_service.hash_password",
        fail_if_called,
    )
    with pytest.raises(InvalidCredentialsError):
        await service.login(
            username="missing_user",
            password="Student-pass-123",
        )


def test_auth_helpers_reject_invalid_values():
    assert normalize_username("  Student_One  ") == "student_one"
    assert verify_password("wrong-password", hash_password("Student-pass-123")) is False
    assert verify_password("Student-pass-123", "not-an-argon2-hash") is False

    with pytest.raises(InvalidCredentialsError):
        normalize_username("ab")
    with pytest.raises(InvalidCredentialsError):
        normalize_username("bad username")
    with pytest.raises(InvalidSessionError):
        decode_access_token("not-a-jwt")


@pytest.mark.asyncio
async def test_argon2_async_helpers_offload_work_from_event_loop(monkeypatch):
    calls: list[tuple[object, tuple[object, ...]]] = []

    async def fake_to_thread(function, *args):
        calls.append((function, args))
        return function(*args)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    password_hash = await hash_password_async("Student-pass-123")
    assert await verify_password_async("Student-pass-123", password_hash)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_invite_and_admin_input_boundaries_are_enforced(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    regular = User(
        username="regular_boundary_user",
        email=None,
        hashed_password=hash_password("Student-pass-123"),
        display_name="Regular",
        role="user",
    )
    db_session.add(regular)
    await db_session.commit()

    with pytest.raises(InvalidInviteError):
        await service.create_invite(actor=admin, max_uses=0)
    with pytest.raises(InvalidInviteError):
        await service.create_invite(
            actor=admin,
            expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
        )
    with pytest.raises(ForbiddenError):
        await service.create_invite(actor=regular)


@pytest.mark.asyncio
async def test_expired_or_missing_refresh_sessions_are_rejected(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin)
    issued = await service.register(
        username="expired_refresh_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )
    stored = (
        await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(issued.refresh_token)
            )
        )
    ).scalar_one()
    stored.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)
    await db_session.commit()

    with pytest.raises(InvalidSessionError):
        await service.rotate_refresh_token(
            refresh_token=issued.refresh_token,
            csrf_token=issued.csrf_token,
        )
    with pytest.raises(InvalidSessionError):
        await service.rotate_refresh_token(
            refresh_token="missing-refresh-token",
            csrf_token="missing-csrf-token",
        )


@pytest.mark.asyncio
async def test_remaining_session_and_resource_error_paths(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin)
    issued = await service.register(
        username="session_error_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )

    with pytest.raises(CsrfError):
        await service.logout(
            refresh_token=issued.refresh_token,
            csrf_token="wrong-csrf-token",
        )
    with pytest.raises(InvalidSessionError):
        await service.logout(
            refresh_token="missing-refresh-token",
            csrf_token="missing-csrf-token",
        )
    with pytest.raises(ResourceNotFoundError):
        await service.set_invite_disabled(
            actor=admin,
            invite_id=999999,
            disabled=True,
        )
    with pytest.raises(InvalidSessionError):
        await service.validate_access_token(
            jwt.encode(
                {"sub": str(issued.user.id), "type": "access"},
                settings.jwt_secret,
                algorithm="HS256",
            )
        )
    with pytest.raises(InvalidCredentialsError):
        await service.register(
            username="short_password_user",
            password="too-short",
            invite_code=invite.code,
        )
    with pytest.raises(ResourceNotFoundError):
        await service.set_user_disabled(
            actor=admin,
            user_id=999999,
            disabled=True,
        )

    await service.logout(
        refresh_token=issued.refresh_token,
        csrf_token=issued.csrf_token,
    )
    with pytest.raises(InvalidSessionError):
        await service.validate_access_token(issued.access_token)


@pytest.mark.asyncio
async def test_refresh_rejects_user_disabled_outside_session_revocation(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin)
    issued = await service.register(
        username="manually_disabled_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )
    issued.user.is_disabled = True
    issued.user.disabled_at = datetime.datetime.now(datetime.UTC)
    await db_session.commit()

    with pytest.raises(InvalidSessionError):
        await service.rotate_refresh_token(
            refresh_token=issued.refresh_token,
            csrf_token=issued.csrf_token,
        )


def test_access_token_type_and_nullable_timestamp_are_validated():
    refresh_payload = jwt.encode(
        {"sub": "1", "type": "refresh"},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidSessionError):
        decode_access_token(refresh_payload)

    assert AuthService._aware(None) == datetime.datetime.min.replace(
        tzinfo=datetime.UTC
    )


@pytest.mark.asyncio
async def test_logout_revokes_only_the_selected_session(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin, max_uses=1)
    registered = await service.register(
        username="multi_session_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )
    second = await service.login(
        username="multi_session_user",
        password="Student-pass-123",
    )

    await service.logout(
        refresh_token=registered.refresh_token,
        csrf_token=registered.csrf_token,
    )

    with pytest.raises(InvalidSessionError):
        await service.rotate_refresh_token(
            refresh_token=registered.refresh_token,
            csrf_token=registered.csrf_token,
        )
    refreshed_second = await service.rotate_refresh_token(
        refresh_token=second.refresh_token,
        csrf_token=second.csrf_token,
    )
    assert refreshed_second.session_id == second.session_id


@pytest.mark.asyncio
async def test_disabled_user_cannot_login_or_refresh_and_sessions_are_revoked(db_session):
    service = AuthService(db_session)
    admin = await _admin(db_session)
    invite = await service.create_invite(actor=admin, max_uses=1)
    issued = await service.register(
        username="disabled_user",
        password="Student-pass-123",
        invite_code=invite.code,
    )

    await service.set_user_disabled(actor=admin, user_id=issued.user.id, disabled=True)

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            username="disabled_user",
            password="Student-pass-123",
        )
    with pytest.raises(InvalidSessionError):
        await service.rotate_refresh_token(
            refresh_token=issued.refresh_token,
            csrf_token=issued.csrf_token,
        )
    tokens = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == issued.user.id)
        )
    ).scalars().all()
    assert tokens
    assert all(token.revoked_at is not None for token in tokens)
