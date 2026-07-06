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

    @pytest.mark.asyncio
    async def test_daily_session_returns_priority_review_items(self, client):
        store = get_shared_store()
        await store.add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-low",
            "question_text": "已掌握错题",
            "concept": "导数",
            "topic": "微积分",
            "wrong_answer": "A",
            "correct_answer": "B",
            "status": "mastered",
            "attempt_count": 5,
        })
        await store.add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-priority",
            "question_text": "未订正错题",
            "concept": "特征值",
            "topic": "线性代数",
            "wrong_answer": "C",
            "correct_answer": "D",
            "status": "unreviewed",
            "attempt_count": 3,
        })

        response = await client.post("/api/review/daily-session", json={"limit": 5})

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["mistakes"][0]["id"] == "q-priority"
        assert "今日复习" in data["message"]

    @pytest.mark.asyncio
    async def test_similar_quiz_uses_mistake_context(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-similar",
            "question_text": "特征值定义",
            "question_type": "multiple_choice",
            "concept": "特征值",
            "topic": "线性代数",
            "wrong_answer": "A",
            "correct_answer": "B",
            "status": "unreviewed",
        })

        response = await client.post("/api/review/mistakes/q-similar/similar-quiz")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["topic"] == "特征值"
        assert data["total"] == 1
        assert "特征值" in data["questions"][0]["question"]

    @pytest.mark.asyncio
    async def test_explain_mistake_returns_and_stores_explanation(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-explain",
            "question_text": "行列式定义",
            "question_type": "multiple_choice",
            "concept": "行列式",
            "topic": "线性代数",
            "wrong_answer": "A",
            "correct_answer": "D",
            "status": "unreviewed",
            "explanation": "",
        })

        response = await client.post("/api/review/mistakes/q-explain/explanation")

        assert response.status_code == 200
        data = response.json()["data"]
        assert "正确答案" in data["explanation"]

        detail = await client.get("/api/review/mistakes/q-explain")
        assert detail.json()["data"]["explanation"] == data["explanation"]

    @pytest.mark.asyncio
    async def test_update_mistake_sets_review_schedule_and_history(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-schedule",
            "question_text": "函数连续性",
            "question_type": "multiple_choice",
            "concept": "连续",
            "topic": "微积分",
            "wrong_answer": "A",
            "correct_answer": "B",
            "status": "unreviewed",
            "review_history": [],
        })

        response = await client.patch(
            "/api/review/mistakes/q-schedule",
            json={"status": "needs_requiz"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "needs_requiz"
        assert data["next_review_at"] is not None
        assert data["review_history"][-1]["event"] == "needs_requiz"

    @pytest.mark.asyncio
    async def test_export_mistakes_as_markdown_and_csv(self, client):
        await get_shared_store().add({
            "type": "mistake_records",
            "user_id": "default",
            "question_id": "q-export",
            "question_text": "特征值定义",
            "question_type": "multiple_choice",
            "concept": "特征值",
            "topic": "线性代数",
            "wrong_answer": "A",
            "correct_answer": "B",
            "status": "corrected",
            "correction_note": "回到定义判断。",
        })

        markdown = await client.get("/api/review/export", params={"format": "markdown"})
        csv = await client.get("/api/review/export", params={"format": "csv"})

        assert markdown.status_code == 200
        assert "# 错题导出" in markdown.json()["data"]["content"]
        assert "特征值定义" in markdown.json()["data"]["content"]
        assert csv.status_code == 200
        assert "question,concept,topic" in csv.json()["data"]["content"]
        assert "特征值定义" in csv.json()["data"]["content"]
