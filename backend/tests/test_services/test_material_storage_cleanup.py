from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api import materials as materials_api
from app.core.auth import AuthenticatedUser
from app.db.models import (
    Course,
    Material,
    MaterialChunk,
    ProcessingStatus,
    StorageStatus,
)
from app.services import material_storage_cleanup
from app.services.material_storage_cleanup import recover_stale_material_reservations
from app.services.quota_service import QuotaService
from app.services.retrieval_service import RetrievalService


class _InMemoryVectorStore:
    def __init__(self) -> None:
        self.documents: list[dict] = []

    def add(self, user_id, embeddings, documents, metadatas, ids=None):
        self.documents.extend(
            {
                "user_id": user_id,
                "id": chunk_id,
                "document": document,
                "metadata": metadata,
                "distance": 0.1,
            }
            for chunk_id, document, metadata in zip(
                ids, documents, metadatas, strict=False
            )
        )
        return ids

    def search(self, user_id, query_embedding, top_k=10, metadata_filter=None):
        return [
            document for document in self.documents if document["user_id"] == user_id
        ][:top_k]

    def delete(self, user_id, ids) -> None:
        self.documents = [
            document
            for document in self.documents
            if document["user_id"] != user_id or document["id"] not in ids
        ]


class _InMemoryEmbeddings:
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class _CrossEncoder:
    def predict(self, pairs, show_progress_bar=False):
        return [0.9 for _ in pairs]


async def _stale_material(db_session, authenticated_user, object_storage, *, status):
    course = Course(
        user_id=authenticated_user.id,
        name=f"Storage cleanup {status}",
        is_default=True,
    )
    db_session.add(course)
    await db_session.flush()
    material = Material(
        user_id=authenticated_user.id,
        course_id=course.id,
        filename="opaque-object",
        original_filename="notes.pdf",
        file_type="pdf",
        file_size=123,
        storage_backend="s3",
        storage_status=status,
        created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
    )
    db_session.add(material)
    await db_session.flush()
    material.object_key = (
        f"users/{authenticated_user.id}/courses/{course.id}/materials/{material.id}/"
        f"objects/{material.object_id}"
    )
    material.object_version_id = "in-memory-version"
    object_storage.objects[material.object_key] = b"private material"
    await db_session.commit()
    return material


@pytest.mark.asyncio
async def test_stale_s3_reservation_is_deleted_and_no_longer_consumes_quota(
    db_session, authenticated_user, object_storage
):
    material = await _stale_material(
        db_session,
        authenticated_user,
        object_storage,
        status=StorageStatus.RESERVED,
    )

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    usage = await QuotaService(db_session).get_usage(authenticated_user.id)
    assert report.scanned == 1
    assert report.objects_cleaned == 1
    assert report.tombstones_written == 1
    assert report.pending == 0
    assert material.storage_status == StorageStatus.DELETED
    assert material.object_key not in object_storage.objects
    assert usage.files_used == 0
    assert usage.storage_used_bytes == 0


@pytest.mark.asyncio
async def test_stale_deleting_material_with_chunks_remains_retryable(
    db_session, authenticated_user, object_storage, monkeypatch
):
    material = await _stale_material(
        db_session,
        authenticated_user,
        object_storage,
        status=StorageStatus.DELETING,
    )
    db_session.add(
        MaterialChunk(
            material_id=material.id,
            user_id=material.user_id,
            course_id=material.course_id,
            chunk_id="storage-cleanup-chunk",
            text_preview="pending vector cleanup",
            token_count=1,
            embedding_id="storage-cleanup-chunk",
        )
    )
    await db_session.commit()

    class FailingRetrieval:
        async def delete_chunks(self, **kwargs):
            raise RuntimeError("retrieval service temporarily unavailable")

    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", FailingRetrieval
    )

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    assert report.objects_cleaned == 1
    assert report.tombstones_written == 0
    assert report.pending == 1
    assert material.storage_status == StorageStatus.DELETING
    assert material.object_key not in object_storage.objects


