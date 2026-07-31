"""Stage 9 — Context optimization: order, deduplicate, and trim top chunks."""

from __future__ import annotations
from ingestion.chunker import Chunk

MAX_CONTEXT_CHARS = 8000


def _lost_in_middle_order(chunks: list[Chunk]) -> list[Chunk]:
    """
    Place the most relevant chunks at the start and end of the context
    window. LLMs tend to forget information in the middle of long prompts
    (the "lost-in-the-middle" phenomenon).
    Interleave: best → worst → second-best → second-worst → ...
    """
    if len(chunks) <= 2:
        return chunks
    result = []
    lo, hi = 0, len(chunks) - 1
    toggle = True
    while lo <= hi:
        if toggle:
            result.append(chunks[lo]); lo += 1
        else:
            result.append(chunks[hi]); hi -= 1
        toggle = not toggle
    return result


def optimize_context(chunks: list[Chunk]) -> list[Chunk]:
    """
    1. Deduplicate by exact text.
    2. Reorder using lost-in-the-middle strategy.
    3. Trim total characters to MAX_CONTEXT_CHARS.
    """
    seen, unique = set(), []
    for chunk in chunks:
        if chunk.text not in seen:
            seen.add(chunk.text)
            unique.append(chunk)

    ordered = _lost_in_middle_order(unique)

    trimmed, total = [], 0
    for chunk in ordered:
        if total + len(chunk.text) > MAX_CONTEXT_CHARS:
            break
        trimmed.append(chunk)
        total += len(chunk.text)

    return trimmed
