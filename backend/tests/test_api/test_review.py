from __future__ import annotations

import pytest

from app.core.store import get_shared_store


class TestReviewEndpoints:

    @pytest.fixture(autouse=True)
    def clear_shared_store(self):
        get_shared_store()._records.clear()

    @pytest.mark.asyncio
    async def test_get_weak_points(self, client):
        response = await client.get("/api/review/weak-points")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "weak_concepts" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_mistakes_returns_review_records(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-review",
            "question_text": "矩阵 A 的特征值定义是什么？",
            "question_type": "multiple_choice",
            "concept": "特征值",
            "topic": "线性代数",
            "wrong_answer": "A",
            "correct_answer": "B",
            "explanation": "特征值满足 Ax = λx。",
            "source_material": "linear.pdf",
            "source_chunk_ids": ["chunk-1"],
            "status": "unreviewed",
            "attempt_count": 2,
            "last_wrong_at": "2026-07-06T10:00:00+00:00",
            "correction_note": "",
            "mastered_at": None,
        })

        response = await client.get("/api/review/mistakes")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["mistakes"][0]["id"] == "q-review"
        assert data["mistakes"][0]["question_text"] == "矩阵 A 的特征值定义是什么？"
        assert data["mistakes"][0]["status"] == "unreviewed"
        assert data["summary"]["pending_count"] == 1

    @pytest.mark.asyncio
    async def test_list_mistakes_filters_by_status_and_search(self, client):
        store = get_shared_store()
        await store.add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-alpha",
            "question_text": "导数定义",
            "question_type": "multiple_choice",
            "concept": "导数",
            "topic": "微积分",
            "wrong_answer": "A",
            "correct_answer": "B",
            "status": "corrected",
        })
        await store.add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-beta",
            "question_text": "特征值定义",
            "question_type": "multiple_choice",
            "concept": "特征值",
            "topic": "线性代数",
            "wrong_answer": "C",
            "correct_answer": "D",
            "status": "unreviewed",
        })

        response = await client.get(
            "/api/review/mistakes",
            params={"status": "unreviewed", "search": "特征"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["mistakes"][0]["id"] == "q-beta"

    @pytest.mark.asyncio
    async def test_get_mistake_detail(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-detail",
            "question_text": "什么是极限？",
            "question_type": "multiple_choice",
            "concept": "极限",
            "topic": "微积分",
            "wrong_answer": "A",
            "correct_answer": "C",
            "status": "unreviewed",
        })

        response = await client.get("/api/review/mistakes/q-detail")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == "q-detail"
        assert data["concept"] == "极限"

    @pytest.mark.asyncio
    async def test_update_mistake_correction_and_mastery(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-update",
            "question_text": "什么是行列式？",
            "question_type": "multiple_choice",
            "concept": "行列式",
            "topic": "线性代数",
            "wrong_answer": "A",
            "correct_answer": "D",
            "status": "unreviewed",
            "review_history": [],
        })

        response = await client.patch(
            "/api/review/mistakes/q-update",
            json={
                "correction_note": "我把定义和计算公式混淆了。",
                "status": "corrected",
                "mastered": True,
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["correction_note"] == "我把定义和计算公式混淆了。"
        assert data["status"] == "mastered"
        assert data["mastered_at"] is not None
