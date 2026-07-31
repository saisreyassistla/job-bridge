# JobBridge

A Slack agent that helps job seekers — first-time job hunters, non-native
English speakers, and people without access to career services — find real
job openings, understand companies, prepare to apply, and get grounded
answers from career documents. All in plain language, inside Slack.

Built for the **Slack Agent Builder Challenge** — "New Slack Agent / Agent
for Good" track, using **MCP integration** (Indeed MCP) as the primary
technology.

## Architecture

```
User (Slack DM / @mention / /find-job)
        │
        ▼
  Bolt app (app.js)          ← Node.js, socket mode
        │
        ▼
  ai/index.js                ← intent classifier + orchestration
   ├── job_search            → server/apify-client.js → Express → Apify (Indeed scraper)
   ├── job_details           → ai/tools/job-details.js → Indeed MCP
   ├── company_lookup        → ai/tools/company-data.js → Indeed MCP
   ├── interview_prep        → ai/prompts/interview-prep.js → Claude
   ├── resume_builder        → ai/prompts/resume-builder.js → Claude
   └── rag_query             → ai/tools/rag-client.js
                                      │
                              server/index.js  (Express proxy :3001)
                                      │
                              rag/api/server.py  (FastAPI :8000)
                                      │
                         ┌────────────┴────────────┐
                    BM25 index               Qdrant (dense)
                         └────────────┬────────────┘
                                 RRF → Rerank → Gemini
                                      │
                               answer + citations
```

## Project structure

```
jobbridge/
├── app.js                        Bolt entry point
├── manifest.json
├── package.json
├── .env.example                  ← all env vars (Node + Python)
│
├── ai/
│   ├── index.js                  Intent classifier + orchestration
│   ├── prompts/
│   │   ├── system-prompt.js
│   │   ├── interview-prep.js
│   │   └── resume-builder.js
│   └── tools/
│       ├── mcp-client.js         Indeed MCP via Anthropic API
│       ├── search-jobs.js
│       ├── job-details.js
│       ├── company-data.js
│       └── rag-client.js         ← calls RAG proxy → Python RAG server
│
├── server/
│   ├── index.js                  Express API (Apify proxy + RAG proxy)
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
│   └── conversation-context.js
│
├── utils/
│   └── formatting.js
│
├── data/demos/                   Demo data for testing
│
├── tests/
│   └── conversation-context.test.js
│
└── rag/                          ← Python Hybrid RAG pipeline
    ├── ingestion/
    │   ├── loader.py             Stage 1: PDF, DOCX, HTML, TXT
    │   ├── cleaner.py            Stage 2: normalize + deduplicate
    │   ├── chunker.py            Stage 3: recursive chunking
    │   └── enricher.py           Stage 4: metadata enrichment
    ├── indexing/
    │   ├── bm25_index.py         Stage 5A: BM25 lexical index
    │   └── vector_index.py       Stage 5B: Gemini embeddings + Qdrant
    ├── retrieval/
    │   └── rrf.py                Stage 7: reciprocal rank fusion
    ├── reranking/
    │   └── reranker.py           Stage 8: cross-encoder / Cohere
    ├── generation/
    │   ├── context.py            Stage 9: context optimization
    │   ├── prompt.py             Stage 9: prompt construction
    │   └── llm.py                Stage 10: Gemini generation + citations
    ├── graph/
    │   ├── state.py              LangGraph RAGState
    │   ├── nodes.py              One function per pipeline stage
    │   └── pipeline.py           StateGraph wiring
    ├── api/
    │   └── server.py             FastAPI: /ingest + /query + /health
    ├── scripts/
    │   └── ingest_docs.py        CLI ingestor
    ├── tests/
    │   ├── test_rrf.py
    │   └── test_chunker.py
    └── requirements.txt
```

## Setup

### 1. Clone and install Node dependencies

```bash
npm install
```

### 2. Install Python dependencies (for RAG)

```bash
cd rag
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 3. Start Qdrant (Docker)

```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 4. Configure environment

```bash
cp .env.example .env
# Fill in: SLACK_*, ANTHROPIC_API_KEY, APIFY_TOKEN,
#          GOOGLE_API_KEY, QDRANT_URL, COHERE_API_KEY (optional)
```

### 5. Ingest documents into RAG (optional but recommended)

```bash
npm run rag:ingest ./rag/data/raw
```

## Running

Three processes, three terminals:

**Terminal 1 — Slack app (Bolt)**
```bash
slack run        # or: npm start
```

**Terminal 2 — Express API server (Apify + RAG proxy)**
```bash
npm run server
```

**Terminal 3 — Python RAG server (FastAPI)**
```bash
npm run rag
```

## Available npm scripts

| Script | What it does |
|--------|-------------|
| `npm start` | Run the Bolt Slack app |
| `npm run server` | Run the Express API server |
| `npm run rag` | Run the Python FastAPI RAG server |
| `npm run rag:ingest <dir>` | Ingest documents into BM25 + Qdrant |
| `npm test` | Node tests (conversation context) |
| `npm run test:rag` | Python tests (RRF + chunker) |

## How the RAG pipeline integrates

When a user asks a knowledge question in Slack (e.g. "what does the
employee handbook say about PTO?"), `ai/index.js` routes it to
`ai/tools/rag-client.js`, which calls the Express proxy at
`/api/rag/query`. The proxy forwards to the Python FastAPI server, which
runs the full 10-stage pipeline (BM25 + dense retrieval → RRF → rerank →
Gemini) and returns a grounded answer with citations. The Slack bot then
formats and posts the answer, with source references appended.

If the Python RAG server is not running, the bot falls back to a direct
Claude response — no hard failure.
