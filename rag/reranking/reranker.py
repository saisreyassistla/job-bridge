"""Stage 8 — Reranking: cross-encoder (local) or Cohere rerank."""

from __future__ import annotations
import os
from ingestion.chunker import Chunk

RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))
CROSS_ENCODER_MODEL = os.getenv(
    "CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)


class CrossEncoderReranker:
    """Local reranker using sentence-transformers CrossEncoder."""

    def __init__(self):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(CROSS_ENCODER_MODEL)

    def rerank(
        self, query: str, candidates: list[tuple[Chunk, float]], top_k: int = RERANK_TOP_K
    ) -> list[tuple[Chunk, float]]:
        pairs = [(query, chunk.text) for chunk, _ in candidates]
        scores = self.model.predict(pairs)
        ranked = sorted(
            zip(candidates, scores), key=lambda x: x[1], reverse=True
        )
        return [(chunk, float(score)) for (chunk, _), score in ranked[:top_k]]


class CohereReranker:
    """Cohere rerank API (faster, no local GPU needed)."""

    def __init__(self):
        import cohere
        self.client = cohere.Client(os.getenv("COHERE_API_KEY"))

    def rerank(
        self, query: str, candidates: list[tuple[Chunk, float]], top_k: int = RERANK_TOP_K
    ) -> list[tuple[Chunk, float]]:
        docs = [chunk.text for chunk, _ in candidates]
        response = self.client.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=docs,
            top_n=top_k,
        )
        results = []
        for hit in response.results:
            chunk, _ = candidates[hit.index]
            results.append((chunk, hit.relevance_score))
        return results


def get_reranker():
    """Return Cohere reranker if API key is set, else local cross-encoder."""
    if os.getenv("COHERE_API_KEY"):
        return CohereReranker()
    return CrossEncoderReranker()
