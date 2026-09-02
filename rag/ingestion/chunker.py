"""Stage 3 — Chunking: split documents into overlapping text chunks."""

from __future__ import annotations
import os
import re
import hashlib
from dataclasses import dataclass, field
from .loader import RawDocument

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))


@dataclass
class Chunk:
    text: str
    source: str
    page: int = 0
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)


def chunk_id(chunk: Chunk) -> str:
    identity = f"{chunk.source}\0{chunk.page}\0{chunk.chunk_index}\0{chunk.text}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _recursive_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split on paragraph → sentence → word boundaries, maintaining overlap."""
    separators = ["\n\n", "\n", ". ", " ", ""]
    chunks: list[str] = []

    def _split(text: str, seps: list[str]) -> list[str]:
        if not seps or len(text) <= chunk_size:
            return [text] if text.strip() else []
        sep = seps[0]
        parts = text.split(sep) if sep else list(text)
        result, current = [], ""
        for part in parts:
            candidate = (current + sep + part).lstrip(sep) if current else part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    result.append(current)
                if len(part) > chunk_size:
                    result.extend(_split(part, seps[1:]))
                    current = ""
                else:
                    current = part
        if current:
            result.append(current)
        return result

    raw = _split(text, separators)
    # Apply overlap: carry the tail of the previous chunk into the next
    for i, chunk in enumerate(raw):
        if i == 0 or overlap == 0:
            chunks.append(chunk)
        else:
            prev = chunks[-1]
            tail = prev[-overlap:] if len(prev) > overlap else prev
            chunks.append((tail + " " + chunk).strip())

    return [c for c in chunks if c.strip()]


def chunk_document(doc: RawDocument) -> list[Chunk]:
    parts = _recursive_split(doc.content, CHUNK_SIZE, CHUNK_OVERLAP)
    return [
        Chunk(
            text=text,
            source=doc.source,
            page=doc.page,
            chunk_index=i,
        )
        for i, text in enumerate(parts)
    ]


def chunk_documents(docs: list[RawDocument]) -> list[Chunk]:
    chunks = []
    for doc in docs:
        chunks.extend(chunk_document(doc))
    return chunks
