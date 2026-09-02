"""Verify an authenticated staging RAG service with real Qdrant/LLM dependencies.

Required environment:
  RAG_SERVER_URL, SERVICE_API_KEY
Optional:
  STAGING_RAG_QUESTION (default: a basic retrieval question)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)


RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8000").rstrip("/")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")
QUESTION = os.getenv(
    "STAGING_RAG_QUESTION",
    "What are the main topics covered by the ingested documents?",
)


def main() -> int:
    if not SERVICE_API_KEY:
        print("SERVICE_API_KEY is required", file=sys.stderr)
        return 2

    headers = {"x-service-key": SERVICE_API_KEY}
    try:
        health = requests.get(f"{RAG_SERVER_URL}/health", timeout=10)
        health.raise_for_status()
        health_data = health.json()
        if not health_data.get("ready"):
            print(f"RAG service is not ready: {health_data}", file=sys.stderr)
            return 1
        if health_data.get("indexed_chunks", 0) < 1:
            print("RAG service has no indexed chunks", file=sys.stderr)
            return 1

        response = requests.post(
            f"{RAG_SERVER_URL}/query",
            headers={**headers, "content-type": "application/json"},
            json={"question": QUESTION},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("answer"):
            print("RAG query returned no answer", file=sys.stderr)
            return 1
        print(
            f"Staging verification passed: {health_data['indexed_chunks']} chunks, "
            f"{len(data.get('citations', []))} citations."
        )
        return 0
    except requests.RequestException as error:
        print(f"Staging verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
