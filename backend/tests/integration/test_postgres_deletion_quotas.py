from __future__ import annotations

import asyncio
import datetime
import io
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.datastructures import Headers, UploadFile

from app.api import materials as materials_api
from app.api.materials import upload_material
from app.core.auth import AuthenticatedUser
from app.db.database import bind_tenant_context
from app.db.models import (
    AccountDeletionJob,
    Course,
    InviteCode,
    Material,
    MaterialChunk,
    ProcessingStatus,
    User,
)
from app.core.exceptions import AppException
from app.services.account_deletion_service import (
    AccountArtifactCleaner,
    AccountDeletionService,
)
from app.services.object_storage import StoredObject
from app.services.parser_service import Chunk, ParseResult
from app.services.material_storage_cleanup import (
    recover_stale_material_reservations_for_user,
)
from app.services.quota_service import QuotaService


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


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def put_file(
        self,
        *,
        key: str,
        source: Path,
        size_bytes: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        content = source.read_bytes()
        assert len(content) == size_bytes
        self.objects[key] = content
        return StoredObject(
            key=key,
            size_bytes=size_bytes,
            etag="integration-etag",
            version_id="integration-version",
        )

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        version_id: str | None = None,
    ) -> None:
        destination.write_bytes(self.objects[key])

    async def delete_object(self, *, key: str, version_id: str | None = None) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)


