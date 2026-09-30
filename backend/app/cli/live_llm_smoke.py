"""Run an explicit, opt-in DeepSeek quiz-generation smoke test."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from app.services.llm_providers.deepseek import DeepSeekProvider
from app.specialists.quiz_generator import QuizGenerator


def _default_key_file() -> Path:
    if os.name == "nt":
        app_data = os.environ.get("LOCALAPPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Local"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "exam-review-agent" / "deepseek_api_key.txt"


DEFAULT_KEY_FILE = _default_key_file()


def _read_key(path: Path | None) -> str:
    environment_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if environment_key:
        return environment_key
    if path is not None and path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


async def run_smoke(key: str) -> tuple[int, int]:
    provider = DeepSeekProvider(api_key=key, base_url="https://api.deepseek.com")
    questions = await QuizGenerator(provider).generate(
        chunks=[
            SimpleNamespace(
                id="chunk-0",
                text="牛顿第二定律指出，物体的加速度与合外力成正比，与质量成反比，方向与合外力相同。",
            )
        ],
        difficulty=0.3,
        count=1,
    )
    if len(questions) != 1:
        raise RuntimeError(f"expected one question, got {len(questions)}")
    question = questions[0]
    if len(question.options) != 4:
        raise RuntimeError(f"expected four options, got {len(question.options)}")
    if not question.correct or not question.explanation:
        raise RuntimeError("question lacks correct answer or explanation")
    if question.source_chunk_ids != ["chunk-0"]:
        raise RuntimeError("source citation was not preserved")
    return len(questions), len(question.options)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=DEFAULT_KEY_FILE,
        help="read the DeepSeek API key from a local file",
    )
    args = parser.parse_args()
    key = _read_key(args.key_file if args.key_file else None)
    if not key:
        parser.error("a non-empty DeepSeek API key is required")
    questions, options = asyncio.run(run_smoke(key))
    print(f"LIVE_LLM_SMOKE=PASS QUESTIONS={questions} OPTIONS={options}")


if __name__ == "__main__":
    main()
