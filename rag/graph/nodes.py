"""LangGraph nodes — all LLM calls use Claude (Anthropic)."""

from __future__ import annotations
import os
import time
import json
import re
import anthropic
from .state import RAGState
from retrieval.rrf import reciprocal_rank_fusion
from reranking.reranker import get_reranker
from generation.context import optimize_context
from generation.prompt import build_prompt
from generation.llm import generate_answer

_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_reranker  = None


def _ms():
    return time.perf_counter() * 1000


# Global latency accumulator — persists across all nodes
_LATENCY_STORE: dict = {}

def _add_latency(state, key, elapsed):
    """Accumulate latency into global store AND state."""
    _LATENCY_STORE[key] = round(elapsed, 1)
    lat = dict(state.get("latency_ms", {}))
    lat.update(_LATENCY_STORE)
    lat[key] = round(elapsed, 1)
    return lat

def _reset_latency():
    """Call at pipeline start to clear previous run."""
    _LATENCY_STORE.clear()


def _claude(prompt, max_tokens=512):
    response = _anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def query_processing_node(state, bm25_index, vector_index):
    _reset_latency()  # Clear previous run latency
    question = state["question"]
    prompt = f"""Return ONLY valid JSON, no markdown:
{{
  "rewritten": "rewrite the question to be search-friendly",
  "hyde": "write a 2-3 sentence hypothetical answer",
  "sub_queries": ["keyword query 1", "keyword query 2", "keyword query 3"]
}}
Question: {question}"""

    t0 = _ms()
    text = _claude(prompt, max_tokens=512)
    text = re.sub(r"```json|```", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {"rewritten": question, "hyde": question, "sub_queries": [question]}

    return {
        **state,
        "rewritten_query":  data.get("rewritten", question),
        "hyde_document":    data.get("hyde", question),
        "expanded_queries": data.get("sub_queries", [question]),
        "latency_ms":       _add_latency(state, "query_processing", _ms() - t0),
    }


def bm25_retrieval_node(state, bm25_index):
    queries = [state.get("rewritten_query", state["question"])] + state.get("expanded_queries", [])
    t0 = _ms()
    all_results = {}
    for q in queries:
        for chunk, score in bm25_index.search(q):
            key = f"{chunk.source}::{chunk.chunk_index}"
            if key not in all_results or score > all_results[key][1]:
                all_results[key] = (chunk, score)
    ranked = sorted(all_results.values(), key=lambda x: x[1], reverse=True)
    top_k  = ranked[:int(os.getenv("BM25_TOP_K", "30"))]
    return {**state, "bm25_results": top_k, "latency_ms": _add_latency(state, "bm25", _ms() - t0)}


def dense_retrieval_node(state, vector_index):
    hyde_query = state.get("hyde_document") or state.get("rewritten_query") or state["question"]
    t0 = _ms()
    results = vector_index.search(hyde_query)
    return {**state, "dense_results": results, "latency_ms": _add_latency(state, "dense", _ms() - t0)}


def rrf_node(state):
    t0 = _ms()
    fused = reciprocal_rank_fusion(state.get("bm25_results", []), state.get("dense_results", []))
    return {**state, "fused_results": fused, "latency_ms": _add_latency(state, "rrf", _ms() - t0)}


def reranking_node(state):
    global _reranker
    if _reranker is None:
        _reranker = get_reranker()
    t0 = _ms()
    reranked = _reranker.rerank(
        query=state.get("rewritten_query", state["question"]),
        candidates=state.get("fused_results", [])
    )
    chunks = [c for c, _ in reranked]
    scores = [float(s) for _, s in reranked]
    return {**state, "reranked_chunks": chunks, "reranked_scores": scores, "latency_ms": _add_latency(state, "reranking", _ms() - t0)}


def context_and_prompt_node(state):
    t0 = _ms()
    optimized = optimize_context(state.get("reranked_chunks", []))
    prompt, sources = build_prompt(state["question"], optimized)
    return {**state, "context_chunks": optimized, "prompt": prompt, "sources": sources, "latency_ms": _add_latency(state, "context_prompt", _ms() - t0)}


def generation_node(state):
    t0 = _ms()
    result = generate_answer(state["prompt"], state["sources"])
    return {**state, "answer": result["answer"], "citations": result["citations"], "latency_ms": _add_latency(state, "generation", _ms() - t0)}


def _chunk_to_dict(chunk, score=None, extra=None):
    d = {
        "id":          chunk.metadata.get("id", f"{chunk.source}::{chunk.chunk_index}"),
        "text":        chunk.text,
        "source":      chunk.source,
        "page":        chunk.page,
        "section":     chunk.metadata.get("section", ""),
        "chunk_index": chunk.chunk_index,
    }
    if score is not None:
        d["score"] = round(score, 6)
    if extra:
        d.update(extra)
    return d


def build_report_node(state):
    bm25_results    = state.get("bm25_results", [])
    dense_results   = state.get("dense_results", [])
    fused_results   = state.get("fused_results", [])
    reranked_chunks = state.get("reranked_chunks", [])
    reranked_scores = state.get("reranked_scores", [])
    latency         = state.get("latency_ms", {})

    def fp(chunk):
        return f"{chunk.source}::{chunk.chunk_index}"

    bm25_rank_map  = {fp(c): i + 1 for i, (c, _) in enumerate(bm25_results)}
    dense_rank_map = {fp(c): i + 1 for i, (c, _) in enumerate(dense_results)}
    fused_rank_map = {fp(c): i + 1 for i, (c, _) in enumerate(fused_results)}

    stage_keys = ["query_processing", "bm25", "dense", "rrf", "reranking", "context_prompt", "generation"]
    total = sum(latency.get(k, 0) for k in stage_keys)
    latency_report = {k: latency.get(k, 0) for k in stage_keys}
    latency_report["total"] = round(total, 1)

    report = {
        "question":         state.get("question", ""),
        "rewritten_query":  state.get("rewritten_query", ""),
        "hyde_document":    state.get("hyde_document", ""),
        "expanded_queries": state.get("expanded_queries", []),
        "answer":           state.get("answer", ""),
        "citations":        state.get("citations", []),
        "stages": {
            "bm25":     [_chunk_to_dict(c, score=round(s, 6)) for c, s in bm25_results[:30]],
            "dense":    [_chunk_to_dict(c, score=round(s, 6)) for c, s in dense_results[:30]],
            "rrf":      [_chunk_to_dict(c, score=round(s, 6), extra={"bm25_rank": bm25_rank_map.get(fp(c)), "dense_rank": dense_rank_map.get(fp(c))}) for c, s in fused_results[:20]],
            "reranked": [_chunk_to_dict(chunk, score=round(score, 6), extra={"rank": i+1, "rrf_rank": fused_rank_map.get(fp(chunk)), "rank_delta": (fused_rank_map[fp(chunk)] - (i+1)) if fp(chunk) in fused_rank_map else None}) for i, (chunk, score) in enumerate(zip(reranked_chunks, reranked_scores))],
        },
        "stats": {
            "bm25_count":         len(bm25_results),
            "dense_count":        len(dense_results),
            "rrf_count":          len(fused_results),
            "reranked_count":     len(reranked_chunks),
            "overlap_bm25_dense": len(set(fp(c) for c, _ in bm25_results) & set(fp(c) for c, _ in dense_results)),
            "reranker_type":      "cohere-rerank-v3" if os.getenv("COHERE_API_KEY") else os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        },
        "latency_ms": latency_report,
    }
    return {**state, "report": report}