class BlockingRecordingVectorStore(RecordingVectorStore):
    def __init__(
        self,
        cleanup_started: asyncio.Event,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        super().__init__()
        self.cleanup_started = cleanup_started
        self.loop = loop
        self.scopes: set[str] = set()

    def delete_collection(self, scope: str) -> None:
        super().delete_collection(scope)
        self.scopes.discard(scope)
        self.loop.call_soon_threadsafe(self.cleanup_started.set)


class BlockingRetrieval:
    def __init__(
        self,
        vector_store: BlockingRecordingVectorStore,
        indexing_started: asyncio.Event,
        release_indexing: asyncio.Event,
    ) -> None:
        self.vector_store = vector_store
        self.indexing_started = indexing_started
        self.release_indexing = release_indexing

    async def index_chunks(
        self,
        user_id: str,
        chunks: list[dict],
        *,
        course_id: int | None = None,
        chunk_ids: list[str] | None = None,
    ) -> list[str]:
        self.indexing_started.set()
        await self.release_indexing.wait()
        scope = user_id if course_id is None else f"{user_id}_course_{course_id}"
        self.vector_store.scopes.add(scope)
        return chunk_ids or [
            f"blocked-index-{index}" for index, _chunk in enumerate(chunks)
        ]


class SingleChunkParser:
    async def parse(self, _file_path: str, file_type: str | None = None) -> ParseResult:
        return ParseResult(
            chunks=[Chunk(text="account deletion indexing race", metadata={})],
            page_count=1,
        )


@pytest.mark.asyncio
async def test_postgres_recovery_fences_a_paused_stale_processing_attempt(
    monkeypatch,
):
    """An expired worker cannot index after recovery takes over its lease."""
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    intent_committed = asyncio.Event()
    release_processing = asyncio.Event()
    user_id: int | None = None
    course_id: int | None = None
    upload_task: asyncio.Task | None = None
    storage = InMemoryObjectStorage()
    persisted_chunk_ids: list[str] = []
    object_key: str | None = None

    class RecordingRetrieval:
        def __init__(self) -> None:
            self.index_calls = 0
            self.deleted_chunk_ids: list[str] = []

        async def index_chunks(self, **kwargs) -> list[str]:
            self.index_calls += 1
            return kwargs["chunk_ids"]

        async def delete_chunks(self, *, chunk_ids, **_kwargs) -> None:
            self.deleted_chunk_ids.extend(chunk_ids)

    retrieval = RecordingRetrieval()
    original_lock_upload = materials_api.QuotaService.lock_upload
    paused = False
    intent_material_id: int | None = None

    async def pause_after_durable_intent(service, locked_user_id):
        nonlocal intent_material_id, paused
        intent_exists = await service.db.scalar(
            select(MaterialChunk.id)
            .join(Material)
            .where(Material.user_id == locked_user_id)
            .limit(1)
        )
        if intent_exists is not None and not paused:
            paused = True
            intent_material_id = await service.db.scalar(
                select(MaterialChunk.material_id)
                .join(Material)
                .where(Material.user_id == locked_user_id)
                .limit(1)
            )
            intent_committed.set()
            await release_processing.wait()
        return await original_lock_upload(service, locked_user_id)

    monkeypatch.setattr(
        "app.services.parser_service.ParserService", lambda: SingleChunkParser()
    )
    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", lambda: retrieval
    )
    monkeypatch.setattr(
        materials_api.QuotaService,
        "lock_upload",
        pause_after_durable_intent,
    )

    try:
        async with session_factory() as session:
            user = User(
                username=f"lease_fence_{suffix}",
                hashed_password="integration-test-hash",
                display_name="Lease Fence Integration",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        assert user_id is not None
        async with session_factory() as session:
            await bind_tenant_context(session, user_id)
            course = Course(
                user_id=user_id,
                name=f"Lease fence course {suffix}",
                is_default=True,
            )
            session.add(course)
            await session.commit()
            course_id = course.id

        assert course_id is not None
        current_user = AuthenticatedUser(
            id=user_id,
            username=f"lease_fence_{suffix}",
            role="user",
            session_id=f"lease-fence-session-{suffix}",
        )

        async def run_upload():
            async with session_factory() as session:
                await bind_tenant_context(session, user_id)
                uploaded_file = UploadFile(
                    file=io.BytesIO(
                        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
                        b"trailer\n<<>>\n%%EOF\n"
                    ),
                    filename="fenced-postgres.pdf",
                    headers=Headers({"content-type": "application/pdf"}),
                )
                try:
                    return await upload_material(
                        file=uploaded_file,
                        course_id=course_id,
                        current_user=current_user,
                        db=session,
                        storage=storage,
                    )
                finally:
                    await uploaded_file.close()

        upload_task = asyncio.create_task(run_upload())
        await asyncio.wait_for(intent_committed.wait(), timeout=5)
        assert intent_material_id is not None

        async with session_factory() as recovery_session:
            await bind_tenant_context(recovery_session, user_id)
            material = await recovery_session.scalar(
                select(Material)
                .where(Material.id == intent_material_id)
                .with_for_update()
            )
            assert material is not None
            assert material.processing_status == ProcessingStatus.PROCESSING
            assert material.processing_lease_id is not None
            object_key = material.object_key
            persisted_chunk_ids = list(
                (
                    await recovery_session.scalars(
                        select(MaterialChunk.chunk_id).where(
                            MaterialChunk.material_id == material.id
                        )
                    )
                ).all()
            )
            assert persisted_chunk_ids
            material.processing_lease_expires_at = datetime.datetime.now(
                datetime.UTC
            ) - datetime.timedelta(seconds=1)
            material.created_at = datetime.datetime.now(
                datetime.UTC
            ) - datetime.timedelta(hours=2)
            await recovery_session.commit()

            report = await recover_stale_material_reservations_for_user(
                recovery_session,
                storage,
                user_id=user_id,
                older_than=datetime.datetime.now(datetime.UTC)
                - datetime.timedelta(minutes=1),
            )
            assert report.scanned == 1
            assert report.pending == 0

            material = await recovery_session.scalar(
                select(Material).where(Material.id == intent_material_id)
            )
            assert material is not None
            assert material.storage_status.value == "available"
            assert material.processing_status == ProcessingStatus.FAILED
            assert material.processing_lease_id is None
            assert material.processing_lease_expires_at is None
            assert (
                await recovery_session.scalar(
                    select(MaterialChunk.id).where(
                        MaterialChunk.material_id == material.id
                    )
                )
                is None
            )

        release_processing.set()
        result = await asyncio.wait_for(upload_task, timeout=5)

        assert result.data is not None
        assert retrieval.index_calls == 0
        assert retrieval.deleted_chunk_ids == persisted_chunk_ids
        assert object_key is not None
        assert object_key in storage.objects
        async with session_factory() as inspection_session:
            await bind_tenant_context(inspection_session, user_id)
            material = await inspection_session.scalar(
                select(Material).where(Material.id == intent_material_id)
            )
            assert material is not None
            assert material.storage_status.value == "available"
            assert material.processing_status == ProcessingStatus.FAILED
            assert material.processing_lease_id is None
            assert material.processing_lease_expires_at is None
    finally:
        release_processing.set()
        if upload_task is not None and not upload_task.done():
            await asyncio.gather(upload_task, return_exceptions=True)
        async with session_factory() as cleanup_session:
            if user_id is not None:
                user = await cleanup_session.get(User, user_id)
                if user is not None:
                    await cleanup_session.delete(user)
            await cleanup_session.commit()
        await engine.dispose()


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

        async with session_factory() as session:
            session.add_all(
                [
                    AccountDeletionJob(
                        public_id=f"duplicate-a-{suffix}",
                        user_id=user_id,
                        status_token_hash="a" * 64,
                    ),
                    AccountDeletionJob(
                        public_id=f"duplicate-b-{suffix}",
                        user_id=user_id,
                        status_token_hash="b" * 64,
                    ),
                ]
            )
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
                storage_backend="legacy_local",
                storage_status="available",
                storage_path=str(tmp_path / filename),
            )
            session.add(material)
            await session.commit()

            service = AccountDeletionService(
                session,
                AccountArtifactCleaner(tmp_path, vector_store),
            )
            result = await service.request(user_id)
            job_public_id = result.job.public_id
            assert result.job.status == "pending"
            await service.execute(result.job.public_id)

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