@pytest.mark.asyncio
async def test_recovery_skips_an_active_material_processing_lease(
    db_session, authenticated_user, object_storage, monkeypatch
):
    material = await _stale_material(
        db_session,
        authenticated_user,
        object_storage,
        status=StorageStatus.AVAILABLE,
    )
    material.processing_status = ProcessingStatus.PROCESSING
    material.processing_lease_expires_at = datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(minutes=5)
    db_session.add(
        MaterialChunk(
            material_id=material.id,
            user_id=material.user_id,
            course_id=material.course_id,
            chunk_id="active-processing-lease",
            text_preview="must not be reclaimed while indexing",
            token_count=6,
            embedding_id="active-processing-lease",
        )
    )
    await db_session.commit()

    class RetrievalMustNotRun:
        async def delete_chunks(self, **kwargs) -> None:
            raise AssertionError("active indexing must not be reclaimed")

    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", RetrievalMustNotRun
    )

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    assert report.scanned == 0
    assert material.object_key in object_storage.objects
    assert material.processing_status == ProcessingStatus.PROCESSING


@pytest.mark.asyncio
async def test_recovery_does_not_bypass_an_active_lease_while_deleting(
    db_session, authenticated_user, object_storage, monkeypatch
):
    material = await _stale_material(
        db_session,
        authenticated_user,
        object_storage,
        status=StorageStatus.DELETING,
    )
    material.processing_status = ProcessingStatus.PROCESSING
    material.processing_lease_expires_at = datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(minutes=5)
    db_session.add(
        MaterialChunk(
            material_id=material.id,
            user_id=material.user_id,
            course_id=material.course_id,
            chunk_id="active-deleting-processing-lease",
            text_preview="must not be reclaimed while indexing",
            token_count=6,
            embedding_id="active-deleting-processing-lease",
        )
    )
    await db_session.commit()

    class RetrievalMustNotRun:
        async def delete_chunks(self, **kwargs) -> None:
            raise AssertionError("active deleting index must not be reclaimed")

    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", RetrievalMustNotRun
    )

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    assert report.scanned == 1
    assert report.objects_cleaned == 0
    assert report.tombstones_written == 0
    assert material.storage_status == StorageStatus.DELETING
    assert material.processing_status == ProcessingStatus.PROCESSING
    assert material.object_key in object_storage.objects
    assert (
        await db_session.scalar(
            select(MaterialChunk.id).where(MaterialChunk.material_id == material.id)
        )
        is not None
    )


@pytest.mark.asyncio
async def test_recovery_marks_an_expired_processing_material_without_chunk_intent_failed(
    db_session, authenticated_user, object_storage
):
    material = await _stale_material(
        db_session,
        authenticated_user,
        object_storage,
        status=StorageStatus.AVAILABLE,
    )
    material.processing_status = ProcessingStatus.PROCESSING
    material.processing_lease_expires_at = None
    await db_session.commit()

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    assert report.scanned == 1
    assert report.pending == 0
    assert material.processing_status == ProcessingStatus.FAILED
    assert material.processing_lease_expires_at is None
    assert material.object_key in object_storage.objects


