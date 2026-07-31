"""Stage 2 — Data cleaning: normalize whitespace, deduplicate, filter noise."""

from __future__ import annotations
import re
import hashlib
from .loader import RawDocument


def normalize(text: str) -> str:
    """Collapse excessive whitespace, strip control characters."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def is_noise(text: str, min_chars: int = 50) -> bool:
    """Return True if the text is too short or mostly non-alphanumeric."""
    clean = re.sub(r"\s", "", text)
    if len(clean) < min_chars:
        return True
    alpha_ratio = sum(c.isalpha() for c in clean) / max(len(clean), 1)
    return alpha_ratio < 0.4


def fingerprint(text: str) -> str:
    return hashlib.md5(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()


def clean_documents(docs: list[RawDocument]) -> list[RawDocument]:
    """Normalize, filter noise, and deduplicate a list of RawDocuments."""
    seen: set[str] = set()
    cleaned: list[RawDocument] = []

    for doc in docs:
        text = normalize(doc.content)
        if is_noise(text):
            continue
        fp = fingerprint(text)
        if fp in seen:
            continue
        seen.add(fp)
        doc.content = text
        cleaned.append(doc)

    return cleaned