@pytest.mark.asyncio
async def test_account_deletion_waits_for_an_upload_holding_the_user_lock(tmp_path):
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    upload_locked = asyncio.Event()
    release_upload = asyncio.Event()
    user_id: int | None = None
    job_public_id: str | None = None
    upload_task: asyncio.Task[None] | None = None
    deletion_task: asyncio.Task | None = None
    filename = f"concurrent-{suffix}.pdf"
    vector_store = RecordingVectorStore()

    try:
        async with session_factory() as session:
            user = User(
                username=f"concurrent_deletion_{suffix}",
                hashed_password="integration-test-hash",
                display_name="Concurrent Deletion",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        assert user_id is not None
        async with session_factory() as session:
            await bind_tenant_context(session, user_id)
            course = Course(
                user_id=user_id,
                name=f"Concurrent course {suffix}",
                is_default=True,
            )
            session.add(course)
            await session.commit()
            course_id = course.id

        async def finish_upload() -> None:
            async with session_factory() as session:
                await bind_tenant_context(session, user_id)
                await QuotaService(session).ensure_upload_allowed(user_id, 7)
                (tmp_path / filename).write_bytes(b"pending")
                session.add(
                    Material(
                        user_id=user_id,
                        course_id=course_id,
                        filename=filename,
                        original_filename=filename,
                        file_type="pdf",
                        file_size=7,
                        storage_backend="legacy_local",
                        storage_status="available",
                        storage_path=str(tmp_path / filename),
                    )
                )
                upload_locked.set()
                await release_upload.wait()
                await session.commit()

        async def delete_account():
            async with session_factory() as session:
                service = AccountDeletionService(
                    session,
                    AccountArtifactCleaner(tmp_path, vector_store),
                )
                result = await service.request(user_id)
                await service.execute(result.job.public_id)
                return result

        upload_task = asyncio.create_task(finish_upload())
        await upload_locked.wait()
        deletion_task = asyncio.create_task(delete_account())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(deletion_task), timeout=0.2)

        release_upload.set()
        await upload_task
        result = await deletion_task
        job_public_id = result.job.public_id

        assert result.job.status == "succeeded"
        assert not (tmp_path / filename).exists()
        assert vector_store.deleted == [
            str(user_id),
            f"{user_id}_course_{course_id}",
        ]
        async with session_factory() as session:
            assert await session.get(User, user_id) is None
    finally:
        release_upload.set()
        pending_tasks = [
            task
            for task in (upload_task, deletion_task)
            if task is not None and not task.done()
        ]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        async with session_factory() as session:
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
        (tmp_path / filename).unlink(missing_ok=True)
        await engine.dispose()


