from __future__ import annotations

import datetime
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import bind_tenant_context
from app.db.models import AccountDeletionJob, Course, InviteCode, Material, User
from app.services.account_deletion_service import (
    AccountArtifactCleaner,
    AccountDeletionService,
)


POSTGRES_INTEGRATION_URL = os.getenv("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_URL,
    reason="POSTGRES_INTEGRATION_URL is required for PostgreSQL integration tests",
)


class RecordingVectorStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_collection(self, scope: str) -> None:
        self.deleted.append(scope)


@pytest.mark.asyncio
async def test_postgres_quotas_and_account_deletion_cascade(tmp_path):
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user_id: int | None = None
    invite_id: int | None = None
    job_public_id: str | None = None

    try:
        async with session_factory() as session:
            user = User(
                username=f"deletion_{suffix}",
                hashed_password="integration-test-hash",
                display_name="Deletion Integration",
                role="admin",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            assert user.file_limit == 100
            assert user.storage_limit_bytes == 2 * 1024 * 1024 * 1024

            invite = InviteCode(
                code_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                created_by_user_id=user.id,
                expires_at=datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(days=1),
            )
            session.add(invite)
            await session.commit()
            invite_id = invite.id

        async with session_factory() as session:
            invalid = User(
                username=f"invalid_quota_{suffix}",
                hashed_password="integration-test-hash",
                display_name="Invalid Quota",
                file_limit=-1,
            )
            session.add(invalid)
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

        assert user_id is not None
        filename = f"deletion-{suffix}.pdf"
        (tmp_path / filename).write_bytes(b"private integration material")
        vector_store = RecordingVectorStore()

        async with session_factory() as session:
            await bind_tenant_context(session, user_id)
            course = Course(
                user_id=user_id,
                name=f"Deletion course {suffix}",
                is_default=True,
            )
            session.add(course)
            await session.flush()
            course_id = course.id
            material = Material(
                user_id=user_id,
                course_id=course.id,
                filename=filename,
                original_filename=filename,
                file_type="pdf",
                file_size=28,
            )
            session.add(material)
            await session.commit()

            result = await AccountDeletionService(
                session,
                AccountArtifactCleaner(tmp_path, vector_store),
            ).request(user_id)
            job_public_id = result.job.public_id

            assert result.job.status == "succeeded"
            assert result.job.user_id is None
            assert await session.get(User, user_id) is None
            assert (
                await session.scalar(select(Course.id).where(Course.id == course_id))
                is None
            )
            assert (
                await session.scalar(
                    select(Material.id).where(Material.id == material.id)
                )
                is None
            )

        assert not (tmp_path / filename).exists()
        assert vector_store.deleted == [
            str(user_id),
            f"{user_id}_course_{course_id}",
        ]

        async with session_factory() as session:
            assert invite_id is not None
            invite = await session.get(InviteCode, invite_id)
            assert invite is not None
            assert invite.created_by_user_id is None
            assert invite.disabled_at is not None

            job = await session.scalar(
                select(AccountDeletionJob).where(
                    AccountDeletionJob.public_id == job_public_id
                )
            )
            assert job is not None
            assert job.status == "succeeded"
            assert job.user_id is None
    finally:
        async with session_factory() as session:
            if invite_id is not None:
                invite = await session.get(InviteCode, invite_id)
                if invite is not None:
                    await session.delete(invite)
            if job_public_id is not None:
                job = await session.scalar(
                    select(AccountDeletionJob).where(
                        AccountDeletionJob.public_id == job_public_id
                    )
                )
                if job is not None:
                    await session.delete(job)
            if user_id is not None:
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
            await session.commit()
        await engine.dispose()
