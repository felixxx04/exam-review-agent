from __future__ import annotations

import pytest

from app.cli import create_admin as create_admin_module
from app.cli.create_admin import _run, create_admin


@pytest.mark.asyncio
async def test_create_admin_bootstraps_first_administrator(db_session):
    admin = await create_admin(
        db_session,
        username="local_admin",
        password="Admin-pass-123",
        display_name="Local Admin",
    )

    assert admin.username == "local_admin"
    assert admin.role == "admin"
    assert admin.is_disabled is False


@pytest.mark.asyncio
async def test_create_admin_rejects_duplicate_username(db_session):
    await create_admin(
        db_session,
        username="local_admin",
        password="Admin-pass-123",
        display_name="Local Admin",
    )

    with pytest.raises(ValueError, match="already exists"):
        await create_admin(
            db_session,
            username="LOCAL_ADMIN",
            password="Another-pass-123",
            display_name="Another Admin",
        )


@pytest.mark.asyncio
async def test_create_admin_rejects_short_password(db_session):
    with pytest.raises(ValueError, match="10 to 128"):
        await create_admin(
            db_session,
            username="local_admin",
            password="short",
            display_name="Local Admin",
        )


@pytest.mark.asyncio
async def test_run_rejects_mismatched_password_confirmation(monkeypatch):
    responses = iter(["Admin-pass-123", "Different-pass-123"])
    monkeypatch.setattr(create_admin_module.getpass, "getpass", lambda _prompt: next(responses))

    with pytest.raises(SystemExit, match="Passwords do not match"):
        await _run("local_admin", "Local Admin")


@pytest.mark.asyncio
async def test_run_creates_admin_with_session_factory(
    db_session, monkeypatch, capsys
):
    responses = iter(["Admin-pass-123", "Admin-pass-123"])
    monkeypatch.setattr(create_admin_module.getpass, "getpass", lambda _prompt: next(responses))

    class SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(create_admin_module, "AsyncSessionLocal", SessionContext)

    await _run("local_admin", "Local Admin")

    assert "Created administrator: local_admin" in capsys.readouterr().out
