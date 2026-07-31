"""LangGraph StateGraph — sequential pipeline to avoid concurrent state conflicts."""

from __future__ import annotations
from functools import partial
from langgraph.graph import StateGraph, END
from .state import RAGState
from .nodes import (
    query_processing_node,
    bm25_retrieval_node,
    dense_retrieval_node,
    rrf_node,
    reranking_node,
    context_and_prompt_node,
    generation_node,
    build_report_node,
)


def build_pipeline(bm25_index, vector_index):
    graph = StateGraph(RAGState)

    graph.add_node("query_processing",
        partial(query_processing_node, bm25_index=bm25_index, vector_index=vector_index))
    graph.add_node("bm25_retrieval",
        partial(bm25_retrieval_node, bm25_index=bm25_index))
    graph.add_node("dense_retrieval",
        partial(dense_retrieval_node, vector_index=vector_index))
    graph.add_node("rrf",            rrf_node)
    graph.add_node("reranking",      reranking_node)
    graph.add_node("context_prompt", context_and_prompt_node)
    graph.add_node("generation",     generation_node)
    graph.add_node("build_report",   build_report_node)

    graph.set_entry_point("query_processing")
    graph.add_edge("query_processing", "bm25_retrieval")
    graph.add_edge("bm25_retrieval",   "dense_retrieval")
    graph.add_edge("dense_retrieval",  "rrf")
    graph.add_edge("rrf",              "reranking")
    graph.add_edge("reranking",        "context_prompt")
    graph.add_edge("context_prompt",   "generation")
    graph.add_edge("generation",       "build_report")
    graph.add_edge("build_report",     END)

    return graph.compile()
