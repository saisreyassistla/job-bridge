# Hybrid RAG System

A production-grade Retrieval-Augmented Generation pipeline implementing all
10 stages of the hybrid retrieval architecture: dual indexing (BM25 + dense
embeddings), reciprocal rank fusion, cross-encoder reranking, and grounded
LLM generation with citations.

Built with **LangGraph** for agent orchestration, local MiniLM embeddings,
Claude generation, and **Qdrant** as the vector store.

## Pipeline

```
Document Ingestion
  1. Data sources        (PDF, HTML, DOCX, plain text)
  2. Data cleaning       (normalize, deduplicate, filter)
  3. Chunking            (recursive / semantic)
  4. Metadata enrichment (source, page, section, timestamp)
        ┌──────────────────────────┐
  5A. BM25 index            5B. Dense embeddings
  Lexical index             Vector database (Qdrant)
        └──────────────────────────┘
User question
  6. Query processing    (rewrite + HyDE + expansion)
        ┌──────────────────────────┐
  BM25 search            Dense retrieval
  Top 30 docs            Top 30 docs
        └──────────────────────────┘
  7. Reciprocal rank fusion  → top 20 candidates
  8. Reranking               → top 5 chunks
     (cross-encoder / Cohere rerank)
  9. Context optimization + prompt construction
  10. LLM (Claude)           → answer + citations
```

## Tech stack

| Layer            | Tools |
|------------------|-------|
| Orchestration    | LangGraph |
| Embeddings       | `all-MiniLM-L6-v2` |
| LLM              | Claude Haiku |
| Vector store     | Qdrant |
| Lexical search   | rank_bm25 (BM25Okapi) |
| Reranking        | cross-encoder/ms-marco-MiniLM-L-6-v2 (local) or Cohere |
| Document parsing | unstructured, pdfminer, python-docx |
| API layer        | FastAPI |

## Project structure

```
hybrid-rag/
├── ingestion/
│   ├── loader.py          # Load PDF, HTML, DOCX, TXT
│   ├── cleaner.py         # Normalize, deduplicate, filter
│   ├── chunker.py         # Recursive + semantic chunking
│   └── enricher.py        # Metadata enrichment
├── indexing/
│   ├── bm25_index.py      # BM25Okapi index: build + search
│   └── vector_index.py    # Qdrant: embed + upsert + search
├── retrieval/
│   ├── bm25_retriever.py  # BM25 search wrapper
│   ├── dense_retriever.py # Dense retrieval wrapper
│   └── rrf.py             # Reciprocal rank fusion
├── reranking/
│   └── reranker.py        # Cross-encoder + Cohere rerank
├── generation/
│   ├── context.py         # Context optimization
│   ├── prompt.py          # Prompt construction
│   └── llm.py             # Claude generation + citations
├── graph/
│   ├── state.py           # LangGraph RAGState definition
│   ├── nodes.py           # One function per pipeline node
│   └── pipeline.py        # StateGraph wiring
├── api/
│   └── server.py          # FastAPI: /ingest + /query
├── tests/
│   ├── test_chunker.py
│   ├── test_rrf.py
│   └── test_metrics.py
├── scripts/
│   └── ingest_docs.py     # CLI: python scripts/ingest_docs.py <path>
├── .env.example
├── requirements.txt
└── pyproject.toml
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_API_KEY, COHERE_API_KEY
```

Start Qdrant locally (Docker):
```bash
docker run -p 6333:6333 qdrant/qdrant
```

## Running

**Ingest documents:**
```bash
python scripts/ingest_docs.py ./data/raw
```

**Start the API server:**
```bash
uvicorn api.server:app --reload
```

For staging verification from the repository root:
```bash
npm run rag:verify-staging
```

**Query directly:**
```python
from graph.pipeline import build_pipeline

pipeline = build_pipeline()
result = pipeline.invoke({"question": "What is the refund policy?"})
print(result["answer"])
print(result["citations"])
```
