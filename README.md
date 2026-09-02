# JobBridge

JobBridge is a Slack-native career assistant that helps job seekers find jobs, understand companies, prepare for interviews, build resumes, and get grounded answers from their uploaded or indexed career documents.

The project combines:
- Slack conversation routing and workflow orchestration
- external job/company data tools
- Redis-based conversation state
- a Python hybrid RAG pipeline using BM25 + Qdrant + reranking
- grounded LLM generation with citations

This repo is intentionally designed as a real multi-service system rather than a single prompt wrapper.

---

## Product purpose

The core problem it solves is information fragmentation:
- jobs live in multiple places
- company details are scattered across sources
- policy and handbook documents are often hard to search
- users need trustworthy, plain-language help without manually browsing many tools

JobBridge creates a single place where users can:
- find jobs
- ask about a company
- prepare for interviews
- build a resume
- ask grounded questions about documents and policy content

---

## High-level architecture

```text
User (Slack DM / @mention / slash command)
        │
        ▼
  Bolt Slack app (app.js)
        │
        ▼
  Intent router + orchestration (ai/index.js)
        │
        ├── Job search ───────> server/apify-client.js ───────> Apify / Indeed data
        │
        ├── Company lookup ───> ai/tools/company-data.js ──────> MCP / external data
        │
        ├── Resume builder ───> ai/prompts/resume-builder.js
        │
        ├── Interview prep ───> ai/prompts/interview-prep.js
        │
        └── RAG query ────────> server/index.js ───────────────> Python FastAPI service
                                                            │
                                                            ▼
                                              rag/api/server.py
                                                            │
                                                            ▼
                               ┌────────────────────────────────────────────┐
                               │        Hybrid RAG orchestration           │
                               │  LangGraph pipeline:                     │
                               │  query_processing -> bm25 -> dense       │
                               │  -> RRF -> rerank -> prompt -> generate │
                               └────────────────────────────────────────────┘
                                                            │
                        ┌───────────────────────────────────────┴───────────────────────────────────────┐
                        ▼                                                                               ▼
                BM25 lexical index                                                            Qdrant vector store
                rag/indexing/bm25_index.py                                                   rag/indexing/vector_index.py
                        │                                                                               │
                        └───────────────────────────────┬───────────────────────────────────────────────┘
                                                        ▼
                                                reciprocal rank fusion
                                                rag/retrieval/rrf.py
                                                        │
                                                        ▼
                                                    reranking
                                              rag/reranking/reranker.py
                                                        │
                                                        ▼
                                            context optimization + prompts
                                      rag/generation/context.py + rag/generation/prompt.py
                                                        │
                                                        ▼
                                             Claude generation + citations
                                      rag/generation/llm.py + rag/graph/nodes.py
                                                        │
                                                        ▼
                                                     answer to user
```

---

## Project structure

```text
jobbridge/
├── app.js                              Bolt Slack entry point
├── manifest.json
├── package.json
├── .env.example
├── README.md
├── ai/
│   ├── index.js                        Intent routing and orchestration
│   ├── prompts/
│   │   ├── system-prompt.js
│   │   ├── interview-prep.js
│   │   └── resume-builder.js
│   └── tools/
│       ├── mcp-client.js              MCP client for external company/job data
│       ├── search-jobs.js
│       ├── job-details.js
│       ├── company-data.js
│       └── rag-client.js              Node-side RAG client for the Python backend
│
├── server/
│   ├── index.js                       Express server for API proxies and service routing
│   ├── apify-client.js
│   └── synthesis.js
│
├── listeners/
│   ├── assistant/
│   ├── events/
│   ├── commands/
│   └── app-home/
│
├── state/
│   └── conversation-context.js        Redis-backed or in-memory thread/user context
│
├── utils/
│   └── formatting.js
│
├── tests/
│   └── conversation-context.test.js
│
├── data/
│   └── demos/
│
├── rag/
│   ├── api/
│   │   └── server.py                  FastAPI application
│   ├── graph/
│   │   ├── pipeline.py                LangGraph state machine / orchestration
│   │   ├── nodes.py                   Stage-by-stage RAG execution nodes
│   │   └── state.py                   Shared state schema
│   ├── ingestion/
│   │   ├── loader.py                  File loading (PDF, DOCX, HTML, TXT)
│   │   ├── cleaner.py                 Normalization and deduplication
│   │   ├── chunker.py                 Recursive chunking with overlap
│   │   ├── enricher.py                Metadata enrichment
│   │   └── __init__.py
│   ├── indexing/
│   │   ├── bm25_index.py              BM25 lexical index
│   │   ├── vector_index.py            Dense vector index backed by Qdrant
│   │   └── vector_index.py.bak
│   ├── retrieval/
│   │   └── rrf.py                     Reciprocal rank fusion for hybrid retrieval
│   ├── reranking/
│   │   └── reranker.py                Cross-encoder / Cohere reranker
│   ├── generation/
│   │   ├── context.py                 Context trimming and optimization
│   │   ├── llm.py                    Generation with citations
│   │   └── prompt.py                 Final prompt construction
│   ├── scripts/
│   │   ├── ingest_docs.py             CLI document ingestion
│   │   └── verify_staging.py
│   ├── evaluation/
│   │   ├── retrieval_metrics.py
│   │   ├── latency_profiler.py
│   │   ├── evaluate_ragas.py
│   │   ├── run_all.py
│   │   └── results/
│   ├── tests/
│   │   ├── test_chunker.py
│   │   ├── test_rrf.py
│   │   └── test_metrics.py
│   ├── requirements.txt
│   ├── .venv/
│   └── qdrant_storage/
│       └── collections/
│           └── hybrid_rag/
│
├── .gitignore
├── package-lock.json
└── pnpm-lock.yaml
```

