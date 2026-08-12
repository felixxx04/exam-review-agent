"""Materials API endpoint tests."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from unittest.mock import AsyncMock

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.api import materials as materials_api
from app.core.auth import AuthenticatedUser
from app.core.exceptions import AppException
from app.core.middleware import RateLimitMiddleware
from app.db.models import (
    Course,
    Material,
    MaterialChunk,
    ProcessingStatus,
    StorageStatus,
    User,
)
from app.services.material_storage_cleanup import recover_stale_material_reservations


def _minimal_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length 36 >>\nstream\nBT /F1 12 Tf 72 720 Td (test) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(payload)


def _minimal_docx() -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_STORED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>test</w:t></w:r></w:p>"
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>'
            "</w:body></w:document>",
        )
    return stream.getvalue()


MINIMAL_PDF = _minimal_pdf()
MINIMAL_DOCX = _minimal_docx()


def _data(response):
    """Unwrap ApiResponse envelope."""
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.fixture(autouse=True)
def reset_rate_limit():
    RateLimitMiddleware.reset()
    yield
    RateLimitMiddleware.reset()


class TestMaterialsUpload:
    @pytest.mark.asyncio
    async def test_upload_material_returns_pending_status(self, client_with_db):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        assert response.status_code == 200
        data = _data(response)
        # Inline parsing can fail independently after the object upload succeeds.
        assert data["processing_status"] in ("failed", "ready", "pending")
        assert data["original_filename"] == "test.pdf"
        assert data["file_type"] == "pdf"

    @pytest.mark.asyncio
    async def test_upload_rejects_unsupported_file_type(self, client_with_db):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.txt", b"plain text", "text/plain")},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_rejects_empty_filename(self, client_with_db):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("", b"content", "application/pdf")},
        )
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_upload_rejects_oversized_file_without_leaving_staged_data(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        monkeypatch.setattr(materials_api.settings, "max_upload_size_mb", 0)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("too-large.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
        assert (await db_session.execute(select(Material))).scalars().all() == []
        assert object_storage.objects == {}

    @pytest.mark.asyncio
    async def test_upload_accepts_an_exact_file_limit_inside_a_multipart_envelope(
        self, client_with_db, object_storage, monkeypatch
    ):
        from app.services.parser_service import ParseResult

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(chunks=[], page_count=1)

        maximum_size = 1024 * 1024
        content = b"%PDF-" + b"x" * (maximum_size - len(b"%PDF-"))
        monkeypatch.setattr(materials_api.settings, "max_upload_size_mb", 1)
        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("at-limit.pdf", content, "application/pdf")},
        )

        assert response.status_code == 200
        assert _data(response)["file_size"] == maximum_size
        assert len(object_storage.objects) == 1

    @pytest.mark.asyncio
    async def test_upload_rejects_a_file_one_byte_over_the_limit_with_a_stable_error(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        maximum_size = 1024 * 1024
        content = b"%PDF-" + b"x" * (maximum_size + 1 - len(b"%PDF-"))
        monkeypatch.setattr(materials_api.settings, "max_upload_size_mb", 1)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("one-byte-over.pdf", content, "application/pdf")},
        )

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
        assert await db_session.scalar(select(Material)) is None
        assert object_storage.objects == {}

    @pytest.mark.asyncio
    async def test_upload_sanitizes_client_filename_paths(
        self, client_with_db, db_session, object_storage
    ):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("../../escape.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 200
        material = await db_session.get(Material, _data(response)["id"])
        assert material is not None
        assert material.filename == material.object_id
        assert material.original_filename == "escape.pdf"
        assert material.storage_path is None
        assert material.object_key in object_storage.objects
        assert "escape.pdf" not in material.object_key

    @pytest.mark.asyncio
    async def test_upload_persists_a_reservation_before_writing_private_data(
        self, client_with_db, db_session, monkeypatch
    ):
        async def inspect_reservation(file, destination):
            reservations = (await db_session.execute(select(Material))).scalars().all()
            assert len(reservations) == 1
            assert reservations[0].storage_status == StorageStatus.RESERVED
            assert reservations[0].object_key
            destination.write_bytes(MINIMAL_PDF)
            return len(MINIMAL_PDF), hashlib.sha256(MINIMAL_PDF).hexdigest()

        monkeypatch.setattr(materials_api, "_stage_upload", inspect_reservation)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("reserved.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_holds_the_user_lock_before_staging_private_data(
        self, client_with_db, monkeypatch
    ):
        original_lock_upload = materials_api.QuotaService.lock_upload
        lock_calls = 0

        async def recording_lock(service, user_id):
            nonlocal lock_calls
            lock_calls += 1
            return await original_lock_upload(service, user_id)

        async def inspect_stage(file, destination):
            # The first call reserves the file slot. The second must protect staging.
            assert lock_calls >= 2
            destination.write_bytes(MINIMAL_PDF)
            return len(MINIMAL_PDF), hashlib.sha256(MINIMAL_PDF).hexdigest()

        monkeypatch.setattr(materials_api.QuotaService, "lock_upload", recording_lock)
        monkeypatch.setattr(materials_api, "_stage_upload", inspect_stage)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("locked.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_reclaims_its_reservation_when_staging_fails(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        async def broken_stage(file, destination):
            raise OSError("client stream interrupted")

        monkeypatch.setattr(materials_api, "_stage_upload", broken_stage)

        with pytest.raises(OSError):
            await client_with_db.post(
                "/api/materials",
                files={"file": ("broken.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert (await db_session.execute(select(Material))).scalars().all() == []
        assert object_storage.objects == {}

    @pytest.mark.asyncio
    async def test_cancelled_upload_after_object_write_keeps_a_recovery_tombstone(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        original_put_file = object_storage.put_file

        async def cancel_after_put(**kwargs):
            await original_put_file(**kwargs)
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
            await asyncio.sleep(0)

        monkeypatch.setattr(object_storage, "put_file", cancel_after_put)

        # ASGI middleware converts a cancelled request into this transport error.
        with pytest.raises(RuntimeError, match="No response returned"):
            await client_with_db.post(
                "/api/materials",
                files={"file": ("cancelled.pdf", MINIMAL_PDF, "application/pdf")},
            )

        material = await db_session.scalar(select(Material))
        assert material is not None
        assert material.storage_status == StorageStatus.DELETING
        assert material.object_write_uncertain is True
        assert material.object_key in object_storage.objects

    @pytest.mark.asyncio
    async def test_cancelled_upload_waits_for_an_inflight_object_write_before_cleanup(
        self, db_session, authenticated_user, object_storage, monkeypatch
    ):
        put_started = asyncio.Event()
        release_put = asyncio.Event()
        object_written = asyncio.Event()
        cleanup_finished = asyncio.Event()
        original_put_file = object_storage.put_file
        original_delete_object = object_storage.delete_object

        async def completes_after_cancellation(**kwargs):
            async def finish_write():
                put_started.set()
                await release_put.wait()
                stored = await original_put_file(**kwargs)
                object_written.set()
                return stored

            completion = asyncio.create_task(finish_write())
            return await asyncio.shield(completion)

        async def record_completed_cleanup(**kwargs):
            await original_delete_object(**kwargs)
            cleanup_finished.set()

        monkeypatch.setattr(object_storage, "put_file", completes_after_cancellation)
        monkeypatch.setattr(object_storage, "delete_object", record_completed_cleanup)

        upload_file = UploadFile(
            file=BytesIO(MINIMAL_PDF),
            filename="cancelled-inflight.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        request_task = asyncio.create_task(
            materials_api.upload_material(
                file=upload_file,
                current_user=AuthenticatedUser(
                    id=authenticated_user.id,
                    username=authenticated_user.username,
                    role=authenticated_user.role,
                    session_id="test-session",
                ),
                db=db_session,
                storage=object_storage,
            )
        )
        await asyncio.wait_for(put_started.wait(), timeout=1)
        request_task.cancel()

        # The old direct await compensates before the shielded PUT finishes.
        # Release it only after that early deletion; the fixed path reaches
        # this timeout because it waits for the in-flight PUT first.
        try:
            await asyncio.wait_for(cleanup_finished.wait(), timeout=1)
        except TimeoutError:
            pass
        release_put.set()

        await asyncio.gather(request_task, return_exceptions=True)
        await asyncio.wait_for(object_written.wait(), timeout=1)

        assert (await db_session.execute(select(Material))).scalars().all() == []
        assert object_storage.objects == {}

    @pytest.mark.asyncio
    async def test_database_processing_error_keeps_storage_accurately_reserved(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        class ParserStub:
            async def parse(self, file_path, file_type=None):
                raise SQLAlchemyError("processing database unavailable")

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        content = MINIMAL_PDF

        with pytest.raises(SQLAlchemyError):
            await client_with_db.post(
                "/api/materials",
                files={"file": ("database-error.pdf", content, "application/pdf")},
            )

        material = await db_session.scalar(select(Material))
        assert material is not None
        await db_session.refresh(material)
        assert material.processing_status == ProcessingStatus.PENDING
        assert material.file_size == len(content)
        assert material.hash == hashlib.sha256(content).hexdigest()
        assert material.storage_status == StorageStatus.AVAILABLE
        assert material.object_key in object_storage.objects

    @pytest.mark.asyncio
    async def test_final_commit_error_keeps_storage_accurately_reserved(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        class ParserStub:
            async def parse(self, file_path, file_type=None):
                raise ValueError("invalid document")

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        original_commit = db_session.commit

        async def fail_processing_commit():
            material = next(
                (
                    instance
                    for instance in db_session.identity_map.values()
                    if isinstance(instance, Material)
                ),
                None,
            )
            if (
                material is not None
                and material.processing_status != ProcessingStatus.PENDING
            ):
                raise SQLAlchemyError("final commit unavailable")
            await original_commit()

        monkeypatch.setattr(db_session, "commit", fail_processing_commit)
        content = MINIMAL_PDF

        with pytest.raises(SQLAlchemyError):
            await client_with_db.post(
                "/api/materials",
                files={"file": ("final-error.pdf", content, "application/pdf")},
            )

        material = await db_session.scalar(select(Material))
        assert material is not None
        await db_session.refresh(material)
        assert material.processing_status == ProcessingStatus.PENDING
        assert material.file_size == len(content)
        assert material.hash == hashlib.sha256(content).hexdigest()
        assert material.storage_status == StorageStatus.AVAILABLE
        assert material.object_key in object_storage.objects

    @pytest.mark.asyncio
    async def test_final_database_commit_compensates_indexed_vectors(
        self, client_with_db, db_session, authenticated_user, monkeypatch
    ):
        from app.services.parser_service import Chunk, ParseResult

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(
                    chunks=[Chunk(text="commit failure vector cleanup")], page_count=1
                )

        class RecordingRetrieval:
            def __init__(self) -> None:
                self.indexed: set[str] = set()

            async def index_chunks(
                self, *, user_id, chunks, course_id, chunk_ids=None
            ) -> list[str]:
                ids = chunk_ids or ["commit-failure-indexed-chunk"]
                self.indexed.update(ids)
                return ids

            async def delete_chunks(self, *, user_id, chunk_ids, course_id) -> None:
                self.indexed.difference_update(chunk_ids)

        retrieval = RecordingRetrieval()
        original_commit = db_session.commit
        final_commit_failed = False

        async def fail_index_metadata_commit():
            nonlocal final_commit_failed
            material = next(
                (
                    instance
                    for instance in db_session.identity_map.values()
                    if isinstance(instance, Material)
                ),
                None,
            )
            if (
                not final_commit_failed
                and material is not None
                and material.processing_status == ProcessingStatus.READY
            ):
                final_commit_failed = True
                raise SQLAlchemyError("indexed metadata commit unavailable")
            await original_commit()

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )
        monkeypatch.setattr(db_session, "commit", fail_index_metadata_commit)

        with pytest.raises(SQLAlchemyError, match="indexed metadata"):
            await client_with_db.post(
                "/api/materials",
                files={"file": ("index-commit.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert final_commit_failed is True
        assert retrieval.indexed == set()
        assert (await db_session.scalar(select(MaterialChunk))) is None

    @pytest.mark.asyncio
    async def test_cancelled_final_database_commit_compensates_indexed_vectors(
        self, db_session, authenticated_user, object_storage, monkeypatch
    ):
        from app.services.parser_service import Chunk, ParseResult

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(
                    chunks=[Chunk(text="cancelled commit vector cleanup")], page_count=1
                )

        class RecordingRetrieval:
            def __init__(self) -> None:
                self.indexed: set[str] = set()

            async def index_chunks(
                self, *, user_id, chunks, course_id, chunk_ids=None
            ) -> list[str]:
                assert chunk_ids is not None
                self.indexed.update(chunk_ids)
                return chunk_ids

            async def delete_chunks(self, *, user_id, chunk_ids, course_id) -> None:
                self.indexed.difference_update(chunk_ids)

        retrieval = RecordingRetrieval()
        original_commit = db_session.commit
        cancelled_once = False

        async def cancel_ready_metadata_commit():
            nonlocal cancelled_once
            material = next(
                (
                    instance
                    for instance in db_session.identity_map.values()
                    if isinstance(instance, Material)
                ),
                None,
            )
            if (
                not cancelled_once
                and material is not None
                and material.processing_status == ProcessingStatus.READY
            ):
                cancelled_once = True
                raise asyncio.CancelledError()
            await original_commit()

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )
        monkeypatch.setattr(db_session, "commit", cancel_ready_metadata_commit)
        upload_file = UploadFile(
            file=BytesIO(MINIMAL_PDF),
            filename="cancelled-index-commit.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )

        with pytest.raises(asyncio.CancelledError):
            await materials_api.upload_material(
                file=upload_file,
                current_user=AuthenticatedUser(
                    id=authenticated_user.id,
                    username=authenticated_user.username,
                    role=authenticated_user.role,
                    session_id="test-session",
                ),
                db=db_session,
                storage=object_storage,
            )

        assert cancelled_once is True
        assert retrieval.indexed == set()
        material = await db_session.scalar(select(Material))
        assert material is not None
        assert material.processing_status == ProcessingStatus.FAILED
        assert await db_session.scalar(select(MaterialChunk)) is None

    @pytest.mark.asyncio
    async def test_partial_index_failure_keeps_durable_chunk_cleanup_intent_for_recovery(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        from app.services.parser_service import Chunk, ParseResult

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(
                    chunks=[Chunk(text="partial index durable cleanup")], page_count=1
                )

        class PartiallyFailingRetrieval:
            def __init__(self) -> None:
                self.indexed: set[str] = set()
                self.delete_attempts = 0

            async def index_chunks(
                self, *, user_id, chunks, course_id, chunk_ids=None
            ) -> list[str]:
                assert chunk_ids is not None
                self.indexed.add(chunk_ids[0])
                raise RuntimeError("indexing stopped after a partial write")

            async def delete_chunks(self, *, user_id, chunk_ids, course_id) -> None:
                self.delete_attempts += 1
                if self.delete_attempts == 1:
                    raise RuntimeError("index cleanup temporarily unavailable")
                self.indexed.difference_update(chunk_ids)

        retrieval = PartiallyFailingRetrieval()
        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("partial-index.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 200
        material = await db_session.scalar(select(Material))
        assert material is not None
        chunk_rows = (
            (
                await db_session.execute(
                    select(MaterialChunk).where(
                        MaterialChunk.material_id == material.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [row.chunk_id for row in chunk_rows] == list(retrieval.indexed)
        assert material.processing_status == ProcessingStatus.FAILED

        material.created_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            hours=2
        )
        await db_session.commit()
        report = await recover_stale_material_reservations(
            db_session,
            object_storage,
            older_than=datetime.datetime.now(datetime.UTC)
            - datetime.timedelta(minutes=1),
        )

        await db_session.refresh(material)
        assert report.scanned == 1
        assert report.pending == 0
        assert material.storage_status == StorageStatus.AVAILABLE
        assert material.processing_status == ProcessingStatus.FAILED
        assert retrieval.indexed == set()
        assert (
            await db_session.scalar(
                select(MaterialChunk).where(MaterialChunk.material_id == material.id)
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_stale_processing_attempt_is_fenced_before_writing_vectors(
        self, db_session, authenticated_user, object_storage, monkeypatch
    ):
        from app.services.parser_service import Chunk, ParseResult

        intent_committed = asyncio.Event()
        continue_processing = asyncio.Event()

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(
                    chunks=[Chunk(text="stale worker must not resurrect vectors")],
                    page_count=1,
                )

        class RecordingRetrieval:
            def __init__(self) -> None:
                self.index_calls = 0

            async def index_chunks(self, **kwargs) -> list[str]:
                self.index_calls += 1
                return kwargs["chunk_ids"]

            async def delete_chunks(self, **kwargs) -> None:
                return None

        retrieval = RecordingRetrieval()
        original_lock_upload = materials_api.QuotaService.lock_upload
        lock_calls = 0

        async def pause_before_reacquiring_lock(service, user_id):
            nonlocal lock_calls
            lock_calls += 1
            # The upload acquires the shared user lock five times before the
            # durable indexing intent. Pause exactly between that intent's
            # commit and the worker's lock reacquisition.
            if lock_calls == 6:
                intent_committed.set()
                await continue_processing.wait()
            return await original_lock_upload(service, user_id)

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )
        monkeypatch.setattr(
            materials_api.QuotaService,
            "lock_upload",
            pause_before_reacquiring_lock,
        )
        upload_file = UploadFile(
            file=BytesIO(MINIMAL_PDF),
            filename="fenced-stale-worker.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        task = asyncio.create_task(
            materials_api.upload_material(
                file=upload_file,
                current_user=AuthenticatedUser(
                    id=authenticated_user.id,
                    username=authenticated_user.username,
                    role=authenticated_user.role,
                    session_id="test-session",
                ),
                db=db_session,
                storage=object_storage,
            )
        )
        await asyncio.wait_for(intent_committed.wait(), timeout=1)

        material = await db_session.scalar(select(Material))
        assert material is not None
        material.processing_lease_expires_at = datetime.datetime.now(
            datetime.UTC
        ) - datetime.timedelta(seconds=1)
        material.created_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            hours=2
        )
        await db_session.commit()
        try:
            report = await recover_stale_material_reservations(
                db_session,
                object_storage,
                older_than=datetime.datetime.now(datetime.UTC)
                - datetime.timedelta(minutes=1),
            )
            assert report.scanned == 1
            await db_session.refresh(material)
            assert material.processing_status == ProcessingStatus.FAILED
            assert await db_session.scalar(select(MaterialChunk)) is None
        finally:
            continue_processing.set()
        result = await asyncio.wait_for(task, timeout=1)

        assert result.data is not None
        assert retrieval.index_calls == 0
        await db_session.refresh(material)
        assert material.processing_status == ProcessingStatus.FAILED
        assert await db_session.scalar(select(MaterialChunk)) is None

    @pytest.mark.asyncio
    async def test_cancelled_indexing_keeps_durable_chunks_for_recovery(
        self, db_session, authenticated_user, object_storage, monkeypatch
    ):
        from app.services.parser_service import Chunk, ParseResult

        indexing_started = asyncio.Event()

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(
                    chunks=[Chunk(text="cancelled index durable cleanup")], page_count=1
                )

        class CancellingRetrieval:
            def __init__(self) -> None:
                self.indexed: set[str] = set()
                self.delete_attempts = 0

            async def index_chunks(
                self, *, user_id, chunks, course_id, chunk_ids=None
            ) -> list[str]:
                assert chunk_ids is not None
                self.indexed.update(chunk_ids)
                indexing_started.set()
                await asyncio.Event().wait()
                return chunk_ids

            async def delete_chunks(self, *, user_id, chunk_ids, course_id) -> None:
                self.delete_attempts += 1
                if self.delete_attempts == 1:
                    raise RuntimeError("index cleanup temporarily unavailable")
                self.indexed.difference_update(chunk_ids)

        retrieval = CancellingRetrieval()
        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )
        upload_file = UploadFile(
            file=BytesIO(MINIMAL_PDF),
            filename="cancelled-index.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        task = asyncio.create_task(
            materials_api.upload_material(
                file=upload_file,
                current_user=AuthenticatedUser(
                    id=authenticated_user.id,
                    username=authenticated_user.username,
                    role=authenticated_user.role,
                    session_id="test-session",
                ),
                db=db_session,
                storage=object_storage,
            )
        )
        await asyncio.wait_for(indexing_started.wait(), timeout=1)
        task.cancel()

        result = await asyncio.gather(task, return_exceptions=True)

        assert isinstance(result[0], asyncio.CancelledError)
        material = await db_session.scalar(select(Material))
        assert material is not None
        chunk_rows = (
            (
                await db_session.execute(
                    select(MaterialChunk).where(
                        MaterialChunk.material_id == material.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {row.chunk_id for row in chunk_rows} == retrieval.indexed
        assert material.processing_status == ProcessingStatus.FAILED

        material.created_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            hours=2
        )
        await db_session.commit()
        await recover_stale_material_reservations(
            db_session,
            object_storage,
            older_than=datetime.datetime.now(datetime.UTC)
            - datetime.timedelta(minutes=1),
        )

        assert retrieval.indexed == set()
        assert retrieval.delete_attempts == 2

    @pytest.mark.asyncio
    async def test_metadata_commit_error_discards_file_and_reservation(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        original_commit = db_session.commit
        metadata_commit_failed = False

        async def fail_metadata_commit():
            nonlocal metadata_commit_failed
            material = next(
                (
                    instance
                    for instance in db_session.identity_map.values()
                    if isinstance(instance, Material)
                ),
                None,
            )
            if (
                not metadata_commit_failed
                and material is not None
                and material.processing_status == ProcessingStatus.PENDING
                and material.file_size > 0
            ):
                metadata_commit_failed = True
                raise SQLAlchemyError("metadata commit unavailable")
            await original_commit()

        monkeypatch.setattr(db_session, "commit", fail_metadata_commit)

        with pytest.raises(SQLAlchemyError):
            await client_with_db.post(
                "/api/materials",
                files={"file": ("metadata-error.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert metadata_commit_failed is True
        assert await db_session.scalar(select(Material)) is None
        assert object_storage.objects == {}
        assert object_storage.deleted == []

    @pytest.mark.asyncio
    async def test_upload_commits_validated_reservation_before_object_write(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        original_commit = db_session.commit
        original_put_file = object_storage.put_file
        expected_hash = hashlib.sha256(MINIMAL_PDF).hexdigest()
        metadata_committed = False

        async def record_metadata_commit():
            nonlocal metadata_committed
            material = next(
                (
                    instance
                    for instance in db_session.identity_map.values()
                    if isinstance(instance, Material)
                ),
                None,
            )
            if (
                material is not None
                and material.file_size == len(MINIMAL_PDF)
                and material.hash == expected_hash
            ):
                metadata_committed = True
            await original_commit()

        async def require_durable_metadata_before_write(**kwargs):
            assert metadata_committed is True
            return await original_put_file(**kwargs)

        monkeypatch.setattr(db_session, "commit", record_metadata_commit)
        monkeypatch.setattr(
            object_storage, "put_file", require_durable_metadata_before_write
        )

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("durable-reservation.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 200
        assert metadata_committed is True

    @pytest.mark.asyncio
    async def test_upload_reports_account_deletion_when_reserved_material_disappears(
        self, client_with_db, db_session, object_storage, monkeypatch
    ):
        async def material_is_being_deleted(*args, **kwargs):
            return None

        monkeypatch.setattr(
            materials_api, "_get_owned_material", material_is_being_deleted
        )

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("deleted-course.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ACCOUNT_DELETION_IN_PROGRESS"
        assert await db_session.scalar(select(Material)) is None
        assert object_storage.objects == {}

    @pytest.mark.asyncio
    async def test_discard_reservation_retries_a_transient_database_failure(
        self, db_session, authenticated_user, object_storage, monkeypatch
    ):
        course = Course(
            user_id=authenticated_user.id,
            name="Transient cleanup",
            is_default=True,
        )
        db_session.add(course)
        await db_session.flush()
        object_key = (
            f"users/{authenticated_user.id}/courses/{course.id}/materials/"
            "transient/objects/transient-object"
        )
        object_storage.objects[object_key] = MINIMAL_PDF
        material = Material(
            user_id=authenticated_user.id,
            course_id=course.id,
            filename="transient-object",
            original_filename="transient.pdf",
            file_type="pdf",
            file_size=0,
            object_key=object_key,
            storage_status=StorageStatus.RESERVED,
        )
        db_session.add(material)
        await db_session.commit()
        material_id = material.id
        original_commit = db_session.commit
        failed_once = False

        async def fail_once():
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise SQLAlchemyError("cleanup commit unavailable")
            await original_commit()

        monkeypatch.setattr(db_session, "commit", fail_once)

        await materials_api._discard_reservation(
            db_session, material_id, storage=object_storage, delete_object=True
        )

        assert failed_once is True
        assert object_key not in object_storage.objects
        assert await db_session.get(Material, material_id) is None

    @pytest.mark.asyncio
    async def test_upload_stores_material_metadata(
        self, client_with_db, db_session, object_storage
    ):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        assert response.status_code == 200
        material_id = _data(response)["id"]

        material = await db_session.get(Material, material_id)
        assert material.storage_path is None
        assert material.object_key in object_storage.objects
        assert material.object_version_id == "in-memory-version"
        assert material.object_etag == "in-memory-etag"
        assert material.mime_type == "application/pdf"
        assert material.hash is not None

    @pytest.mark.asyncio
    async def test_upload_uses_authenticated_user(self, client_with_db, db_session):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )

        assert response.status_code == 200
        users = (await db_session.execute(select(User))).scalars().all()
        assert len(users) == 1
        assert users[0].username == "test_user"

    @pytest.mark.asyncio
    async def test_upload_indexes_chunks_with_original_filename_metadata(
        self, client_with_db, monkeypatch
    ):
        class ParserStub:
            async def parse(self, file_path, file_type=None):
                from app.services.parser_service import Chunk, ParseResult

                return ParseResult(
                    chunks=[
                        Chunk(
                            text="MQ content",
                            metadata={"source": "stored_MQ.docx", "file_type": "docx"},
                        )
                    ],
                    page_count=1,
                )

        retrieval = AsyncMock()
        retrieval.index_chunks = AsyncMock(return_value=["chunk-1"])

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )

        response = await client_with_db.post(
            "/api/materials",
            files={
                "file": (
                    "MQ.docx",
                    MINIMAL_DOCX,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        assert response.status_code == 200
        indexed_chunks = retrieval.index_chunks.call_args.kwargs["chunks"]
        metadata = indexed_chunks[0]["metadata"]
        assert metadata["source"] == "MQ.docx"
        assert metadata["original_filename"] == "MQ.docx"
        assert metadata["storage_filename"] != "MQ.docx"
        assert metadata["storage_filename"].isalnum()
        assert metadata["material_id"] == _data(response)["id"]

    @pytest.mark.asyncio
    async def test_upload_indexes_normalized_chunks(
        self, client_with_db, db_session, monkeypatch
    ):
        from app.services.parser_service import Chunk, ParseResult

        class ParserStub:
            async def parse(self, file_path, file_type=None):
                return ParseResult(
                    chunks=[
                        Chunk(
                            text="original long section",
                            metadata={
                                "source": "stored_Redis.docx",
                                "file_type": "docx",
                            },
                            chunk_index=0,
                        )
                    ],
                    page_count=1,
                )

        class ChunkingStub:
            def normalize(self, chunks):
                return [
                    Chunk(
                        text="normalized window one",
                        metadata={
                            **chunks[0].metadata,
                            "chunking": "overlap_window",
                            "parent_chunk_index": 0,
                            "window_index": 0,
                        },
                        chunk_index=0,
                    ),
                    Chunk(
                        text="normalized window two",
                        metadata={
                            **chunks[0].metadata,
                            "chunking": "overlap_window",
                            "parent_chunk_index": 0,
                            "window_index": 1,
                        },
                        chunk_index=1,
                    ),
                ]

        retrieval = AsyncMock()
        retrieval.index_chunks = AsyncMock(return_value=["chunk-1", "chunk-2"])

        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        monkeypatch.setattr(
            "app.services.chunking_service.ChunkingService", lambda: ChunkingStub()
        )
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )

        response = await client_with_db.post(
            "/api/materials",
            files={
                "file": (
                    "Redis.docx",
                    MINIMAL_DOCX,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        assert response.status_code == 200
        data = _data(response)
        assert data["chunk_count"] == 2

        indexed_chunks = retrieval.index_chunks.call_args.kwargs["chunks"]
        assert [chunk["text"] for chunk in indexed_chunks] == [
            "normalized window one",
            "normalized window two",
        ]
        rows = (
            (
                await db_session.execute(
                    select(MaterialChunk).order_by(MaterialChunk.id.asc())
                )
            )
            .scalars()
            .all()
        )
        assert [row.text_preview for row in rows] == [
            "normalized window one",
            "normalized window two",
        ]
        assert [row.content for row in rows] == [
            "normalized window one",
            "normalized window two",
        ]
        assert (
            rows[0].content_hash == hashlib.sha256(b"normalized window one").hexdigest()
        )
        assert rows[0].lexical_tokens
        assert rows[0].chunk_metadata["source"] == "Redis.docx"


class TestMaterialsList:
    @pytest.mark.asyncio
    async def test_list_materials_returns_empty_list(self, client_with_db):
        response = await client_with_db.get("/api/materials")
        assert response.status_code == 200
        data = _data(response)
        assert data["total"] == 0
        assert data["materials"] == []

    @pytest.mark.asyncio
    async def test_list_materials_after_upload(self, client_with_db):
        await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        response = await client_with_db.get("/api/materials")
        assert response.status_code == 200
        data = _data(response)
        assert data["total"] == 1
        assert data["materials"][0]["original_filename"] == "test.pdf"


class TestMaterialsDetail:
    @pytest.mark.asyncio
    async def test_get_material_not_found(self, client_with_db):
        response = await client_with_db.get("/api/materials/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_material_after_upload(self, client_with_db):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_data = _data(upload_resp)
        material_id = material_data["id"]

        response = await client_with_db.get(f"/api/materials/{material_id}")
        assert response.status_code == 200
        assert _data(response)["id"] == material_id
        assert _data(response)["original_filename"] == "test.pdf"


class TestMaterialsDelete:
    @pytest.mark.asyncio
    async def test_delete_material(self, client_with_db):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]

        response = await client_with_db.delete(f"/api/materials/{material_id}")
        assert response.status_code == 200

        get_resp = await client_with_db.get(f"/api/materials/{material_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_material(self, client_with_db):
        response = await client_with_db.delete("/api/materials/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_reclaims_a_stale_processing_material(
        self, client_with_db, db_session
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("stale.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]
        material = await db_session.get(Material, material_id)
        assert material is not None
        material.processing_status = ProcessingStatus.PROCESSING
        material.processing_lease_expires_at = None
        await db_session.commit()

        response = await client_with_db.delete(f"/api/materials/{material_id}")

        assert response.status_code == 200
        await db_session.refresh(material)
        assert material.storage_status == StorageStatus.DELETED

    @pytest.mark.asyncio
    async def test_delete_legacy_local_material_keeps_task_1_4_cleanup_working(
        self, client_with_db, db_session, authenticated_user, tmp_path, monkeypatch
    ):
        course = Course(
            user_id=authenticated_user.id,
            name="Legacy material",
            is_default=True,
        )
        db_session.add(course)
        await db_session.flush()
        legacy_path = tmp_path / "legacy.pdf"
        legacy_path.write_bytes(MINIMAL_PDF)
        material = Material(
            user_id=authenticated_user.id,
            course_id=course.id,
            filename=legacy_path.name,
            original_filename=legacy_path.name,
            file_type="pdf",
            file_size=len(MINIMAL_PDF),
            storage_backend="legacy_local",
            storage_status=StorageStatus.AVAILABLE,
            storage_path=str(legacy_path),
        )
        db_session.add(material)
        await db_session.commit()
        monkeypatch.setattr(materials_api, "LEGACY_UPLOAD_ROOT", tmp_path)

        response = await client_with_db.delete(f"/api/materials/{material.id}")

        assert response.status_code == 200
        assert not legacy_path.exists()
        await db_session.refresh(material)
        assert material.storage_status == StorageStatus.DELETED

    @pytest.mark.asyncio
    async def test_delete_material_removes_chunk_rows(self, client_with_db, db_session):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_data = _data(upload_resp)
        material_id = material_data["id"]
        db_session.add(
            MaterialChunk(
                material_id=material_id,
                user_id=1,
                course_id=material_data["course_id"],
                chunk_id="chunk-delete-test",
                text_preview="preview",
                page_number=1,
                token_count=3,
                embedding_id="chunk-delete-test",
            )
        )
        await db_session.commit()

        response = await client_with_db.delete(f"/api/materials/{material_id}")
        assert response.status_code == 200

        rows = (await db_session.execute(select(MaterialChunk))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_delete_material_removes_vector_chunks(
        self, client_with_db, db_session, monkeypatch
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_data = _data(upload_resp)
        material_id = material_data["id"]
        db_session.add(
            MaterialChunk(
                material_id=material_id,
                user_id=1,
                course_id=material_data["course_id"],
                chunk_id="chunk-vector-delete-test",
                text_preview="preview",
                page_number=1,
                token_count=3,
                embedding_id="chunk-vector-delete-test",
            )
        )
        await db_session.commit()

        retrieval = AsyncMock()
        retrieval.delete_chunks = AsyncMock()
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )

        response = await client_with_db.delete(f"/api/materials/{material_id}")

        assert response.status_code == 200
        retrieval.delete_chunks.assert_awaited_once_with(
            user_id="1",
            chunk_ids=["chunk-vector-delete-test"],
            course_id=1,
        )


class TestMaterialsReprocess:
    @pytest.mark.asyncio
    async def test_reprocess_cleans_a_ready_materials_existing_index_before_reset(
        self, client_with_db, db_session, monkeypatch
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("ready.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]
        material = await db_session.get(Material, material_id)
        assert material is not None
        material.processing_status = ProcessingStatus.READY
        db_session.add(
            MaterialChunk(
                material_id=material.id,
                user_id=material.user_id,
                course_id=material.course_id,
                chunk_id="ready-material-chunk",
                text_preview="ready material index",
                token_count=3,
                embedding_id="ready-material-chunk",
            )
        )
        await db_session.commit()

        retrieval = AsyncMock()
        retrieval.delete_chunks = AsyncMock()
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )

        response = await materials_api.reprocess_material(
            material_id,
            current_user=AuthenticatedUser(
                id=material.user_id,
                username="test_user",
                role="user",
                session_id="test-session",
            ),
            db=db_session,
        )

        assert response.data is not None
        assert response.data.processing_status == ProcessingStatus.PENDING
        retrieval.delete_chunks.assert_awaited_once_with(
            user_id=str(material.user_id),
            chunk_ids=["ready-material-chunk"],
            course_id=material.course_id,
        )
        assert (
            await db_session.scalar(
                select(MaterialChunk.id).where(MaterialChunk.material_id == material_id)
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_reprocess_keeps_a_recovery_visible_lease_when_cleanup_commit_fails(
        self, client_with_db, db_session, monkeypatch
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("ready.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]
        material = await db_session.get(Material, material_id)
        assert material is not None
        material.processing_status = ProcessingStatus.READY
        db_session.add(
            MaterialChunk(
                material_id=material.id,
                user_id=material.user_id,
                course_id=material.course_id,
                chunk_id="ready-material-crash-window",
                text_preview="ready material index",
                token_count=3,
                embedding_id="ready-material-crash-window",
            )
        )
        await db_session.commit()

        retrieval = AsyncMock()
        retrieval.delete_chunks = AsyncMock()
        monkeypatch.setattr(
            "app.services.retrieval_service.RetrievalService", lambda: retrieval
        )
        original_commit = db_session.commit
        commit_count = 0

        async def fail_final_commit():
            nonlocal commit_count
            commit_count += 1
            if commit_count == 2:
                raise SQLAlchemyError("final reprocess commit failed")
            await original_commit()

        monkeypatch.setattr(db_session, "commit", fail_final_commit)

        with pytest.raises(SQLAlchemyError):
            await materials_api.reprocess_material(
                material_id,
                current_user=AuthenticatedUser(
                    id=material.user_id,
                    username="test_user",
                    role="user",
                    session_id="test-session",
                ),
                db=db_session,
            )

        await db_session.refresh(material)
        assert material.processing_status == ProcessingStatus.PROCESSING
        assert material.processing_lease_expires_at is not None
        assert (
            await db_session.scalar(
                select(MaterialChunk.id).where(MaterialChunk.material_id == material_id)
            )
            is not None
        )

    @pytest.mark.asyncio
    async def test_reprocess_resets_to_pending_without_a_chunk_cleanup_intent(
        self, client_with_db, db_session
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]
        material = await db_session.get(Material, material_id)
        assert material is not None
        material.processing_status = ProcessingStatus.FAILED
        await db_session.execute(
            delete(MaterialChunk).where(MaterialChunk.material_id == material_id)
        )
        await db_session.commit()

        response = await materials_api.reprocess_material(
            material_id,
            current_user=AuthenticatedUser(
                id=material.user_id,
                username="test_user",
                role="user",
                session_id="test-session",
            ),
            db=db_session,
        )
        assert response.data is not None
        assert response.data.processing_status == "pending"

    @pytest.mark.asyncio
    async def test_reprocess_reclaims_a_stale_processing_material_without_chunk_intent(
        self, client_with_db, db_session
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("stale.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]
        material = await db_session.get(Material, material_id)
        assert material is not None
        material.processing_status = ProcessingStatus.PROCESSING
        material.processing_lease_expires_at = None
        await db_session.execute(
            delete(MaterialChunk).where(MaterialChunk.material_id == material_id)
        )
        await db_session.commit()

        response = await materials_api.reprocess_material(
            material_id,
            current_user=AuthenticatedUser(
                id=material.user_id,
                username="test_user",
                role="user",
                session_id="test-session",
            ),
            db=db_session,
        )

        assert response.data is not None
        assert response.data.processing_status == ProcessingStatus.PENDING

    @pytest.mark.asyncio
    async def test_reprocess_refuses_a_failed_material_with_chunk_cleanup_intent(
        self, client_with_db, db_session
    ):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("intent.pdf", MINIMAL_PDF, "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]
        material = await db_session.get(Material, material_id)
        assert material is not None
        material.processing_status = ProcessingStatus.FAILED
        db_session.add(
            MaterialChunk(
                material_id=material.id,
                user_id=material.user_id,
                course_id=material.course_id,
                chunk_id="failed-cleanup-intent",
                text_preview="durable cleanup intent",
                token_count=3,
                embedding_id="failed-cleanup-intent",
            )
        )
        await db_session.commit()
        with pytest.raises(AppException) as conflict:
            await materials_api.reprocess_material(
                material_id,
                current_user=AuthenticatedUser(
                    id=material.user_id,
                    username="test_user",
                    role="user",
                    session_id="test-session",
                ),
                db=db_session,
            )

        assert conflict.value.code == "CONFLICT"
        await db_session.refresh(material)
        assert material.processing_status == ProcessingStatus.FAILED
        assert (
            await db_session.scalar(
                select(MaterialChunk).where(
                    MaterialChunk.material_id == material_id,
                    MaterialChunk.chunk_id == "failed-cleanup-intent",
                )
            )
        ) is not None
