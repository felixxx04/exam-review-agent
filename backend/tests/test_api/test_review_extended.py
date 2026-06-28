from __future__ import annotations

import pytest


class TestStudyPlan:

    @pytest.mark.asyncio
    async def test_study_plan_endpoint(self, client):
        response = await client.post(
            "/api/review/study-plan",
            json={"exam_date": "2026-07-01", "days_before_exam": 7},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "plan" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_study_plan_default_days(self, client):
        response = await client.post(
            "/api/review/study-plan",
            json={"exam_date": "2026-07-01"},
        )
        assert response.status_code == 200
