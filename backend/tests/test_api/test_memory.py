from __future__ import annotations

import pytest


def _data(response):
    body = response.json()
    assert body["success"] is True
    return body["data"]


@pytest.mark.asyncio
async def test_get_memory_profile(client_with_db):
    response = await client_with_db.get("/api/memory/profile")

    assert response.status_code == 200
    data = _data(response)
    assert data["weak_concepts"] == []
    assert data["frequent_questions"] == []
    assert data["active_materials"] == []
    assert data["preferences"] == {}
