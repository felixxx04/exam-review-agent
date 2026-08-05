from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.db.models import Base, Conversation, Material, MistakeRecord, User
from app.main import app
from app.services.auth_service import AuthService, IssuedSession, hash_password
from app.services.course_service import CourseService


def _apply_session(client: AsyncClient, issued: IssuedSession) -> dict[str, str]:
    client.cookies.set("access_token", issued.access_token)
    client.cookies.set("refresh_token", issued.refresh_token, path="/api/auth")
    client.cookies.set("csrf_token", issued.csrf_token)
    return {"X-CSRF-Token": issued.csrf_token}


@pytest.mark.asyncio
async def test_resource_ids_are_scoped_to_authenticated_tenant():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
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
        service = AuthService(session)
        invite_a = await service.create_invite(actor=admin, max_uses=1)
        invite_b = await service.create_invite(actor=admin, max_uses=1)
        user_a = await service.register(
            username="tenant_a",
            password="Student-pass-123",
            invite_code=invite_a.code,
        )
        user_b = await service.register(
            username="tenant_b",
            password="Student-pass-123",
            invite_code=invite_b.code,
        )
        course = await CourseService(session).resolve_course(user_a.user.id, None)

        conversation = Conversation(
            user_id=user_a.user.id,
            course_id=course.id,
            title="A only",
        )
        material = Material(
            user_id=user_a.user.id,
            course_id=course.id,
            filename="a.pdf",
            original_filename="a.pdf",
            file_type="pdf",
            file_size=1,
        )
        mistake = MistakeRecord(
            public_id="a-mistake",
            user_id=user_a.user.id,
            course_id=course.id,
            source_question_id="a-question",
            wrong_answer="A",
            correct_answer="B",
        )
        session.add_all([conversation, material, mistake])
        await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            csrf = _apply_session(client, user_b)

            assert (
                await client.get(f"/api/conversations/{conversation.id}/messages")
            ).status_code == 404
            assert (
                await client.delete(
                    f"/api/conversations/{conversation.id}", headers=csrf
                )
            ).status_code == 404
            assert (
                await client.get(f"/api/materials/{material.id}")
            ).status_code == 404
            assert (
                await client.post(
                    f"/api/materials/{material.id}/reprocess", headers=csrf
                )
            ).status_code == 404
            assert (
                await client.get("/api/review/mistakes/a-mistake")
            ).status_code == 404
            assert (
                await client.patch(
                    "/api/review/mistakes/a-mistake",
                    headers=csrf,
                    json={"status": "corrected"},
                )
            ).status_code == 404

            materials = (await client.get("/api/materials")).json()["data"]
            assert materials["materials"] == []
    finally:
        app.dependency_overrides.clear()
        await session.close()
        await engine.dispose()
