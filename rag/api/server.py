"""FastAPI server exposing /ingest and /query endpoints."""

from __future__ import annotations
import os
import asyncio
import logging
import inspect
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Header, Depends
from pydantic import BaseModel
import tempfile
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
BM25_PATH = "data/processed/bm25_index.pkl"
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_QUESTION_LENGTH = int(os.getenv("MAX_QUESTION_LENGTH", "2000"))
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")
INGEST_LOCK = asyncio.Lock()


def upsert_vectors(vector_index: VectorIndex, chunks) -> None:
    if "replace_sources" in inspect.signature(vector_index.upsert).parameters:
        vector_index.upsert(chunks, replace_sources=True)
    else:
        logger.warning("Vector index lacks source replacement; using idempotent upsert")
        vector_index.upsert(chunks)


def require_service_key(service_key: Optional[str] = Header(default=None, alias="x-service-key")):
    if not SERVICE_API_KEY:
        raise HTTPException(status_code=503, detail="Service authentication is not configured")
    if service_key != SERVICE_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bm25_index, vector_index, pipeline
    app.state.ready = False
    bm25_index = BM25Index()
    if Path(BM25_PATH).exists():
        bm25_index.load(BM25_PATH)
        print(f"Loaded BM25 index from {BM25_PATH}")
    vector_index = VectorIndex()
    pipeline = build_pipeline(bm25_index, vector_index)
    app.state.ready = True
    print("RAG pipeline ready.")
    yield


app = FastAPI(title="Hybrid RAG API", lifespan=lifespan)


# ── /ingest ──────────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    chunks_added: int
    message: str


@app.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...), _: None = Depends(require_service_key)):
    """Upload a document, run the full ingestion pipeline, and index it."""
    global bm25_index, pipeline
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        total_bytes = 0
        too_large = False
        while block := file.file.read(1024 * 1024):
            total_bytes += len(block)
            if total_bytes > MAX_UPLOAD_BYTES:
                too_large = True
                break
            tmp.write(block)
        tmp_path = tmp.name
    if too_large:
        os.unlink(tmp_path)
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    try:
        async with INGEST_LOCK:
            raw_docs = load_file(tmp_path)
            for document in raw_docs:
                document.source = filename
            cleaned = clean_documents(raw_docs)
            chunks = chunk_documents(cleaned)
            enriched = enrich(chunks)

            replacement_bm25 = bm25_index.replace_sources(enriched)
            pending_bm25_path = f"{BM25_PATH}.pending"
            replacement_bm25.save(pending_bm25_path)
            try:
                upsert_vectors(vector_index, enriched)
                os.replace(pending_bm25_path, BM25_PATH)
            except Exception:
                if os.path.exists(pending_bm25_path):
                    os.unlink(pending_bm25_path)
                raise

            # Publish the new in-memory index only after persistence succeeds.
            bm25_index = replacement_bm25
            pipeline = build_pipeline(bm25_index, vector_index)

            return IngestResponse(
                chunks_added=len(enriched),
                message=f"Ingested {filename}: {len(enriched)} chunks indexed."
            )
    except Exception as e:
        logger.exception("Document ingestion failed for %s", filename)
        raise HTTPException(status_code=500, detail="Document ingestion failed") from e
    finally:
        if os.path.exists(tmp_path):
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
async def query(request: QueryRequest, _: None = Depends(require_service_key)):
    """Run the full RAG pipeline and return a grounded answer with citations."""
    question = request.question.strip()
    if not question or len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=400, detail="Question must be between 1 and 2000 characters")
    if not bm25_index or not bm25_index.chunks:
        raise HTTPException(status_code=400, detail="No documents ingested yet.")

    result = pipeline.invoke({"question": question})
    return QueryResponse(
        answer=result["answer"],
        citations=[Citation(**c) for c in result.get("citations", [])]
    )


@app.get("/health")
def health(response: Response):
    ready = bool(getattr(app.state, "ready", False))
    if not ready:
        response.status_code = 503
    return {
        "status": "ok" if ready else "starting",
        "ready": ready,
        "indexed_chunks": len(bm25_index.chunks) if bm25_index else 0
    }


@app.post("/report")
async def report(request: QueryRequest, _: None = Depends(require_service_key)):
    """Run full pipeline and return per-stage chunk report with latency."""
    question = request.question.strip()
    if not question or len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=400, detail="Question must be between 1 and 2000 characters")
    if not bm25_index or not bm25_index.chunks:
        raise HTTPException(status_code=400, detail="No documents ingested yet.")

    import time
    t_start     = time.perf_counter()
    result      = pipeline.invoke({"question": question})
    t_total     = (time.perf_counter() - t_start) * 1000
    report_data = result.get("report", {})

    # Pull per-stage latency from state (collected by _LATENCY_STORE in nodes.py)
    state_latency = result.get("latency_ms", {})
    report_data["latency_ms"] = {**state_latency, "wall_clock_total": round(t_total, 1)}

    return report_data
