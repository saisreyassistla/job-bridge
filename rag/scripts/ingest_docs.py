"""CLI: ingest all documents from a directory into the hybrid RAG indexes."""

import sys
import os
import inspect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from ingestion.loader import load_directory
from ingestion.cleaner import clean_documents
from ingestion.chunker import chunk_documents
from ingestion.enricher import enrich
from indexing.bm25_index import BM25Index
from indexing.vector_index import VectorIndex


def upsert_vectors(vector: VectorIndex, chunks) -> None:
    """Support the current vector index API and older local checkouts."""
    if "replace_sources" in inspect.signature(vector.upsert).parameters:
        vector.upsert(chunks, replace_sources=True)
    else:
        print("Warning: vector index does not support source replacement; using idempotent upsert.")
        vector.upsert(chunks)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_docs.py <directory>")
        sys.exit(1)

    directory = os.path.abspath(sys.argv[1])
    if not os.path.isdir(directory):
        print(f"Error: document directory does not exist: {directory}", file=sys.stderr)
        sys.exit(1)
    print(f"Loading documents from {directory}...")

    raw_docs = list(load_directory(directory))
    if not raw_docs:
        print(f"Error: no supported documents found in {directory}", file=sys.stderr)
        sys.exit(1)
    print(f"  Loaded {len(raw_docs)} raw document pages/sections")

    cleaned = clean_documents(raw_docs)
    print(f"  After cleaning: {len(cleaned)} documents")

    chunks = chunk_documents(cleaned)
    print(f"  After chunking: {len(chunks)} chunks")

    enriched = enrich(chunks)
    print(f"  After enrichment: {len(enriched)} chunks")

    print("Building BM25 index...")
    bm25 = BM25Index.from_chunks(enriched)
    bm25.save()
    print(f"  BM25 index saved to data/processed/bm25_index.pkl")

    print("Upserting to Qdrant vector store...")
    vector = VectorIndex()
    upsert_vectors(vector, enriched)
    print(f"  Done. {len(enriched)} chunks indexed in Qdrant.")


if __name__ == "__main__":
    main()