---

## Lifecycle of a request

### 1. User enters Slack
The user interacts with the assistant through Slack DM, mention, or slash command. The entry point is [app.js](app.js).

### 2. Intent classification and routing
The Node-side orchestrator in [ai/index.js](ai/index.js) classifies the input into one of several intents:
- job search
- company lookup
- resume builder
- interview prep
- document-grounded RAG query

This routing logic decides what tool or workflow should be invoked.

### 3. External tool or backend call
Depending on intent:
- job requests call the job search flow through the server layer
- company requests use MCP/data tools
- document queries call the RAG service

### 4. Express proxy layer
The Express server in [server/index.js](server/index.js) acts as the service gateway, forwarding relevant requests to the appropriate backend service or data source.

### 5. FastAPI RAG service
The Python service in [rag/api/server.py](rag/api/server.py) receives the user question and starts the retrieval pipeline.

### 6. Query processing stage
In [rag/graph/nodes.py](rag/graph/nodes.py), the `query_processing_node` function performs:
- query rewriting
- HyDE-style hypothetical answer generation for recall improvement
- keyword expansion for lexical retrieval

This step prepares a stronger retrieval request.

### 7. BM25 retrieval
The rewritten query and expanded subqueries are passed to the BM25 lexical retriever in [rag/indexing/bm25_index.py](rag/indexing/bm25_index.py).

### 8. Dense retrieval with Qdrant
The HyDE-style query is also embedded and sent to the Qdrant vector collection in [rag/indexing/vector_index.py](rag/indexing/vector_index.py).

### 9. Hybrid fusion and reranking
The retrieved results are combined using reciprocal rank fusion in [rag/retrieval/rrf.py](rag/retrieval/rrf.py), then reranked in [rag/reranking/reranker.py](rag/reranking/reranker.py) to keep only the best candidates.

### 10. Prompt assembly and final answer generation
The reranked chunks are optimized and formatted into the final prompt in:
- [rag/generation/context.py](rag/generation/context.py)
- [rag/generation/prompt.py](rag/generation/prompt.py)

The final answer is produced by the LLM in [rag/generation/llm.py](rag/generation/llm.py), with citations or source references included.

### 11. Response returned to the user
The final response moves back through the service layer and is delivered in Slack to the user.

---

## The RAG pipeline stages (1 to 10)

This project implements a hybrid retrieval architecture across 10 logical stages:

1. Data sources and file loading
2. Data cleaning and normalization
3. Chunking
4. Metadata enrichment
5A. BM25 lexical indexing
5B. Dense embedding indexing in Qdrant
6. Query processing (rewrite + HyDE + expansion)
7. Reciprocal rank fusion (BM25 + dense)
8. Reranking
9. Context optimization and prompt construction
10. Grounded answer generation with citations

The full pipeline is wired in [rag/graph/pipeline.py](rag/graph/pipeline.py).

---

## Data flow and storage architecture

### Runtime storage
- Redis: conversation state, job results, active flow, user context
  - see [state/conversation-context.js](state/conversation-context.js)
- Qdrant: dense vector knowledge base
  - see [rag/indexing/vector_index.py](rag/indexing/vector_index.py)
- BM25 local index: lexical retrieval persistence
  - see [rag/indexing/bm25_index.py](rag/indexing/bm25_index.py)

### Persistence model
- user conversation state is stored in Redis with TTLs
- knowledge chunks are stored in Qdrant as vector records with payload metadata
- lexical retrieval uses an indexed BM25 representation

---

## Why this architecture matters

This architecture is intentionally layered because a realistic assistant is more than a single LLM call:
- the assistant has to decide intent
- fetch the correct data source
- retrieve the most relevant facts
- reduce hallucination risk
- provide grounded answers with citations

That is the reason the project separates:
- routing
- service APIs
- retrieval
- reranking
- generation
- evaluation

---

## Setup and run commands

### Install dependencies

```bash
npm install
```

```bash
cd rag
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### Start Qdrant locally

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### Configure env vars

```bash
cp .env.example .env
```

Fill in:
- SLACK_* variables
- ANTHROPIC_API_KEY
- APIFY_TOKEN
- QDRANT_URL
- COHERE_API_KEY (optional)
- REDIS_URL (for production state persistence)

### Ingest documents

```bash
npm run rag:ingest ./rag/data/raw
```

### Run project

Terminal 1:
```bash
npm start
```

Terminal 2:
```bash
npm run server
```

Terminal 3:
```bash
npm run rag
```

### Run tests

```bash
npm test
```

```bash
npm run test:rag
```

---

## Summary

JobBridge is a practical, end-to-end AI application that combines:
- Slack assistant UX
- intent routing
- external tools and APIs
- hybrid document retrieval
- reranking and prompt optimization
- grounded generation with citations

It is a strong example of a production-style AI product architecture that goes beyond a simple chatbot and uses retrieval, orchestration, and evaluation as first-class parts of the system.

`ai/tools/rag-client.js`, which calls the Express proxy at
`/api/rag/query`. The proxy forwards to the Python FastAPI server, which
runs the full 10-stage pipeline (BM25 + dense retrieval → RRF → rerank →
Claude) and returns a grounded answer with citations. The Slack bot then
formats and posts the answer, with source references appended.

If the Python RAG server is not running, the bot falls back to a direct
Claude response — no hard failure.