@pytest.mark.asyncio
async def test_recovery_removes_searchable_chunks_after_transient_delete_failure(
    db_session, authenticated_user, object_storage, monkeypatch
):
    material = await _stale_material(
        db_session,
        authenticated_user,
        object_storage,
        status=StorageStatus.AVAILABLE,
    )
    user_id = authenticated_user.id
    course_id = material.course_id
    vector_store = _InMemoryVectorStore()
    retrieval = RetrievalService(
        vector_store=vector_store,
        embedding_service=_InMemoryEmbeddings(),
    )
    monkeypatch.setattr(
        RetrievalService,
        "_get_cross_encoder",
        classmethod(lambda _cls: _CrossEncoder()),
    )
    chunk_ids = await retrieval.index_chunks(
        str(user_id),
        [
            {
                "text": "durable cleanup search token",
                "metadata": {"material_id": material.id},
            }
        ],
        course_id=course_id,
    )
    db_session.add(
        MaterialChunk(
            material_id=material.id,
            user_id=material.user_id,
            course_id=material.course_id,
            chunk_id=chunk_ids[0],
            content="durable cleanup search token",
            text_preview="durable cleanup search token",
            token_count=4,
            embedding_id=chunk_ids[0],
        )
    )
    await db_session.commit()

    original_delete_chunks = retrieval.delete_chunks
    delete_attempts = 0

    async def fail_once(*args, **kwargs):
        nonlocal delete_attempts
        delete_attempts += 1
        if delete_attempts == 1:
            raise RuntimeError("retrieval service temporarily unavailable")
        await original_delete_chunks(*args, **kwargs)

    monkeypatch.setattr(retrieval, "delete_chunks", fail_once)
    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", lambda: retrieval
    )
    current_user = AuthenticatedUser(
        id=user_id,
        username=authenticated_user.username,
        role=authenticated_user.role,
        session_id="test-session",
    )

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await materials_api.delete_material(
            material.id,
            current_user=current_user,
            db=db_session,
            storage=object_storage,
        )

    await db_session.refresh(material)
    assert material.storage_status == StorageStatus.DELETING
    assert material.object_key not in object_storage.objects
    assert len(vector_store.documents) == 1
    assert retrieval._scope_key(str(user_id), course_id) in retrieval._bm25_indices
    assert await retrieval.search(
        str(user_id),
        "durable cleanup search token",
        course_id=course_id,
        apply_quality_gate=False,
    )

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    assert report.tombstones_written == 1
    assert report.pending == 0
    assert material.storage_status == StorageStatus.DELETED
    assert (
        await db_session.scalar(
            select(MaterialChunk.id).where(MaterialChunk.material_id == material.id)
        )
        is None
    )
    assert vector_store.documents == []
    assert retrieval._scope_key(str(user_id), course_id) not in retrieval._bm25_indices
    assert (
        await retrieval.search(
            str(user_id),
            "durable cleanup search token",
            course_id=course_id,
            apply_quality_gate=False,
        )
        == []
    )
    assert delete_attempts == 2

    repeat = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )
    assert repeat.scanned == 0


@pytest.mark.asyncio
async def test_recovery_finishes_legacy_cleanup_after_index_delete_failure(
    db_session, authenticated_user, object_storage, monkeypatch, tmp_path
):
    course = Course(
        user_id=authenticated_user.id,
        name="Legacy cleanup recovery",
        is_default=True,
    )
    db_session.add(course)
    await db_session.flush()
    legacy_path = tmp_path / "legacy-retry.pdf"
    legacy_path.write_bytes(b"legacy private material")
    material = Material(
        user_id=authenticated_user.id,
        course_id=course.id,
        filename=legacy_path.name,
        original_filename=legacy_path.name,
        file_type="pdf",
        file_size=legacy_path.stat().st_size,
        storage_backend="legacy_local",
        storage_status=StorageStatus.AVAILABLE,
        storage_path=str(legacy_path),
        created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
    )
    db_session.add(material)
    await db_session.flush()
    db_session.add(
        MaterialChunk(
            material_id=material.id,
            user_id=material.user_id,
            course_id=material.course_id,
            chunk_id="legacy-retry-chunk",
            text_preview="legacy retryable cleanup",
            token_count=1,
            embedding_id="legacy-retry-chunk",
        )
    )
    await db_session.commit()

    class RetryableRetrieval:
        def __init__(self) -> None:
            self.calls = 0

        async def delete_chunks(self, **kwargs) -> None:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("retrieval service temporarily unavailable")

    retrieval = RetryableRetrieval()
    monkeypatch.setattr(
        "app.services.retrieval_service.RetrievalService", lambda: retrieval
    )
    monkeypatch.setattr(materials_api, "LEGACY_UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(
        material_storage_cleanup, "LEGACY_UPLOAD_ROOT", tmp_path, raising=False
    )
    current_user = AuthenticatedUser(
        id=authenticated_user.id,
        username="test_user",
        role="user",
        session_id="test-session",
    )

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await materials_api.delete_material(
            material.id,
            current_user=current_user,
            db=db_session,
            storage=object_storage,
        )

    await db_session.refresh(material)
    assert not legacy_path.exists()
    assert material.storage_status == StorageStatus.DELETING

    report = await recover_stale_material_reservations(
        db_session,
        object_storage,
        older_than=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1),
    )

    await db_session.refresh(material)
    assert report.scanned == 1
    assert report.tombstones_written == 1
    assert report.pending == 0
    assert material.storage_status == StorageStatus.DELETED
    assert (
        await db_session.scalar(
            select(MaterialChunk.id).where(MaterialChunk.material_id == material.id)
        )
        is None
    )
    assert retrieval.calls == 2


