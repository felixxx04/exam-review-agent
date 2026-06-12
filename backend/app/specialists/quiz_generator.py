"""Specialist for generating quiz questions from source material chunks.

Uses an LLM to produce multiple-choice and fill-in-the-blank questions
with source citations and plausible distractors.
"""

from __future__ import annotations

import json

from app.schemas.quiz import Question


class QuizGenerator:
    """Generates quiz questions from source material using an LLM."""

    def __init__(self, llm_service):
        self.llm_service = llm_service

    async def generate(
        self,
        chunks: list,
        difficulty: float = 0.5,
        count: int = 5,
    ) -> list[Question]:
        """Generate quiz questions from source chunks.

        Args:
            chunks: Source material chunks with .id and .text attributes.
            difficulty: Target difficulty (0.0 = easy, 1.0 = hard).
            count: Number of questions to generate.

        Returns:
            List of Question objects with source citations.
        """
        prompt = self._build_prompt(chunks, difficulty, count)
        response = await self.llm_service.invoke([
            {"role": "user", "content": prompt}
        ])
        return self._parse_response(response, chunks)

    def _build_prompt(
        self, chunks: list, difficulty: float, count: int
    ) -> str:
        chunk_texts = []
        for i, chunk in enumerate(chunks):
            chunk_texts.append(f"[{i}] {chunk.text}")

        material = "\n\n".join(chunk_texts)

        difficulty_label = "中等"
        if difficulty <= 0.3:
            difficulty_label = "简单"
        elif difficulty >= 0.7:
            difficulty_label = "困难"

        return (
            f"请根据以下参考资料生成{count}道{difficulty_label}难度的选择题。\n\n"
            f"要求:\n"
            f"1. 每道题必须有4个选项(A/B/C/D)\n"
            f"2. 错误选项(discractors)必须看起来合理(同领域、相近概念)\n"
            f"3. 每道题必须标注source_chunk_ids(引用来源chunk的id列表)\n"
            f"4. 每道题必须提供explanation解释正确答案\n"
            f"5. 返回严格的JSON数组格式\n\n"
            f"参考资料:\n{material}\n\n"
            f'返回格式示例:\n'
            f'[{{"question":"问题内容","options":["A. 选项1","B. 选项2",'
            f'"C. 选项3","D. 选项4"],"correct":"B",'
            f'"explanation":"解释文本","source_chunk_ids":["chunk-0"]}}]\n\n'
            f"请生成{count}道题，直接返回JSON数组:"
        )

    def _parse_response(
        self, response: str, chunks: list
    ) -> list[Question]:
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        questions = []
        for item in data:
            questions.append(Question(
                question=item["question"],
                options=item.get("options", []),
                correct=item["correct"],
                explanation=item.get("explanation", ""),
                source_chunk_ids=item.get("source_chunk_ids", []),
            ))
        return questions
