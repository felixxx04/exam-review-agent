"""Normalize parsed chunks with overlap windows for long text."""

from __future__ import annotations

from app.services.parser_service import Chunk


class ChunkingService:
    """Apply semantic-preserving overlap chunking after document parsing."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def normalize(self, chunks: list[Chunk]) -> list[Chunk]:
        normalized: list[Chunk] = []

        for chunk in chunks:
            source_start = int(chunk.metadata.get("char_start", 0))
            parent_chunk_index = int(
                chunk.metadata.get("parent_chunk_index", chunk.chunk_index)
            )
            base_metadata = {
                "page_number": None,
                "slide_number": None,
                "section_title": None,
                "section_level": None,
                **chunk.metadata,
                "parent_chunk_index": parent_chunk_index,
                "char_start": source_start,
                "char_end": source_start + len(chunk.text),
                "char_count": len(chunk.text),
            }
            if len(chunk.text) <= self.chunk_size:
                normalized.append(
                    Chunk(
                        text=chunk.text,
                        metadata={
                            **base_metadata,
                            "chunking": "semantic",
                        },
                        chunk_index=len(normalized),
                    )
                )
                continue

            normalized.extend(
                self._split_with_overlap(chunk, start_index=len(normalized))
            )

        return [
            Chunk(text=chunk.text, metadata=chunk.metadata, chunk_index=index)
            for index, chunk in enumerate(normalized)
        ]

    def _split_with_overlap(self, chunk: Chunk, start_index: int) -> list[Chunk]:
        windows: list[Chunk] = []
        step = self.chunk_size - self.chunk_overlap
        start = 0
        source_start = int(chunk.metadata.get("char_start", 0))
        parent_chunk_index = int(
            chunk.metadata.get("parent_chunk_index", chunk.chunk_index)
        )

        while start < len(chunk.text):
            end = min(start + self.chunk_size, len(chunk.text))
            text = chunk.text[start:end]
            windows.append(
                Chunk(
                    text=text,
                    metadata={
                        "page_number": None,
                        "slide_number": None,
                        "section_title": None,
                        "section_level": None,
                        **chunk.metadata,
                        "chunking": "overlap_window",
                        "parent_chunk_index": parent_chunk_index,
                        "char_start": source_start + start,
                        "char_end": source_start + end,
                        "char_count": end - start,
                        "window_index": len(windows),
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap,
                    },
                    chunk_index=start_index + len(windows),
                )
            )
            if end == len(chunk.text):
                break
            start += step

        return windows
