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
            response = await self.llm.invoke([
                {"role": "user", "content": question}
            ])
            return AgentResponse(content=response)

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
        prompt = (
            f"请根据以下参考资料回答用户的问题。"
            f"在回答中引用来源时，请使用【来源: 文件名 P.页码】的格式。\n\n"
            f"参考资料:\n{context}\n\n"
            f"用户问题: {question}\n\n"
            f"回答:"
        )

        response = await self.llm.invoke([
            {"role": "user", "content": prompt}
        ])

        citations = self._extract_citations(response, chunks)

        return AgentResponse(
            content=response,
            citations=citations,
            retrieved_chunks=chunks,
        )

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