@pytest.mark.asyncio
async def test_account_deletion_waits_for_blocked_upload_indexing_before_vector_cleanup(
    monkeypatch,
):
    """Deletion must not clear scopes before a committed upload has indexed them."""
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    indexing_started = asyncio.Event()
    release_indexing = asyncio.Event()
    deletion_started = asyncio.Event()
    vector_cleanup_started = asyncio.Event()
    user_id: int | None = None
    course_id: int | None = None
    job_public_id: str | None = None
    upload_task: asyncio.Task | None = None
    deletion_task: asyncio.Task | None = None
    storage = InMemoryObjectStorage()
    vector_store = BlockingRecordingVectorStore(
        vector_cleanup_started,
        asyncio.get_running_loop(),
    )
    retrieval = BlockingRetrieval(vector_store, indexing_started, release_indexing)

    monkeypatch.setattr(
        "app.services.parser_service.ParserService", lambda: SingleChunkParser()
    )
    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", lambda: retrieval
    )

    try:
        async with session_factory() as session:
            user = User(
                username=f"indexing_deletion_{suffix}",
                hashed_password="integration-test-hash",
                display_name="Indexing Deletion",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        assert user_id is not None
        async with session_factory() as session:
            await bind_tenant_context(session, user_id)
            course = Course(
                user_id=user_id,
                name=f"Indexing course {suffix}",
                is_default=True,
            )
            session.add(course)
            await session.commit()
            course_id = course.id

        assert course_id is not None
        current_user = AuthenticatedUser(
            id=user_id,
            username=f"indexing_deletion_{suffix}",
            role="user",
            session_id=f"indexing-session-{suffix}",
        )

        async def run_upload():
            async with session_factory() as session:
                await bind_tenant_context(session, user_id)
                uploaded_file = UploadFile(
                    file=io.BytesIO(
                        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
                        b"trailer\n<<>>\n%%EOF\n"
                    ),
                    filename="concurrent-indexing.pdf",
                    headers=Headers({"content-type": "application/pdf"}),
                )
                try:
                    return await upload_material(
                        file=uploaded_file,
                        course_id=course_id,
                        current_user=current_user,
                        db=session,
                        storage=storage,
                    )
                finally:
                    await uploaded_file.close()

        async def delete_account():
            nonlocal job_public_id
            async with session_factory() as session:
                service = AccountDeletionService(
                    session,
                    AccountArtifactCleaner(storage, vector_store),
                )
                deletion_started.set()
                result = await service.request(user_id)
                job_public_id = result.job.public_id
                await service.execute(result.job.public_id)
                return result

        upload_task = asyncio.create_task(run_upload())
        await asyncio.wait_for(indexing_started.wait(), timeout=5)
        deletion_task = asyncio.create_task(delete_account())
        await asyncio.wait_for(deletion_started.wait(), timeout=5)

        # Without the post-S3 user lock, cleanup reaches the vector store here,
        # before the blocked index can record its scope.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(vector_cleanup_started.wait(), timeout=0.25)

        release_indexing.set()
        await asyncio.wait_for(asyncio.shield(upload_task), timeout=5)
        deletion_result = await asyncio.wait_for(
            asyncio.shield(deletion_task), timeout=5
        )

        assert deletion_result.job.status == "succeeded"
        assert vector_store.scopes == set()
        assert storage.objects == {}
        assert vector_store.deleted == [
            str(user_id),
            f"{user_id}_course_{course_id}",
        ]
        async with session_factory() as session:
            assert await session.get(User, user_id) is None
    finally:
        release_indexing.set()
        pending_tasks = [
            task
            for task in (upload_task, deletion_task)
            if task is not None and not task.done()
        ]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        async with session_factory() as session:
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


@pytest.mark.asyncio
async def test_concurrent_account_deletion_requests_create_one_active_job(tmp_path):
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(POSTGRES_INTEGRATION_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    start = asyncio.Event()
    user_id: int | None = None

    try:
        async with session_factory() as session:
            user = User(
                username=f"concurrent_request_{suffix}",
                hashed_password="integration-test-hash",
                display_name="Concurrent Request",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        assert user_id is not None

        async def request_deletion() -> str:
            async with session_factory() as session:
                await start.wait()
                try:
                    await AccountDeletionService(
                        session,
                        AccountArtifactCleaner(tmp_path, RecordingVectorStore()),
                    ).request(user_id)
                    return "created"
                except AppException as exc:
                    return exc.code

        requests = [
            asyncio.create_task(request_deletion()),
            asyncio.create_task(request_deletion()),
        ]
        start.set()
        outcomes = await asyncio.gather(*requests)

        assert sorted(outcomes) == ["CONFLICT", "created"]
        async with session_factory() as session:
            jobs = (
                (
                    await session.execute(
                        select(AccountDeletionJob).where(
                            AccountDeletionJob.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(jobs) == 1
    finally:
        async with session_factory() as session:
            if user_id is not None:
                jobs = (
                    (
                        await session.execute(
                            select(AccountDeletionJob).where(
                                AccountDeletionJob.user_id == user_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for job in jobs:
                    await session.delete(job)
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
            await session.commit()
        await engine.dispose()
