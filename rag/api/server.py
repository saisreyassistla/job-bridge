"""FastAPI server exposing /ingest and /query endpoints."""

from __future__ import annotations
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
import shutil, tempfile
from typing import Optional

from ingestion.loader import load_file
from ingestion.cleaner import clean_documents
from ingestion.chunker import chunk_documents
from ingestion.enricher import enrich
from indexing.bm25_index import BM25Index
from indexing.vector_index import VectorIndex
from graph.pipeline import build_pipeline

# ── Shared state ────────────────────────────────────────────────────────────
bm25_index: BM25Index | None = None
vector_index: VectorIndex | None = None
pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bm25_index, vector_index, pipeline
    bm25_index = BM25Index()
    bm25_path = "data/processed/bm25_index.pkl"
    if Path(bm25_path).exists():
        bm25_index.load(bm25_path)
        print(f"Loaded BM25 index from {bm25_path}")
    vector_index = VectorIndex()
    pipeline = build_pipeline(bm25_index, vector_index)
    print("RAG pipeline ready.")
    yield


app = FastAPI(title="Hybrid RAG API", lifespan=lifespan)


# ── /ingest ──────────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    chunks_added: int
    message: str


@app.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...)):
    """Upload a document, run the full ingestion pipeline, and index it."""
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        raw_docs = load_file(tmp_path)
        cleaned = clean_documents(raw_docs)
        chunks = chunk_documents(cleaned)
        enriched = enrich(chunks)

        bm25_index.add(enriched)
        bm25_index.save()
        vector_index.upsert(enriched)

        # Rebuild pipeline with updated indexes
        global pipeline
        pipeline = build_pipeline(bm25_index, vector_index)

        return IngestResponse(
            chunks_added=len(enriched),
            message=f"Ingested {file.filename}: {len(enriched)} chunks indexed."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


# ── /query ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str


class Citation(BaseModel):
    index: int
    source: str
    page: Optional[int] = None
    section: Optional[str] = None
    text_preview: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Run the full RAG pipeline and return a grounded answer with citations."""
    if not bm25_index or not bm25_index.chunks:
        raise HTTPException(status_code=400, detail="No documents ingested yet.")

    result = pipeline.invoke({"question": request.question})
    return QueryResponse(
        answer=result["answer"],
        citations=[Citation(**c) for c in result.get("citations", [])]
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "indexed_chunks": len(bm25_index.chunks) if bm25_index else 0
    }


@app.post("/report")
async def report(request: QueryRequest):
    """Run full pipeline and return per-stage chunk report with latency."""
    if not bm25_index or not bm25_index.chunks:
        raise HTTPException(status_code=400, detail="No documents ingested yet.")

    import time
    t_start     = time.perf_counter()
    result      = pipeline.invoke({"question": request.question})
    t_total     = (time.perf_counter() - t_start) * 1000
    report_data = result.get("report", {})

    # Pull per-stage latency from state (collected by _LATENCY_STORE in nodes.py)
    state_latency = result.get("latency_ms", {})
    report_data["latency_ms"] = {**state_latency, "wall_clock_total": round(t_total, 1)}

    return report_data
