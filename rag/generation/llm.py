"""Stage 10 — LLM: generate grounded answer with citations using Claude."""

from __future__ import annotations
import os
import re
import anthropic

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate(prompt: str) -> str:
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def extract_cited_sources(answer: str) -> list:
    return [int(n) for n in re.findall(r"\[Source (\d+)\]", answer)]


def generate_answer(prompt: str, sources: list) -> dict:
    answer = generate(prompt)
    cited  = extract_cited_sources(answer)
    citations = [s for s in sources if s["index"] in cited]
    return {"answer": answer, "citations": citations}
