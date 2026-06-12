"""Mistake summarizer for weak-point analysis.

Uses an LLM to produce concise, actionable summaries of a student's
mistake history. Supports two modes:

- **full**: Send all mistakes in one prompt for a comprehensive summary.
- **incremental**: Only send the most recent 5 mistakes, useful when the
  mistake history is large.
"""

from __future__ import annotations

FULL_THRESHOLD = 5
INCREMENTAL_WINDOW = 5


class MistakeSummarizer:
    """Summarizes mistake records into actionable weak-point descriptions."""

    def __init__(self, llm_service):
        self.llm = llm_service

    async def summarize(
        self,
        mistakes: list[dict],
        mode: str = "auto",
    ) -> str:
        """Summarize mistakes into a Chinese-language weak-point analysis.

        Args:
            mistakes: List of mistake dicts with concept, topic, wrong_answer,
                      correct_answer keys.
            mode: "full", "incremental", or "auto" (default).
                  "auto" picks based on count: fewer than 5 -> full.
        """
        if not mistakes:
            return "暂无错题记录"

        if mode == "auto":
            mode = "full" if len(mistakes) < FULL_THRESHOLD else "incremental"

        if mode == "incremental":
            mistakes = mistakes[-INCREMENTAL_WINDOW:]

        prompt = self._build_prompt(mistakes, mode)
        response = await self.llm.invoke([
            {"role": "user", "content": prompt}
        ])
        return response

    def _build_prompt(self, mistakes: list[dict], mode: str) -> str:
        lines = ["以下是一位学生的错题记录：\n"]
        for m in mistakes:
            lines.append(
                f"- 概念: {m['concept']}, 主题: {m.get('topic', '')}, "
                f"错误答案: {m['wrong_answer']}, 正确答案: {m['correct_answer']}"
            )

        if mode == "full":
            lines.append(
                "\n请基于以上所有错题，全面分析学生的薄弱知识点，"
                "并给出有针对性的复习建议。用中文回答。"
            )
        else:
            lines.append(
                "\n请基于以上最近5道错题，分析学生近期新增的薄弱点，"
                "并给出改进建议。用中文回答。"
            )

        return "\n".join(lines)
