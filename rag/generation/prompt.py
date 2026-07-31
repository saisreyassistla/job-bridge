"""Stage 9 — Prompt construction: assemble context chunks into a final prompt."""

from __future__ import annotations
from ingestion.chunker import Chunk

SYSTEM_PROMPT = """You are a precise, helpful assistant that answers questions
using only the provided context. Always cite your sources using [Source N]
notation. If the answer is not in the context, say so clearly — do not
make up information."""


def build_prompt(question: str, chunks: list[Chunk]) -> tuple[str, list[dict]]:
    """
    Build the final prompt for the LLM.

    Returns:
        prompt: the full prompt string
        sources: list of source dicts for citation rendering
    """
    context_blocks = []
    sources = []

    for i, chunk in enumerate(chunks, start=1):
        source_label = chunk.source or "unknown"
        page = chunk.metadata.get("page", chunk.page)
        if page:
            source_label = f"{source_label} (p.{page})"

        context_blocks.append(f"[Source {i}] {source_label}\n{chunk.text}")
        sources.append({
            "index": i,
            "source": chunk.source,
            "page": page,
            "section": chunk.metadata.get("section", ""),
            "text_preview": chunk.text[:200] + ("…" if len(chunk.text) > 200 else ""),
        })

    context = "\n\n---\n\n".join(context_blocks)

    prompt = f"""{SYSTEM_PROMPT}

CONTEXT:
{context}

QUESTION:
{question}

ANSWER (cite sources using [Source N]):"""

    return prompt, sources
