# CausalSense

**CausalSense** is an agentic data-analysis platform that turns a raw dataset into
validated, causal, business-ready insights. Upload a CSV/Excel/JSON file and, through
a chat interface, run:

- **EDA** — an autonomous exploratory-data-analysis agent (ReAct loop over a sandboxed
  notebook kernel, hybrid vector retrieval over generated facts).
- **Market Research** — an LLM + web-search agent that builds a domain research report
  and a causal DAG for your data.
- **Insight Builder** — a deterministic state graph that generates, statistically
  validates (significance + effect-size + multiple-comparison correction), and narrates
  business insights, optionally enriched with the market-research DAG.
- **Causal analysis** — surfaces the causal DAG and causal findings in the UI.

The result is a single chat where each answer is grounded in code that actually ran on
your data — no hallucinated numbers.

---

## Architecture at a glance

```
                         ┌──────────────────────────────┐
   Browser  ─────────►   │  Frontend (React 19 + Vite)   │   port 5173
                         │  Tailwind, SSE chat UI        │
                         └───────────────┬──────────────┘
                          proxy /api ──►  │  http://localhost:8001
                         ┌───────────────▼──────────────┐
                         │  FastAPI backend               │   port 8001
                         │  backend_fastapi/              │
                         │  ├─ chats / files              │
                         │  ├─ agents (EDA, market)       │
                         │  ├─ eda_pipeline (ReAct)       │
                         │  ├─ market_research            │
                         │  ├─ causal                     │
                         │  └─ /api/insight  ◄── mounts ──┼─► insight_builder/ (state graph)
                         └───────────────┬──────────────┘
                                         │  shared SQLite DB (WAL)
                         ┌───────────────▼──────────────┐
                         │  backend/data/causalsense.db   │
                         └───────────────────────────────┘

   Optional legacy Express backend (backend/, TypeScript) shares the same DB · port 3001
```

| Component | Path | Stack | Port | Role |
|---|---|---|---|---|
| Frontend | `frontend/` | React 19, Vite, TypeScript, Tailwind 4 | 5173 | Chat UI, results panels, DAG viewer |
| FastAPI backend | `backend_fastapi/` | FastAPI, SQLAlchemy 2.0 async, aiosqlite | 8001 | **Primary API** — chat, files, agents, EDA, causal |
| Insight Builder | `insight_builder/` | FastAPI (mounted), NetworkX, SciPy | 8001 `/api/insight` | Deterministic insight state graph |
| Market Research | `market_research/` | OpenAI-compatible LLM, Tavily search | — | Domain report + causal DAG (`output.json`) |
| EDA tooling | `tools/explore_dataset.py` | pandas, matplotlib, nbclient | — | Sandboxed notebook exploration |
| Legacy backend | `backend/` | Express 5, TypeScript, better-sqlite3 | 3001 | Original chat/files API (optional) |

The FastAPI backend is the active one — the frontend proxies `/api` to port **8001**.
The Express backend is kept for reference and shares the same SQLite database file.

---

## Prerequisites

- **Python** ≥ 3.12, < 3.14 (a `.python-version` pins 3.14 for tooling, but the backend
  targets 3.12–3.13)
- **Node.js** ≥ 20 (for the frontend; and optionally the legacy Express backend)
- An **EPAM DIAL** API key (Azure OpenAI proxy) — powers the EDA pipeline, Insight
  Builder, and Market Research.
- *(Optional)* an **Anthropic** API key — powers the plain chat agent. Without it the
  chat runs in a word-by-word **mock mode**.
- *(Optional)* a **Tavily** API key — powers web search in Market Research.

> All LLM-dependent features degrade gracefully to mock/offline modes when keys are
> absent, so you can run the app end-to-end without any credentials.

---

## Quick start

### 1. Clone & configure environment

```bash
git clone https://github.com/Atharva727-c/Causal_Sense.git
cd Causal_Sense
```

Create the **root `.env`** (read by `market_research` and `insight_builder`):

```dotenv
# EPAM DIAL (Azure OpenAI proxy)
DIAL_API_KEY=dial-...
DIAL_ENDPOINT=https://ai-proxy.lab.epam.com
DIAL_API_VERSION=2024-02-01
DIAL_MODEL=gpt-5.5-2026-04-24-reasoning

# Web search for Market Research (optional)
TAVILY_API_KEY=tvly-...
```

Create **`backend_fastapi/.env`** by copying the example:

```bash
cp backend_fastapi/.env.example backend_fastapi/.env
```

