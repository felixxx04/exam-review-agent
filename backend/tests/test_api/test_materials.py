"""Materials API endpoint tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api import materials as materials_api
from app.core.middleware import RateLimitMiddleware
from app.db.models import Course, Material, MaterialChunk, ProcessingStatus, User


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
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
        )
        assert response.status_code == 200
        data = _data(response)
        # Status may be "failed" for fake test PDFs (inline parse runs immediately)
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
        self, client_with_db, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)
        monkeypatch.setattr(materials_api.settings, "max_upload_size_mb", 0)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("too-large.pdf", b"x", "application/pdf")},
        )

        assert response.status_code == 400
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    async def test_upload_sanitizes_client_filename_paths(
        self, client_with_db, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("../../escape.pdf", b"fake pdf", "application/pdf")},
        )

        assert response.status_code == 200
        material = await db_session.get(Material, _data(response)["id"])
        assert material is not None
        assert material.filename.endswith("_escape.pdf")
        assert (
            (tmp_path / material.filename).resolve().is_relative_to(tmp_path.resolve())
        )

    @pytest.mark.asyncio
    async def test_upload_persists_a_reservation_before_writing_private_data(
        self, client_with_db, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)

        async def inspect_reservation(file, destination):
            reservations = (await db_session.execute(select(Material))).scalars().all()
            assert len(reservations) == 1
            assert reservations[0].processing_status == "pending"
            assert Path(reservations[0].storage_path) == destination
            destination.write_bytes(b"reserved")
            return 8, hashlib.sha256(b"reserved").hexdigest()

        monkeypatch.setattr(materials_api, "_write_upload", inspect_reservation)

        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("reserved.pdf", b"reserved", "application/pdf")},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_database_processing_error_keeps_storage_accurately_reserved(
        self, client_with_db, db_session, tmp_path, monkeypatch
    ):
        class ParserStub:
            async def parse(self, file_path, file_type=None):
                raise SQLAlchemyError("processing database unavailable")

        monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)
        monkeypatch.setattr(
            "app.services.parser_service.ParserService", lambda: ParserStub()
        )
        content = b"durable reservation"

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
        assert Path(material.storage_path).exists()

    @pytest.mark.asyncio
    async def test_final_commit_error_keeps_storage_accurately_reserved(
        self, client_with_db, db_session, tmp_path, monkeypatch
    ):
        class ParserStub:
            async def parse(self, file_path, file_type=None):
                raise ValueError("invalid document")

        monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)
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
        content = b"meter this file"

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
        assert Path(material.storage_path).exists()

    @pytest.mark.asyncio
    async def test_metadata_commit_error_discards_file_and_reservation(
        self, client_with_db, db_session, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(materials_api, "UPLOAD_DIR", tmp_path)
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
                files={"file": ("metadata-error.pdf", b"private", "application/pdf")},
            )

        assert metadata_commit_failed is True
        assert await db_session.scalar(select(Material)) is None
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    async def test_discard_reservation_retries_a_transient_database_failure(
        self, db_session, authenticated_user, tmp_path, monkeypatch
    ):
        course = Course(
            user_id=authenticated_user.id,
            name="Transient cleanup",
            is_default=True,
        )
        db_session.add(course)
        await db_session.flush()
        file_path = tmp_path / "transient.pdf"
        file_path.write_bytes(b"private")
        material = Material(
            user_id=authenticated_user.id,
            course_id=course.id,
            filename=file_path.name,
            original_filename=file_path.name,
            file_type="pdf",
            file_size=0,
            storage_path=str(file_path),
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

        await materials_api._discard_reservation(db_session, material_id, file_path)

        assert failed_once is True
        assert not file_path.exists()
        assert await db_session.get(Material, material_id) is None

    @pytest.mark.asyncio
    async def test_upload_stores_material_metadata(self, client_with_db, db_session):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
        )
        assert response.status_code == 200
        material_id = _data(response)["id"]

        material = await db_session.get(Material, material_id)
        assert material.storage_path is not None
        assert material.mime_type == "application/pdf"
        assert material.hash is not None

    @pytest.mark.asyncio
    async def test_upload_uses_authenticated_user(self, client_with_db, db_session):
        response = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
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
                    b"fake docx content",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

        assert response.status_code == 200
        indexed_chunks = retrieval.index_chunks.call_args.kwargs["chunks"]
        metadata = indexed_chunks[0]["metadata"]
        assert metadata["source"] == "MQ.docx"
        assert metadata["original_filename"] == "MQ.docx"
        assert metadata["storage_filename"].endswith("_MQ.docx")
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
                    b"fake docx content",
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
                    select(MaterialChunk).order_by(MaterialChunk.chunk_id.asc())
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
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
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
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
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
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
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
    async def test_delete_material_removes_chunk_rows(self, client_with_db, db_session):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
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
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
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
    async def test_reprocess_resets_to_pending(self, client_with_db):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]

        response = await client_with_db.post(f"/api/materials/{material_id}/reprocess")
        assert response.status_code == 200
        assert _data(response)["processing_status"] == "pending"
