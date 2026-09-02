"""Stage 5A — BM25 lexical index: build, persist, and search."""

from __future__ import annotations
import os
import re
import pickle
import os
import tempfile
from pathlib import Path
from rank_bm25 import BM25Okapi
from ingestion.chunker import Chunk, chunk_id

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
        """Append unseen chunks and rebuild the lexical index."""
        known_ids = {
            chunk.metadata.get("id") or chunk_id(chunk)
            for chunk in self.chunks
        }
        new_chunks = []
        for chunk in chunks:
            identity = chunk.metadata.get("id") or chunk_id(chunk)
            if identity not in known_ids:
                known_ids.add(identity)
                new_chunks.append(chunk)
        if new_chunks:
            self.build(self.chunks + new_chunks)

    def replace_sources(self, chunks: list[Chunk]) -> "BM25Index":
        sources = {chunk.source for chunk in chunks}
        remaining = [chunk for chunk in self.chunks if chunk.source not in sources]
        replacement = BM25Index()
        replacement.build(remaining + chunks)
        return replacement

    def search(self, query: str, top_k: int = BM25_TOP_K) -> list[tuple[Chunk, float]]:
        if not self.bm25:
            raise RuntimeError("BM25 index not built. Call build() first.")
        tokens = _tokenize(query)
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(self.chunks[i], float(score)) for i, score in ranked[:top_k]]

    def save(self, path: str = INDEX_PATH) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump({"bm25": self.bm25, "chunks": self.chunks}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

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
