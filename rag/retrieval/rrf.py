"""Stage 7 — Reciprocal rank fusion: merge BM25 + dense retrieval results."""

from __future__ import annotations
import os
from ingestion.chunker import Chunk, chunk_id

RRF_TOP_K = int(os.getenv("RRF_TOP_K", "20"))
K_CONSTANT = 60  # standard RRF constant; higher = less top-rank bias


def reciprocal_rank_fusion(
    bm25_results: list[tuple[Chunk, float]],
    dense_results: list[tuple[Chunk, float]],
    top_k: int = RRF_TOP_K,
    k: int = K_CONSTANT,
) -> list[tuple[Chunk, float]]:
    """
    Compute RRF scores for the union of BM25 + dense results.

    RRF(d) = Σ 1 / (k + rank(d))  across all result lists.

    Chunks are deduplicated by their text fingerprint. When a chunk appears
    in both lists, its scores are summed — giving it a significant boost.
    """
    scores: dict[str, float] = {}
    chunk_map: dict[str, Chunk] = {}

    def _fingerprint(chunk: Chunk) -> str:
        return chunk.metadata.get("id") or chunk_id(chunk)

    for rank, (chunk, _) in enumerate(bm25_results, start=1):
        fp = _fingerprint(chunk)
        scores[fp] = scores.get(fp, 0.0) + 1.0 / (k + rank)
        chunk_map.setdefault(fp, chunk)

    for rank, (chunk, _) in enumerate(dense_results, start=1):
        fp = _fingerprint(chunk)
        scores[fp] = scores.get(fp, 0.0) + 1.0 / (k + rank)
        chunk_map.setdefault(fp, chunk)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(chunk_map[fp], score) for fp, score in ranked[:top_k]]
