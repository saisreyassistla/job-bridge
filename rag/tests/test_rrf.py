"""Tests for reciprocal rank fusion."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.chunker import Chunk
from retrieval.rrf import reciprocal_rank_fusion


def make_chunk(source: str, index: int, text: str) -> Chunk:
    return Chunk(text=text, source=source, page=1, chunk_index=index)


def test_rrf_basic_merge():
    a = make_chunk("doc1", 0, "The cat sat on the mat")
    b = make_chunk("doc1", 1, "Foxes jump over dogs")
    c = make_chunk("doc2", 0, "Python is a programming language")

    bm25 = [(a, 1.0), (b, 0.8)]
    dense = [(b, 0.95), (c, 0.7)]

    results = reciprocal_rank_fusion(bm25, dense, top_k=3)
    texts = [chunk.text for chunk, _ in results]

    # b appears in both lists → should score highest
    assert texts[0] == b.text, f"Expected b to rank first, got: {texts[0]}"
    assert len(results) == 3


def test_rrf_deduplication():
    a = make_chunk("doc1", 0, "Shared chunk")
    bm25 = [(a, 1.0)]
    dense = [(a, 0.9)]

    results = reciprocal_rank_fusion(bm25, dense, top_k=5)
    # Same chunk from both lists should appear only once
    assert len(results) == 1


def test_rrf_top_k():
    chunks = [make_chunk("doc1", i, f"chunk {i}") for i in range(10)]
    bm25 = [(c, 1.0 - i * 0.05) for i, c in enumerate(chunks[:6])]
    dense = [(c, 1.0 - i * 0.05) for i, c in enumerate(chunks[4:])]

    results = reciprocal_rank_fusion(bm25, dense, top_k=3)
    assert len(results) == 3


if __name__ == "__main__":
    test_rrf_basic_merge()
    test_rrf_deduplication()
    test_rrf_top_k()
    print("All RRF tests passed.")
