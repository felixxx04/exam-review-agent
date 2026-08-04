from __future__ import annotations

import pytest
from unittest.mock import AsyncMock


class TestStudyPlan:
    @pytest.mark.asyncio
    async def test_study_plan_endpoint(self, client_with_db):
        response = await client_with_db.post(
            "/api/review/study-plan",
            json={"exam_date": "2026-07-01", "days_before_exam": 7},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "plan" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_study_plan_default_days(self, client_with_db):
        response = await client_with_db.post(
            "/api/review/study-plan",
            json={"exam_date": "2026-07-01"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_study_plan_resolves_and_propagates_course(
        self, client_with_db, monkeypatch
    ):
        course = (
            await client_with_db.post(
                "/api/courses",
                json={"name": "操作系统", "daily_available_minutes": 50},
            )
        ).json()["data"]
        tracker = AsyncMock()
        tracker.generate_study_plan = AsyncMock(
            return_value={"plan": [], "message": "暂无薄弱知识点"}
        )
        monkeypatch.setattr("app.api.review._build_tracker", lambda repository: tracker)

        response = await client_with_db.post(
            "/api/review/study-plan",
            params={"course_id": course["id"]},
            json={"exam_date": "2026-07-01", "days_before_exam": 7},
        )

        assert response.status_code == 200
        tracker.generate_study_plan.assert_awaited_once_with(
            user_id="1",
            exam_date="2026-07-01",
            days_before_exam=7,
            course_id=course["id"],
        )
