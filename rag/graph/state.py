"""LangGraph RAGState — shared state object passed between pipeline nodes."""

from __future__ import annotations
from typing import TypedDict, Optional, List, Dict, Any
from ingestion.chunker import Chunk


class RAGState(TypedDict, total=False):
    # Input
    question: str

    # Stage 6: query processing
    rewritten_query: str
    hyde_document: str
    expanded_queries: List[str]

    # Stage 5A/5B: retrieval
    bm25_results: List[Any]
    dense_results: List[Any]

    # Stage 7: RRF
    fused_results: List[Any]

    # Stage 8: reranking
    reranked_chunks: List[Any]
    reranked_scores: List[float]

    # Stage 9: context + prompt
    context_chunks: List[Any]
    prompt: str
    sources: List[dict]

    # Stage 10: generation
    answer: str
    citations: List[dict]

    # Latency tracking
    latency_ms: Dict[str, float]

    # Report
    report: Optional[Dict]

    # Error passthrough
    error: Optional[str]
