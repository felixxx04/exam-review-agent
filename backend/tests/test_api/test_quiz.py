from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.schemas.quiz import Question, QuizResponse


class TestQuizGenerate:
    @pytest.mark.asyncio
    async def test_generate_quiz_validates_input(self, client_with_db, monkeypatch):
        build_agent = Mock()
        monkeypatch.setattr("app.api.quiz._build_quiz_agent", build_agent)

        response = await client_with_db.post(
            "/api/quiz/generate",
            json={"difficulty": 0.5, "count": 3},
        )

        assert response.status_code == 422
        build_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_quiz_default_count(self, client_with_db, monkeypatch):
        agent = SimpleNamespace(
            generate_quiz=AsyncMock(
                return_value=QuizResponse(
                    questions=[
                        Question(
                            question="矩阵的秩表示什么？",
                            options=["线性无关行数", "行列式"],
                            correct="线性无关行数",
                            explanation="秩是矩阵中线性无关行或列的最大数目。",
                            source_chunk_ids=["chunk-1"],
                        )
                    ],
                    topic="线性代数",
                )
            )
        )
        build_agent = Mock(return_value=agent)
        monkeypatch.setattr("app.api.quiz._build_quiz_agent", build_agent)

        response = await client_with_db.post(
            "/api/quiz/generate",
            json={"topic": "线性代数"},
        )

        assert response.status_code == 200
        assert response.json()["data"] == {
            "questions": [
                {
                    "id": "q-1",
                    "question": "矩阵的秩表示什么？",
                    "question_type": "multiple_choice",
                    "options": ["线性无关行数", "行列式"],
                    "correct": "线性无关行数",
                    "explanation": "秩是矩阵中线性无关行或列的最大数目。",
                    "difficulty": 0.5,
                    "topic": "线性代数",
                    "source_chunk_ids": ["chunk-1"],
                }
            ],
            "topic": "线性代数",
            "total": 1,
        }
        build_agent.assert_called_once_with()
        agent.generate_quiz.assert_awaited_once()
        kwargs = agent.generate_quiz.await_args.kwargs
        assert kwargs["user_id"] == 1
        assert isinstance(kwargs["user_id"], int)
        assert kwargs["topic"] == "线性代数"
        assert kwargs["difficulty"] == 0.5
        assert kwargs["count"] == 5
        assert kwargs["material_scope"] is None
        assert kwargs["course_id"] is not None

    @pytest.mark.asyncio
    async def test_generate_quiz_passes_material_scope_to_agent(
        self, client_with_db, monkeypatch
    ):
        agent = SimpleNamespace(
            generate_quiz=AsyncMock(
                return_value=QuizResponse(questions=[], topic="线性代数")
            )
        )
        monkeypatch.setattr("app.api.quiz._build_quiz_agent", Mock(return_value=agent))

        response = await client_with_db.post(
            "/api/quiz/generate",
            json={
                "topic": "线性代数",
                "material_scope": ["linear.pdf"],
            },
        )

        assert response.status_code == 200
        kwargs = agent.generate_quiz.await_args.kwargs
        assert kwargs["user_id"] == 1
        assert isinstance(kwargs["user_id"], int)
        assert kwargs["material_scope"] == ["linear.pdf"]


class TestQuizSubmit:
    @pytest.mark.asyncio
    async def test_submit_correct_answer(self, client_with_db):
        response = await client_with_db.post(
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
    async def test_submit_wrong_answer(self, client_with_db):
        response = await client_with_db.post(
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
    async def test_submit_fill_blank_case_insensitive(self, client_with_db):
        response = await client_with_db.post(
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

    @pytest.mark.asyncio
    async def test_submit_wrong_answer_records_question_context(
        self,
        client_with_db,
        mistake_repository,
    ):
        response = await client_with_db.post(
            "/api/quiz/submit",
            json={
                "question_id": "q-context",
                "correct_answer": "B",
                "student_answer": "A",
                "question_type": "multiple_choice",
                "concept": "特征值",
                "topic": "线性代数",
                "question_text": "矩阵 A 的特征值定义是什么？",
                "explanation": "特征值满足 Ax = λx。",
                "source_chunk_ids": ["chunk-1"],
                "source_material": "linear.pdf",
            },
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mistake_recorded"] is True

        mistakes = await mistake_repository.list_for_user("1")
        assert len(mistakes) == 1
        assert mistakes[0]["question_text"] == "矩阵 A 的特征值定义是什么？"
        assert mistakes[0]["explanation"] == "特征值满足 Ax = λx。"
        assert mistakes[0]["source_chunk_ids"] == ["chunk-1"]
