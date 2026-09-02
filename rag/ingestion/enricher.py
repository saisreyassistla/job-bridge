"""Stage 4 — Metadata enrichment: tag each chunk with source, section, timestamps."""

from __future__ import annotations
import re
from datetime import datetime, timezone
from .chunker import Chunk, chunk_id


def _detect_section(text: str) -> str:
    """Heuristic: use the first heading-like line as the section title."""
    for line in text.splitlines():
        line = line.strip()
        if line and (
            re.match(r"^#{1,4}\s+", line)       # markdown heading
            or re.match(r"^[A-Z][A-Z\s]{4,}$", line)   # ALL-CAPS heading
            or re.match(r"^\d+\.\s+[A-Z]", line)  # numbered heading
        ):
            return re.sub(r"^#+\s*", "", line).strip()
    return ""


def _word_count(text: str) -> int:
    return len(text.split())


def enrich(chunks: list[Chunk]) -> list[Chunk]:
    """Adds id, section, word_count, ingested_at, and char_count to each chunk."""
    now = datetime.now(timezone.utc).isoformat()
    for chunk in chunks:
        chunk.metadata.update({
            "id": chunk_id(chunk),
            "section": _detect_section(chunk.text),
            "word_count": _word_count(chunk.text),
            "char_count": len(chunk.text),
            "ingested_at": now,
            "source": chunk.source,
            "page": chunk.page,
            "chunk_index": chunk.chunk_index,
        })
    return chunks
