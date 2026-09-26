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
        "page_number": None,
        "slide_number": None,
        "section_title": None,
        "section_level": None,
        "chunking": "semantic",
        "parent_chunk_index": 3,
        "char_start": 0,
        "char_end": 5,
        "char_count": 5,
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
        "page_number": None,
        "slide_number": None,
        "section_title": None,
        "section_level": None,
        "chunking": "overlap_window",
        "parent_chunk_index": 4,
        "char_start": 8,
        "char_end": 18,
        "char_count": 10,
        "window_index": 1,
        "chunk_size": 10,
        "chunk_overlap": 2,
    }


def test_long_chunk_tracks_inclusive_start_and_exclusive_end_ranges():
    service = ChunkingService(chunk_size=10, chunk_overlap=2)
    source = Chunk(
        text="abcdefghijklmnopqrstuv",
        metadata={
            "source": "notes.pdf",
            "page_number": 2,
            "slide_number": None,
            "section_title": "第二节",
            "section_level": 2,
            "parent_chunk_index": 7,
            "char_start": 100,
            "char_end": 122,
            "char_count": 22,
        },
        chunk_index=7,
    )

    result = service.normalize([source])

    assert [item.metadata["parent_chunk_index"] for item in result] == [7, 7, 7]
    assert [
        (item.metadata["char_start"], item.metadata["char_end"], item.metadata["char_count"])
        for item in result
    ] == [(100, 110, 10), (108, 118, 10), (116, 122, 6)]
    for item in result:
        assert item.text == source.text[
            item.metadata["char_start"] - source.metadata["char_start"] :
            item.metadata["char_end"] - source.metadata["char_start"]
        ]
        assert item.metadata["char_end"] - item.metadata["char_start"] == len(item.text)


def test_short_chunk_tracks_parent_range_without_inventing_overlap():
    service = ChunkingService(chunk_size=10, chunk_overlap=2)
    source = Chunk(
        text="短文本",
        metadata={"char_start": 4, "char_end": 7, "char_count": 3},
        chunk_index=3,
    )

    result = service.normalize([source])

    assert result[0].metadata["parent_chunk_index"] == 3
    assert result[0].metadata["char_start"] == 4
    assert result[0].metadata["char_end"] == 7
    assert result[0].metadata["char_count"] == 3


def test_multiple_input_chunks_are_reindexed_continuously():
    service = ChunkingService(chunk_size=5, chunk_overlap=1)
    chunks = [
        Chunk(text="short", metadata={"source": "a.pdf"}, chunk_index=0),
        Chunk(text="abcdefghij", metadata={"source": "a.pdf"}, chunk_index=1),
    ]

    result = service.normalize(chunks)

    assert [item.chunk_index for item in result] == [0, 1, 2, 3]
    assert [item.metadata["parent_chunk_index"] for item in result] == [0, 1, 1, 1]
