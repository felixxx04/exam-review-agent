from __future__ import annotations

import pytest


class TestQuizGenerate:

    @pytest.mark.skip(reason="Requires real LLM/embedding services - run with API keys")
    @pytest.mark.asyncio
    async def test_generate_quiz_validates_input(self, client):
        response = await client.post(
            "/api/quiz/generate",
            json={"topic": "量子力学", "difficulty": 0.5, "count": 3},
        )
        assert response.status_code in (200, 404)

    @pytest.mark.skip(reason="Requires real LLM/embedding services - run with API keys")
    @pytest.mark.asyncio
    async def test_generate_quiz_default_count(self, client):
        response = await client.post(
            "/api/quiz/generate",
            json={"topic": "线性代数"},
        )
        assert response.status_code in (200, 404)


class TestQuizSubmit:

    @pytest.mark.asyncio
    async def test_submit_correct_answer(self, client):
        response = await client.post(
            "/api/quiz/submit",
            params={
                "question_id": "q1",
                "correct_answer": "B",
                "student_answer": "B",
                "question_type": "multiple_choice",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_correct"] is True

    @pytest.mark.asyncio
    async def test_submit_wrong_answer(self, client):
        response = await client.post(
            "/api/quiz/submit",
            params={
                "question_id": "q2",
                "correct_answer": "B",
                "student_answer": "A",
                "question_type": "multiple_choice",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_correct"] is False

    @pytest.mark.asyncio
    async def test_submit_fill_blank_case_insensitive(self, client):
        response = await client.post(
            "/api/quiz/submit",
            params={
                "question_id": "q3",
                "correct_answer": "hello",
                "student_answer": "HELLO",
                "question_type": "fill_blank",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_correct"] is True
