"""RAG (Retrieval-Augmented Generation) agent for question answering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.retrieval_service import SearchResult


@dataclass
class AgentResponse:
    """Response from the RAG agent with citations and retrieved chunks."""

    content: str
    citations: list[dict] = field(default_factory=list)
    retrieved_chunks: list[SearchResult] = field(default_factory=list)


class RAGAgent:
    """Answers user questions using retrieval-augmented generation.

    Retrieves relevant chunks from the user's material library,
    constructs a prompt with grounded context, and returns an
    annotated answer with source citations.
    """

    def __init__(self, llm_service, retrieval_service):
        self.llm = llm_service
        self.retrieval = retrieval_service

    async def answer(
        self,
        question: str,
        user_id: str,
        material_scope: list[str] | None = None,
        memory_context: dict | None = None,
    ) -> AgentResponse:
        """Answer a question using RAG with the user's materials."""
        metadata_filter = None
        if material_scope:
            metadata_filter = {"source": {"$in": material_scope}}

        chunks = await self.retrieval.search(
            user_id=user_id,
            query=question,
            top_k=5,
            metadata_filter=metadata_filter,
        )

        if not chunks:
            response = await self.llm.invoke(
                [{"role": "user", "content": self._build_prompt(question, [], memory_context)}]
            )
            return AgentResponse(content=response)

        response = await self.llm.invoke(
            [{"role": "user", "content": self._build_prompt(question, chunks, memory_context)}]
        )

        citations = self._extract_citations(response, chunks)

        return AgentResponse(
            content=response,
            citations=citations,
            retrieved_chunks=chunks,
        )

    def _build_prompt(
        self,
        question: str,
        chunks: list[SearchResult],
        memory_context: dict | None,
    ) -> str:
        prompt_parts = [
            "请优先依据参考资料回答用户问题。",
            "如果问题明显在追问上文，请结合会话记忆保持指代一致。",
            "在回答中引用来源时，请使用【来源: 文件名 P.页码】的格式。",
        ]

        memory_block = self._format_memory_context(memory_context)
        if memory_block:
            prompt_parts.append(f"会话记忆:\n{memory_block}")

        if chunks:
            context_parts = []
            for i, chunk in enumerate(chunks):
                source = chunk.metadata.get("source", "unknown")
                page = chunk.metadata.get("page", "")
                ref = f"【来源: {source}"
                if page:
                    ref += f" P.{page}"
                ref += "】"
                context_parts.append(f"[{i + 1}] {chunk.text} {ref}")
            context = "\n\n".join(context_parts)
            prompt_parts.append(f"参考资料:\n{context}")
        else:
            prompt_parts.append("参考资料:\n当前没有检索到直接相关的资料片段，请仅在会话记忆足够时延续回答，否则明确说明资料不足。")

        prompt_parts.append(f"用户问题: {question}")
        prompt_parts.append("回答:")
        return "\n\n".join(prompt_parts)

    @staticmethod
    def _format_memory_context(memory_context: dict | None) -> str:
        if not memory_context:
            return ""

        sections: list[str] = []
        learning_profile = memory_context.get("learning_profile") or {}
        summary = memory_context.get("summary")
        recent_messages = memory_context.get("recent_messages") or []

        profile_lines = []
        if learning_profile.get("current_subject"):
            profile_lines.append(f"当前科目: {learning_profile['current_subject']}")
        if learning_profile.get("review_goal"):
            profile_lines.append(f"复习目标: {learning_profile['review_goal']}")
        weak_concepts = learning_profile.get("weak_concepts") or []
        if weak_concepts:
            profile_lines.append(f"薄弱点: {', '.join(weak_concepts)}")
        if profile_lines:
            sections.append("学习画像:\n" + "\n".join(profile_lines))

        if summary:
            sections.append(f"会话摘要:\n{summary}")

        transcript = []
        for item in recent_messages[-4:]:
            role = item.get("role")
            content = item.get("content")
            if role and content:
                transcript.append(f"{role}: {content}")
        if transcript:
            sections.append("最近对话:\n" + "\n".join(transcript))

        return "\n\n".join(sections)

    def _extract_citations(
        self, response: str, chunks: list[SearchResult]
    ) -> list[dict]:
        """Extract source references from the LLM response.

        Matches patterns like 【来源: file.pdf P.10】,【来源: file.pdf】,
        or bare "file.pdf P.10" references.
        """
        citations: list[dict] = []
        seen: set[str] = set()

        # Match 【来源: ...】 format
        bracketed = r"【来源:\s*(.+?)(?:\s*P\.(\d+))?】"
        # Match bare "source.ext P.XX" format
        bare = r"(?:\b)([\w.-]+\.\w{2,5})\s*(?:P\.(\d+))"

        for match in re.finditer(bracketed, response):
            source = match.group(1).strip()
            page = match.group(2)
            self._add_citation(citations, seen, chunks, source, page)

        for match in re.finditer(bare, response):
            source = match.group(1).strip()
            page = match.group(2)
            self._add_citation(citations, seen, chunks, source, page)

        return citations

    @staticmethod
    def _add_citation(
        citations: list[dict],
        seen: set[str],
        chunks: list[SearchResult],
        source: str,
        page: str | None,
    ) -> None:
        key = f"{source}:{page}" if page else source
        if key in seen:
            return
        seen.add(key)

        citation: dict = {"source": source}
        if page:
            citation["page"] = int(page)

        for chunk in chunks:
            chunk_source = chunk.metadata.get("source", "")
            chunk_page = chunk.metadata.get("page")
            if chunk_source == source and (
                page is None
                or str(chunk_page) == page
            ):
                citation["text"] = chunk.text
                break

        citations.append(citation)
