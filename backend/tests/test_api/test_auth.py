from __future__ import annotations

import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.middleware import RateLimitMiddleware
from app.db.database import get_db
from app.db.models import Base, User
from app.main import app
from app.services.auth_service import AuthService, hash_password


@pytest.fixture
async def auth_environment():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    admin = User(
        username="admin",
        email=None,
        hashed_password=hash_password("Admin-pass-123"),
        display_name="Admin",
        role="admin",
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="https://test")
    RateLimitMiddleware.reset()
    try:
        yield client, session, admin
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        await session.close()
        await engine.dispose()
        RateLimitMiddleware.reset()


def _csrf_header(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


async def _login_admin(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin-pass-123"},
    )
    assert response.status_code == 200
    return response


@pytest.mark.asyncio
async def test_login_sets_secure_cookie_session_without_returning_tokens(auth_environment):
    client, _, _ = auth_environment

    response = await _login_admin(client)

    data = response.json()["data"]
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert data["user"]["username"] == "admin"
    cookies = response.headers.get_list("set-cookie")
    access_cookie = next(cookie for cookie in cookies if cookie.startswith("access_token="))
    refresh_cookie = next(cookie for cookie in cookies if cookie.startswith("refresh_token="))
    assert "HttpOnly" in access_cookie and "Secure" in access_cookie
    assert "SameSite=lax" in access_cookie
    assert "HttpOnly" in refresh_cookie and "Path=/api/auth" in refresh_cookie
    assert client.cookies.get("csrf_token")


@pytest.mark.asyncio
async def test_admin_invite_registration_and_current_user_flow(auth_environment):
    client, _, _ = auth_environment
    await _login_admin(client)
    invite_response = await client.post(
        "/api/auth/invites",
        headers=_csrf_header(client),
        json={"max_uses": 1, "expires_at": None},
    )
    assert invite_response.status_code == 201
    invite_code = invite_response.json()["data"]["code"]

    client.cookies.clear()
    register = await client.post(
        "/api/auth/register",
        json={
            "username": "new_student",
            "password": "Student-pass-123",
            "display_name": "New Student",
            "invite_code": invite_code,
        },
    )
    assert register.status_code == 201

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "new_student"
    reused = await client.post(
        "/api/auth/register",
        json={
            "username": "another_student",
            "password": "Student-pass-123",
            "invite_code": invite_code,
        },
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "INVALID_INVITE"


@pytest.mark.asyncio
async def test_cookie_authenticated_mutations_require_matching_csrf(auth_environment):
    client, _, _ = auth_environment
    await _login_admin(client)

    missing = await client.post("/api/conversations")
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "CSRF_FAILED"

    accepted = await client.post(
        "/api/conversations",
        headers=_csrf_header(client),
    )
    assert accepted.status_code == 200

    rejected = await client.post(
        "/api/conversations",
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )
    assert rejected.status_code == 403


@pytest.mark.asyncio
async def test_bearer_authenticated_mutation_does_not_require_browser_csrf(
    auth_environment,
):
    client, _, _ = auth_environment
    await _login_admin(client)
    access_token = client.cookies.get("access_token")
    assert access_token
    client.cookies.clear()

    response = await client.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_authorization_header_is_rejected(auth_environment):
    client, _, _ = auth_environment

    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Basic not-supported"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_refresh_rotates_cookies_and_logout_revokes_session(auth_environment):
    client, _, _ = auth_environment
    await _login_admin(client)
    old_refresh = client.cookies.get("refresh_token")
    old_csrf = client.cookies.get("csrf_token")

    refreshed = await client.post(
        "/api/auth/refresh",
        headers=_csrf_header(client),
    )
    assert refreshed.status_code == 200
    assert client.cookies.get("refresh_token") != old_refresh
    assert client.cookies.get("csrf_token") != old_csrf

    logged_out = await client.post(
        "/api/auth/logout",
        headers=_csrf_header(client),
    )
    assert logged_out.status_code == 200
    assert client.cookies.get("access_token") is None
    assert client.cookies.get("refresh_token") is None
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_admin_can_disable_account_and_disabled_session_stops_working(auth_environment):
    client, session, admin = auth_environment
    service = AuthService(session)
    created = await service.create_invite(actor=admin, max_uses=1)
    user_session = await service.register(
        username="soon_disabled",
        password="Student-pass-123",
        invite_code=created.code,
    )

    await _login_admin(client)
    response = await client.patch(
        f"/api/auth/users/{user_session.user.id}",
        headers=_csrf_header(client),
        json={"disabled": True},
    )
    assert response.status_code == 200

    client.cookies.clear()
    login = await client.post(
        "/api/auth/login",
        json={"username": "soon_disabled", "password": "Student-pass-123"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_revoked_or_disabled_sessions_reject_saved_access_tokens(auth_environment):
    client, session, admin = auth_environment
    service = AuthService(session)
    created = await service.create_invite(actor=admin, max_uses=1)
    issued = await service.register(
        username="session_state_user",
        password="Student-pass-123",
        invite_code=created.code,
    )

    await service.logout(
        refresh_token=issued.refresh_token,
        csrf_token=issued.csrf_token,
    )
    logged_out = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {issued.access_token}"},
    )
    assert logged_out.status_code == 401

    second = await service.login(
        username="session_state_user",
        password="Student-pass-123",
    )
    await service.set_user_disabled(
        actor=admin,
        user_id=second.user.id,
        disabled=True,
    )
    disabled = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {second.access_token}"},
    )
    assert disabled.status_code == 401


@pytest.mark.asyncio
async def test_missing_admin_resources_return_not_found(auth_environment):
    client, _, _ = auth_environment
    await _login_admin(client)
    headers = _csrf_header(client)

    missing_invite = await client.patch(
        "/api/auth/invites/999999",
        headers=headers,
        json={"disabled": True},
    )
    missing_user = await client.patch(
        "/api/auth/users/999999",
        headers=headers,
        json={"disabled": True},
    )

    assert missing_invite.status_code == 404
    assert missing_invite.json()["error"]["code"] == "NOT_FOUND"
    assert missing_user.status_code == 404
    assert missing_user.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_non_admin_cannot_create_invites(auth_environment):
    client, session, admin = auth_environment
    service = AuthService(session)
    created = await service.create_invite(actor=admin, max_uses=1)
    await service.register(
        username="regular_user",
        password="Student-pass-123",
        invite_code=created.code,
    )
    client.cookies.clear()
    login = await client.post(
        "/api/auth/login",
        json={"username": "regular_user", "password": "Student-pass-123"},
    )
    assert login.status_code == 200

    response = await client.post(
        "/api/auth/invites",
        headers=_csrf_header(client),
        json={"max_uses": 1},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_auth_endpoints_are_rate_limited(auth_environment):
    client, _, _ = auth_environment
    for _ in range(5):
        response = await client.post(
            "/api/auth/login",
            json={"username": "missing", "password": "Wrong-pass-123"},
        )
        assert response.status_code == 401

    limited = await client.post(
        "/api/auth/login",
        json={"username": "missing", "password": "Wrong-pass-123"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
