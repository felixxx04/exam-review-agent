"""Tests for overlap-based chunk normalization."""

from app.services.chunking_service import ChunkingService
from app.services.parser_service import Chunk


def test_short_chunk_is_kept_with_semantic_metadata():
    service = ChunkingService(chunk_size=10, chunk_overlap=2)
    chunk = Chunk(
        text="short",
        metadata={"source": "notes.pdf", "page": 1, "file_type": "pdf"},
        chunk_index=3,
    )

    result = service.normalize([chunk])

    assert len(result) == 1
    assert result[0].text == "short"
    assert result[0].chunk_index == 0
    assert result[0].metadata == {
        "source": "notes.pdf",
        "page": 1,
        "file_type": "pdf",
        "chunking": "semantic",
        "parent_chunk_index": 3,
    }


def test_long_chunk_is_split_with_overlap_windows():
    service = ChunkingService(chunk_size=10, chunk_overlap=2)
    chunk = Chunk(
        text="abcdefghijklmnopqrstuv",
        metadata={"source": "redis.docx", "section": "Pipeline", "file_type": "docx"},
        chunk_index=4,
    )

    result = service.normalize([chunk])

    assert [item.text for item in result] == [
        "abcdefghij",
        "ijklmnopqr",
        "qrstuv",
    ]
    assert result[0].text[-2:] == result[1].text[:2]
    assert result[1].text[-2:] == result[2].text[:2]
    assert [item.chunk_index for item in result] == [0, 1, 2]
    assert result[1].metadata == {
        "source": "redis.docx",
        "section": "Pipeline",
        "file_type": "docx",
        "chunking": "overlap_window",
        "parent_chunk_index": 4,
        "window_index": 1,
        "chunk_size": 10,
        "chunk_overlap": 2,
    }


def test_multiple_input_chunks_are_reindexed_continuously():
    service = ChunkingService(chunk_size=5, chunk_overlap=1)
    chunks = [
        Chunk(text="short", metadata={"source": "a.pdf"}, chunk_index=0),
        Chunk(text="abcdefghij", metadata={"source": "a.pdf"}, chunk_index=1),
    ]

    result = service.normalize(chunks)

    assert [item.chunk_index for item in result] == [0, 1, 2, 3]
    assert [item.metadata["parent_chunk_index"] for item in result] == [0, 1, 1, 1]
