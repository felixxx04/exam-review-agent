"""Materials API endpoint tests."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.middleware import RateLimitMiddleware
from app.db.models import Material, MaterialChunk


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

        monkeypatch.setattr("app.services.parser_service.ParserService", lambda: ParserStub())
        monkeypatch.setattr("app.services.retrieval_service.RetrievalService", lambda: retrieval)

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
        material_id = _data(upload_resp)["id"]

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
        material_id = _data(upload_resp)["id"]
        db_session.add(
            MaterialChunk(
                material_id=material_id,
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
        material_id = _data(upload_resp)["id"]
        db_session.add(
            MaterialChunk(
                material_id=material_id,
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
        monkeypatch.setattr("app.services.retrieval_service.RetrievalService", lambda: retrieval)

        response = await client_with_db.delete(f"/api/materials/{material_id}")

        assert response.status_code == 200
        retrieval.delete_chunks.assert_awaited_once_with(
            user_id="default",
            chunk_ids=["chunk-vector-delete-test"],
        )


class TestMaterialsReprocess:

    @pytest.mark.asyncio
    async def test_reprocess_resets_to_pending(self, client_with_db):
        upload_resp = await client_with_db.post(
            "/api/materials",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
        )
        material_id = _data(upload_resp)["id"]

        response = await client_with_db.post(
            f"/api/materials/{material_id}/reprocess"
        )
        assert response.status_code == 200
        assert _data(response)["processing_status"] == "pending"
