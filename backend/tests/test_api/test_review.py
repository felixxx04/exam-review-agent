from __future__ import annotations

import pytest


class TestReviewEndpoints:

    @pytest.mark.asyncio
    async def test_get_weak_points(self, client):
        response = await client.get("/api/review/weak-points")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "weak_concepts" in data
        assert "total" in data
