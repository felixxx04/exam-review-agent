from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from app.core.auth import AuthenticatedUser, get_current_user, require_admin
from app.db.database import (
    TENANT_USER_ID_KEY,
    _set_tenant_context_after_begin,
    bind_tenant_context,
)
from app.services.auth_service import AuthService, CsrfError, ForbiddenError, hash_token


def _request(method: str, *headers: tuple[bytes, bytes]) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/test",
            "headers": list(headers),
        }
    )


@pytest.mark.asyncio
async def test_bearer_authentication_binds_postgres_tenant_context(monkeypatch):
    user = SimpleNamespace(id=42, username="student", role="user")

    async def validate_access_token(_service, token: str):
        assert token == "access-token"
        return user, {"sid": "session-42"}

    monkeypatch.setattr(AuthService, "validate_access_token", validate_access_token)
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.execute = AsyncMock()

    current = await get_current_user(
        _request("POST", (b"authorization", b"Bearer access-token")),
        db,
    )

    assert current == AuthenticatedUser(
        id=42,
        username="student",
        role="user",
        session_id="session-42",
    )
    assert current.subject == "42"
    statement, parameters = db.execute.await_args.args
    assert "app.current_user_id" in str(statement)
    assert parameters == {"user_id": "42"}


@pytest.mark.asyncio
async def test_tenant_context_binding_covers_current_and_future_transactions():
    db = MagicMock()
    db.sync_session.info = {}
    db.get_bind.return_value.dialect.name = "postgresql"
    db.in_transaction.return_value = True
    db.execute = AsyncMock()

    await bind_tenant_context(db, 42)

    assert db.sync_session.info[TENANT_USER_ID_KEY] == "42"
    statement, parameters = db.execute.await_args.args
    assert "app.current_user_id" in str(statement)
    assert parameters == {"user_id": "42"}

    connection = MagicMock()
    connection.dialect.name = "postgresql"
    _set_tenant_context_after_begin(db.sync_session, None, connection)
    _set_tenant_context_after_begin(db.sync_session, None, connection)

    assert connection.execute.call_count == 2
    for call in connection.execute.call_args_list:
        statement, parameters = call.args
        assert "app.current_user_id" in str(statement)
        assert parameters == {"user_id": "42"}


@pytest.mark.asyncio
async def test_cookie_authentication_requires_bound_double_submit_csrf(monkeypatch):
    user = SimpleNamespace(id=7, username="student", role="user")

    async def validate_access_token(_service, token: str):
        assert token == "cookie-access"
        return user, {"sid": "session-7", "csrf": hash_token("csrf-value")}

    monkeypatch.setattr(AuthService, "validate_access_token", validate_access_token)
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"

    current = await get_current_user(
        _request(
            "POST",
            (b"cookie", b"access_token=cookie-access; csrf_token=csrf-value"),
            (b"x-csrf-token", b"csrf-value"),
        ),
        db,
    )
    assert current.id == 7

    with pytest.raises(CsrfError):
        await get_current_user(
            _request(
                "POST",
                (b"cookie", b"access_token=cookie-access; csrf_token=csrf-value"),
                (b"x-csrf-token", b"wrong-value"),
            ),
            db,
        )


@pytest.mark.asyncio
async def test_admin_dependency_accepts_admin_and_rejects_regular_user():
    admin = AuthenticatedUser(1, "admin", "admin", "session-admin")
    regular = AuthenticatedUser(2, "student", "user", "session-user")

    assert await require_admin(admin) is admin
    with pytest.raises(ForbiddenError):
        await require_admin(regular)
