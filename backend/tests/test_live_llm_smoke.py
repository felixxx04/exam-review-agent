from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cli import live_llm_smoke
from app.schemas.quiz import Question


def test_read_key_from_file(tmp_path):
    key_file = tmp_path / "deepseek.key"
    key_file.write_text("  test-key  \n", encoding="utf-8")

    assert live_llm_smoke._read_key(key_file) == "test-key"


def test_read_key_prefers_environment_key(monkeypatch, tmp_path):
    key_file = tmp_path / "deepseek.key"
    key_file.write_text("file-key", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    assert live_llm_smoke._read_key(key_file) == "env-key"


def test_read_key_uses_environment_key_without_file(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    assert live_llm_smoke._read_key(None) == "env-key"


def test_read_key_returns_empty_for_missing_file(tmp_path):
    assert live_llm_smoke._read_key(tmp_path / "missing.key") == ""


@pytest.mark.asyncio
async def test_run_smoke_validates_question_contract(monkeypatch):
    class FakeGenerator:
        def __init__(self, _provider):
            pass

        async def generate(self, **_kwargs):
            return [
                Question(
                    question="q",
                    options=["A", "B", "C", "D"],
                    correct="A",
                    explanation="because",
                    source_chunk_ids=["chunk-0"],
                )
            ]

    monkeypatch.setattr(live_llm_smoke, "DeepSeekProvider", lambda **_: object())
    monkeypatch.setattr(live_llm_smoke, "QuizGenerator", FakeGenerator)

    assert await live_llm_smoke.run_smoke("test-key") == (1, 4)


@pytest.mark.asyncio
async def test_run_smoke_rejects_missing_citation(monkeypatch):
    class FakeGenerator:
        def __init__(self, _provider):
            pass

        async def generate(self, **_kwargs):
            return [
                SimpleNamespace(
                    options=["A", "B", "C", "D"],
                    correct="A",
                    explanation="because",
                    source_chunk_ids=[],
                )
            ]

    monkeypatch.setattr(live_llm_smoke, "DeepSeekProvider", lambda **_: object())
    monkeypatch.setattr(live_llm_smoke, "QuizGenerator", FakeGenerator)

    with pytest.raises(RuntimeError, match="source citation"):
        await live_llm_smoke.run_smoke("test-key")
