# 01 — Architecture Overview

## System diagram

```
                         ┌──────────────────────────────┐
   Browser  ─────────►   │  Frontend (React 19 + Vite)   │   port 5173
                         │  Tailwind 4, SSE chat UI       │
                         └───────────────┬──────────────┘
                          proxy /api ──►  │  http://localhost:8001
                         ┌───────────────▼──────────────┐
                         │  FastAPI backend               │   port 8001
                         │  backend_fastapi/app           │
                         │  ┌──────────────────────────┐  │
                         │  │ routers:                 │  │
                         │  │  chats  · files          │  │
                         │  │  agents · eda            │  │
                         │  │  market-research         │  │
                         │  │  causal                  │  │
                         │  └──────────────────────────┘  │
                         │  services:                     │
                         │   llm (Anthropic)              │
                         │   eda_pipeline (DIAL+LangGraph)│
                         │   agents framework             │
                         │                                │
                         │  /api/insight ◄── mounts ──────┼─► insight_builder/  (state graph)
                         └──────┬───────────────┬─────────┘
                    imports at  │               │  imports at runtime
                    runtime     ▼               ▼
             market_research/ (Tavily+LLM)   tools/explore_dataset.py (subprocess notebook)
                                         │
                         ┌───────────────▼──────────────┐
                         │  backend/data/causalsense.db   │  shared SQLite (WAL)
                         │  backend/data/uploads/         │  uploaded files
                         │  backend/data/eda_workspace/   │  per-session EDA artifacts
                         └───────────────────────────────┘

   Legacy Express backend (backend/, TypeScript) shares the same DB · port 3001 (optional)
```

## Components

| Component | Path | Stack | Port | Role |
|---|---|---|---|---|
| **Frontend** | `frontend/` | React 19, Vite 8, TypeScript, Tailwind 4, framer-motion | 5173 | Single-screen chat UI, structured result renderers, SVG DAG viewer |
| **FastAPI backend** | `backend_fastapi/` | FastAPI, SQLAlchemy 2.0 async, aiosqlite, Anthropic SDK | 8001 | **Primary API** — chat, files, agents, EDA, market research, causal chain |
| **Insight Builder** | `insight_builder/` | FastAPI (mounted sub-app), NetworkX, SciPy, Jinja2 | 8001 `/api/insight` | Deterministic statistical-insight state graph |
| **Market Research** | `market_research/` | OpenAI-compatible LLM (DIAL), Tavily, NetworkX | imported | Domain report + causal DAG (`AnalysisResult` → `output.json`) |
| **EDA tooling** | `tools/explore_dataset.py` | pandas, matplotlib, seaborn, nbclient | subprocess | Executes a profiling notebook, emits plots + `profile.json` |
| **Legacy backend** | `backend/` | Express 5, TypeScript, better-sqlite3 | 3001 | Original chat/files API; shares the SQLite DB |

The FastAPI backend is the active one — the frontend's Vite dev proxy forwards every `/api`
request to port **8001** (`frontend/vite.config.ts`). The Express backend is retained for
reference and writes to the same database file, but is not required to run the product.

## Two LLM providers

| Provider | Used by | Config prefix | Mock fallback |
|---|---|---|---|
| **Anthropic (Claude)** | Plain chat agent, the `/agents` framework | `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | Word-by-word mock text |
| **EPAM DIAL** (Azure-OpenAI proxy) | EDA pipeline, Insight Builder, Market Research, causal synthesis | `DIAL_API_KEY`, `DIAL_ENDPOINT`, `DIAL_MODEL` / `DIAL_*_DEPLOYMENT` | Deterministic mock output, hashed embeddings |

Both providers degrade to mock modes when their keys are absent, so the whole application is
demoable offline. **Tavily** (`TAVILY_API_KEY`) provides web search for Market Research only.

## The four features

### 1. EDA (Exploratory Data Analysis)
An autonomous notebook-exploration agent. Turn 1 runs a profiling notebook as a subprocess,
sends the executed cells + plot images to a vision LLM, and returns a narrated analysis plus
a persisted knowledge base. Follow-up questions use a LangGraph **ReAct** agent with hybrid
vector retrieval over the accumulated facts. See [04 — EDA Pipeline](04-eda-pipeline.md).

### 2. Market Research
Profiles the dataset, plans and runs web searches (Tavily), synthesizes a structured research
report, and hypothesizes a causal DAG relating dataset variables and external factors.
Output serializes to `output.json`. See [06 — Market Research](06-market-research.md).

### 3. Insight Builder
A deterministic state graph that enumerates candidate hypotheses from inferred column *roles*,
executes each as a sandboxed script, applies a three-gate statistical validation (significance,
effect size, Benjamini-Hochberg correction), and narrates the survivors. Optionally enriched
with the Market Research DAG. See [05 — Insight Builder](05-insight-builder.md).

### 4. Causal Analysis
A chain that runs EDA → Market Research → Insight Builder over one dataset and makes a final
DIAL call to fuse the three outputs into a single causal report (executive summary, causal
story, key drivers, recommendations). Long-running (30–40+ min), executed in a background
thread, polled by the frontend. Implemented in `backend_fastapi/app/routers/causal.py`.

## Request patterns

| Pattern | Endpoints | Why |
|---|---|---|
| **SSE streaming** | `POST /api/chats/{id}/messages`, `POST /api/agents/runs` | Real-time token-by-token LLM output |
| **Blocking JSON (threadpool)** | `POST /api/eda/*`, `POST /api/market-research/analyze`, `POST /api/insight/*` | Multi-second/minute pipelines; simpler than streaming |
| **Background thread + polling** | `POST /api/causal/runs` → `GET /api/causal/runs/{id}` | Very long (30–40 min) chained runs |

## How the pieces connect at runtime

- `backend_fastapi/app/main.py` inserts the **repo root** onto `sys.path` so the root-level
  `market_research` and `insight_builder` packages import cleanly, and loads `.env` from both
  the repo root and `backend_fastapi/`.
- The Insight Builder FastAPI app is **mounted** wholesale at `/api/insight` (guarded by
  try/except so a broken optional dependency can't take the backend down).
- The EDA pipeline shells out to `tools/explore_dataset.py` as a subprocess.
- All three storage locations live under `backend/data/` and are shared with the Express
  backend. See [07 — Data & Storage](07-data-and-storage.md).

## Directory map

```
Causal_sense/
├── frontend/                 React 19 + Vite chat UI            (port 5173)
├── backend_fastapi/          Primary FastAPI backend            (port 8001)
│   └── app/
│       ├── main.py           App factory, router mounts, /api/insight mount
│       ├── config.py         Pydantic settings (env-driven)
│       ├── database.py       Async engine + additive migrations
│       ├── routers/          chats, files, agents, eda_pipeline, market_research, causal
│       ├── services/
│       │   ├── llm.py        Anthropic streaming client
│       │   ├── file_processor.py  pandas schema/preview extraction
│       │   ├── agents/       BaseAgent/Tool framework + registry
│       │   └── eda_pipeline/ DIAL + LangGraph ReAct EDA pipeline
│       ├── models/           SQLAlchemy tables + Pydantic schemas
│       └── core/             SSE events, exceptions
├── insight_builder/          Deterministic insight state graph  (/api/insight)
├── market_research/          LLM + Tavily research → AnalysisResult
├── backend/                  Legacy Express backend + data/     (port 3001)
├── tools/explore_dataset.py  Notebook EDA subprocess
└── Documentation/            You are here
```