Then edit it — at minimum set `DIAL_API_KEY`. Set `ANTHROPIC_API_KEY` for live chat
(leave empty for mock mode). See [Environment variables](#environment-variables) below.

### 2. Start the FastAPI backend (port 8001)

```bash
cd backend_fastapi
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

The API is now at **http://localhost:8001** with interactive docs at
**http://localhost:8001/docs**. Health check: `GET /health`.

> The backend auto-creates the shared SQLite DB and required tables/columns on startup.

### 3. Start the frontend (port 5173)

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies all `/api` calls to the backend on 8001.

### 4. (Optional) Legacy Express backend (port 3001)

Only needed if you want the original Node backend. It shares the same SQLite DB.

```bash
cd backend
npm install
npm run dev
```

---

## Environment variables

### Root `.env` (used by `market_research` and `insight_builder`)

| Variable | Required | Description |
|---|---|---|
| `DIAL_API_KEY` | for LLM features | EPAM DIAL API key |
| `DIAL_ENDPOINT` | yes | DIAL base URL (default `https://ai-proxy.lab.epam.com`) |
| `DIAL_API_VERSION` | yes | Azure API version |
| `DIAL_MODEL` | yes | Chat deployment name |
| `TAVILY_API_KEY` | optional | Web search for Market Research |

### `backend_fastapi/.env`

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(empty → mock)* | Powers the plain chat agent |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Chat model |
| `HOST` / `PORT` | `0.0.0.0` / `8001` | Server bind |
| `DEBUG` | `false` | Enables auto-reload + debug logging |
| `DIAL_API_KEY` | *(empty → mock)* | Powers the EDA pipeline |
| `DIAL_CHAT_DEPLOYMENT` | `gpt-5.5-...-reasoning` | DIAL chat deployment for EDA |
| `DIAL_EMBEDDINGS_DEPLOYMENT` | `text-embedding-3-large` | DIAL embeddings deployment |
| `EDA_SEND_PLOT_IMAGES` | `true` | Send plot PNGs to the vision model |
| `EDA_VECTOR_TOP_K` | `5` | Chunks returned by the retriever |
| `EDA_REACT_MAX_ITERATIONS` | `8` | Max ReAct loop iterations |

See `backend_fastapi/app/config.py` for the full list.

---

## Project layout

```
Causal_sense/
├── frontend/              React 19 + Vite chat UI            (port 5173)
├── backend_fastapi/       Primary FastAPI backend            (port 8001)
│   └── app/
│       ├── routers/       HTTP + SSE endpoints
│       ├── services/      LLM client, agents, EDA pipeline
│       ├── models/        SQLAlchemy tables + Pydantic schemas
│       └── core/          events, exceptions
├── insight_builder/       Deterministic insight state graph  (/api/insight)
├── market_research/       LLM + Tavily research → output.json
├── backend/               Legacy Express backend             (port 3001)
├── tools/                 explore_dataset.py (notebook EDA)
└── Documentation/         Full architecture & feature docs
```

---

## Documentation

In-depth architecture and per-feature documentation lives in [`Documentation/`](Documentation/):

- [`Documentation/README.md`](Documentation/README.md) — documentation index
- [`Documentation/01-architecture-overview.md`](Documentation/01-architecture-overview.md)
- [`Documentation/02-frontend.md`](Documentation/02-frontend.md)
- [`Documentation/03-fastapi-backend.md`](Documentation/03-fastapi-backend.md)
- [`Documentation/04-eda-pipeline.md`](Documentation/04-eda-pipeline.md)
- [`Documentation/05-insight-builder.md`](Documentation/05-insight-builder.md)
- [`Documentation/06-market-research.md`](Documentation/06-market-research.md)
- [`Documentation/07-data-and-storage.md`](Documentation/07-data-and-storage.md)
- [`Documentation/08-api-reference.md`](Documentation/08-api-reference.md)

---

## Common tasks

| Task | Command |
|---|---|
| Run backend | `cd backend_fastapi && python run.py` |
| Run frontend | `cd frontend && npm run dev` |
| API docs | open `http://localhost:8001/docs` |
| Lint frontend | `cd frontend && npm run lint` |
| Build frontend | `cd frontend && npm run build` |
| Health check | `curl http://localhost:8001/health` |

---

## Troubleshooting

- **Chat replies word-by-word placeholder text** → `ANTHROPIC_API_KEY` is not set;
  the chat agent is in mock mode. Set it in `backend_fastapi/.env`.
- **EDA / Insight Builder returns mock output** → `DIAL_API_KEY` missing. Set it in
  both `.env` files.
- **`Insight Builder API could not be mounted`** in logs → an optional dependency for
  `insight_builder` failed to import; the rest of the backend still runs.
- **Frontend can't reach the API** → confirm the backend is on port 8001 and the Vite
  proxy in `frontend/vite.config.ts` points there.
- **Insight Builder runs are slow** → a full insight run can take tens of minutes on
  large datasets; this is expected (many sandboxed statistical scripts execute).