@pytest.mark.asyncio
async def test_discard_reservation_preserves_a_concurrent_deletion_tombstone(
    db_session, authenticated_user
):
    course = Course(
        user_id=authenticated_user.id,
        name="Concurrent deletion tombstone",
        is_default=True,
    )
    db_session.add(course)
    await db_session.flush()
    material = Material(
        user_id=authenticated_user.id,
        course_id=course.id,
        filename="concurrent-delete",
        original_filename="concurrent-delete.pdf",
        file_type="pdf",
        file_size=0,
        storage_status=StorageStatus.DELETED,
    )
    db_session.add(material)
    await db_session.commit()
    material_id = material.id

    await materials_api._discard_reservation(db_session, material_id)

    remaining = await db_session.get(Material, material_id)
    assert remaining is not None
    assert remaining.storage_status == StorageStatus.DELETED


@pytest.mark.asyncio
async def test_recovery_entrypoint_binds_the_requested_tenant_before_scanning(
    db_session, authenticated_user, object_storage, monkeypatch
):
    expected = material_storage_cleanup.ReservationRecoveryReport(
        scanned=0,
        objects_cleaned=0,
        tombstones_written=0,
        pending=0,
    )
    bind_tenant = AsyncMock()
    recover = AsyncMock(return_value=expected)
    monkeypatch.setattr(material_storage_cleanup, "bind_tenant_context", bind_tenant)
    monkeypatch.setattr(
        material_storage_cleanup,
        "recover_stale_material_reservations",
        recover,
    )

    result = (
        await material_storage_cleanup.recover_stale_material_reservations_for_user(
            db_session,
            object_storage,
            user_id=authenticated_user.id,
            older_than=datetime.datetime.now(datetime.UTC),
        )
    )

    assert result == expected
    bind_tenant.assert_awaited_once_with(db_session, authenticated_user.id)
    recover.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_cli_uses_the_tenant_scoped_entrypoint(
    authenticated_user, object_storage, monkeypatch
):
    from app.cli import recover_material_storage as recovery_cli

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    expected = material_storage_cleanup.ReservationRecoveryReport(
        scanned=1,
        objects_cleaned=1,
        tombstones_written=1,
        pending=0,
    )
    recover = AsyncMock(return_value=expected)
    monkeypatch.setattr(recovery_cli, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(recovery_cli, "get_object_storage", lambda: object_storage)
    monkeypatch.setattr(
        recovery_cli,
        "recover_stale_material_reservations_for_user",
        recover,
    )

    result = await recovery_cli.recover_material_storage(
        user_id=authenticated_user.id,
        older_than_minutes=30,
    )

    assert result == expected
    assert recover.await_count == 1
    assert recover.await_args.kwargs["user_id"] == authenticated_user.id
    assert recover.await_args.kwargs["older_than"].tzinfo is datetime.UTC
