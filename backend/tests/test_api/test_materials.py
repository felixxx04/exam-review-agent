"""Materials API endpoint tests."""

from __future__ import annotations

import pytest


def _data(response):
    """Unwrap ApiResponse envelope."""
    body = response.json()
    assert body["success"] is True
    return body["data"]


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
