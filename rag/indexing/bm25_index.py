"""Stage 5A — BM25 lexical index: build, persist, and search."""

from __future__ import annotations
import os
import re
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi
from ingestion.chunker import Chunk

BM25_TOP_K = int(os.getenv("BM25_TOP_K", "30"))
INDEX_PATH = "data/processed/bm25_index.pkl"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


class BM25Index:
    def __init__(self):
        self.bm25: BM25Okapi | None = None
        self.chunks: list[Chunk] = []

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        tokenized = [_tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

    def add(self, chunks: list[Chunk]) -> None:
        """Append new chunks and rebuild (for incremental ingestion)."""
        self.chunks.extend(chunks)
        self.build(self.chunks)

    def search(self, query: str, top_k: int = BM25_TOP_K) -> list[tuple[Chunk, float]]:
        if not self.bm25:
            raise RuntimeError("BM25 index not built. Call build() first.")
        tokens = _tokenize(query)
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(self.chunks[i], float(score)) for i, score in ranked[:top_k]]

    def save(self, path: str = INDEX_PATH) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"bm25": self.bm25, "chunks": self.chunks}, f)

    def load(self, path: str = INDEX_PATH) -> None:
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.bm25 = data["bm25"]
        self.chunks = data["chunks"]

    @classmethod
    def from_chunks(cls, chunks: list[Chunk]) -> "BM25Index":
        idx = cls()
        idx.build(chunks)
        return idx
