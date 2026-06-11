"""Paper analyzer specialist for extracting structure from academic documents.

Identifies sections, chapters, definitions, theorems, and other structural
patterns common in Chinese educational materials.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class PaperSection:
    """A logical section identified in a document."""

    title: str
    level: int
    start_position: int
    content_snippet: str


class PaperAnalyzer:
    """Analyzes the structure of educational/academic documents.

    Detects chapter and section markers common in Chinese-language
    textbooks and lecture notes (e.g., '第一章', '第一节', '定理', '定义').
    """

    # Chinese section patterns
    CHAPTER_PATTERNS = [
        re.compile(r"第[一二三四五六七八九十百千万\d]+章"),
        re.compile(r"第[一二三四五六七八九十百千万\d]+节"),
        re.compile(r"Chapter\s+\d+", re.IGNORECASE),
        re.compile(r"Section\s+\d+", re.IGNORECASE),
    ]

    KEYWORD_PATTERNS = [
        re.compile(r"^(定义\d*[：:])"),
        re.compile(r"^(定理\d*[：:])"),
        re.compile(r"^(公理\d*[：:])"),
        re.compile(r"^(推论\d*[：:])"),
        re.compile(r"^(引理\d*[：:])"),
        re.compile(r"^(例题\d*[：:])"),
        re.compile(r"^(习题\d*[：:])"),
        re.compile(r"^(证明[：:])"),
    ]

    @classmethod
    def detect_structure(cls, text: str) -> list[PaperSection]:
        """Detect the structural elements of a document text.

        Args:
            text: The full text content to analyze.

        Returns:
            A list of PaperSection objects describing the document structure.
        """
        sections: list[PaperSection] = []
        lines = text.split("\n")
        position = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                position += len(line) + 1
                continue

            # Try chapter patterns first
            level = cls._match_chapter_level(stripped)
            if level:
                sections.append(
                    PaperSection(
                        title=stripped,
                        level=level,
                        start_position=position,
                        content_snippet=stripped,
                    )
                )
                position += len(line) + 1
                continue

            # Try keyword patterns
            keyword_match = cls._match_keyword(stripped)
            if keyword_match:
                sections.append(
                    PaperSection(
                        title=stripped,
                        level=3,
                        start_position=position,
                        content_snippet=stripped,
                    )
                )

            position += len(line) + 1

        return sections

    @classmethod
    def extract_concepts(cls, text: str) -> list[str]:
        """Extract key concept names from the document text.

        Looks for patterns like '定义：XXX' or '定理：XXX' and extracts
        the concept name following the marker.
        """
        concepts: list[str] = []
        for pattern in cls.KEYWORD_PATTERNS:
            for match in pattern.finditer(text):
                rest = text[match.end():].strip()
                # Take up to the first punctuation or newline
                concept_end = re.search(r"[，。；,\.;\n]", rest)
                if concept_end:
                    concept_name = rest[:concept_end.start()].strip()
                else:
                    concept_name = rest[:50].strip()
                if concept_name and len(concept_name) < 50:
                    concepts.append(concept_name)
        return concepts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _match_chapter_level(cls, text: str) -> Optional[int]:
        """Return the heading level (1=chapter, 2=section) if the text
        matches a known chapter/section marker."""
        for pattern in cls.CHAPTER_PATTERNS:
            if pattern.match(text):
                if "章" in pattern.pattern or "Chapter" in pattern.pattern:
                    return 1
                return 2
        return None

    @classmethod
    def _match_keyword(cls, text: str) -> bool:
        """Return True if the text matches a known keyword marker."""
        for pattern in cls.KEYWORD_PATTERNS:
            if pattern.match(text):
                return True
        return False
