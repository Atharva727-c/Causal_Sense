# 03 — FastAPI Backend

**Path:** `backend_fastapi/` · **Stack:** FastAPI, SQLAlchemy 2.0 async, aiosqlite, Anthropic
async SDK, aiofiles, pandas · **Port:** 8001

This is the primary API. It is fully async, with blocking sub-pipelines (DIAL/OpenAI, Chroma,
notebook subprocess) offloaded to threadpools or background threads. It shares its SQLite
database with the legacy Express backend and adds its own table + columns via idempotent
migrations.

## Startup

- **`run.py`** — entry point. Loads settings and calls
  `uvicorn.run("app.main:app", host, port, reload=debug, workers=1)`. A **single worker** is
  required because causal-run state is held in memory.
- **`app/main.py`** — the app factory:
  - Inserts the **repo root** onto `sys.path` (so `market_research` and `insight_builder`
    import) and loads `.env` from both the repo root and `backend_fastapi/`.
  - `lifespan` context manager ensures the shared data dir exists and calls `create_tables()`.
  - Middleware: CORS (origins from settings) + GZip.
  - Registers six routers under `/api`: `chats`, `files`, `agents`, `eda_pipeline`,
    `market_research`, `causal`.
  - **Mounts the entire Insight Builder sub-app** at `/api/insight`, wrapped in try/except.
  - `GET /health` (liveness) and `GET /ready` (reports whether the LLM key is configured,
    the model name, and mock mode).
  - Interactive docs at `/docs` (Swagger) and `/redoc`.

## Configuration (`app/config.py`)

A pydantic-settings `Settings` object, `.env`-driven, cached via `get_settings()`. Groups:

- **App/server:** `port=8001`, `debug`, `environment`.
- **CORS:** localhost 5173/3000.
- **Anthropic:** `anthropic_api_key`, `claude_model="claude-sonnet-4-6"`,
  `claude_max_tokens=4096`, `claude_timeout=120`.
- **EPAM DIAL** (powers the EDA pipeline): `dial_api_key`,
  `dial_endpoint="https://ai-proxy.lab.epam.com"`,
  `dial_chat_deployment="gpt-5.5-2026-04-24-reasoning"`,
  `dial_embeddings_deployment="text-embedding-3-large"`, `dial_is_reasoning_model=True`,
  `dial_max_completion_tokens=8192`.
- **EDA tuning:** `eda_vector_top_k=5`, `eda_chunk_size=1200`, `eda_chunk_overlap=150`,
  `eda_sample_rows=100000`, `eda_react_max_iterations=8`, `eda_send_plot_images=True`,
  `eda_explorer_script` → `tools/explore_dataset.py`, `eda_workspace_dir`.
- **Storage:** `upload_dir` (shared `backend/data/uploads`), `max_upload_bytes=100MB`,
  allowed extensions csv/tsv/xlsx/xls/json/parquet/sql/txt.
- **Database:** `sqlite+aiosqlite:///…/backend/data/causalsense.db` — the shared DB.

## Database (`app/database.py`, `app/models/`)

- Async engine + `async_sessionmaker`. `create_tables()` runs
  `Base.metadata.create_all` (creating `agent_runs`), then applies **idempotent additive
  `ALTER TABLE` migrations** adding FastAPI-only columns to the shared `messages` and `files`
  tables, and sets WAL / foreign_keys / synchronous pragmas. `get_db()` is the request-scoped
  session dependency.
- ORM tables (`app/models/db.py`): `chats`, `messages`, `files`, `agent_runs`. See
  [07 — Data & Storage](07-data-and-storage.md) for the full schema.
- Pydantic schemas (`app/models/schemas.py`) validate requests; ms→datetime validators convert
  stored Unix-ms ints to ISO-8601. Responses are frequently hand-serialized to camelCase dicts
  in the routers (to match the frontend and the Express backend).

## Core (`app/core/`)

- **`events.py`** — SSE wire-format helpers, byte-compatible with the frontend. `_encode`
  emits `data: {json}\n\n`. Emitters: `sse_start` (userMsgId), `sse_delta` (text chunk),
  `sse_done` (assistantMsgId + title), `sse_error` (code + message), plus `sse_agent_step`,
  `sse_tool_use`, `sse_tool_result`.
- **`exceptions.py`** — `AppError` base (status_code + code) and subclasses: `NotFoundError`
  (404), `ConflictError` (409), `FileTooLargeError` (413), `UnsupportedFileTypeError` (415),
  `AgentError` (500), `LLMError` (502). Handlers return `{success, code, message}`.

## Routers (all under `/api`)

See [08 — API Reference](08-api-reference.md) for full endpoint tables. Summary:

| Router | Prefix | Key endpoints | Mode |
|---|---|---|---|
| `chats.py` | `/chats` | CRUD + **`POST /{id}/messages`** (SSE chat stream) | SSE |
| `files.py` | `/files` | list / upload / get / download / delete | JSON |
| `agents.py` | `/agents` | list agents, **`POST /runs`** (SSE agent stream), poll run | SSE + poll |
| `eda_pipeline.py` | `/eda` | `POST /analyze`, `POST /ask`, `GET /{session}/facts` | JSON (threadpool) |
| `market_research.py` | `/market-research` | `POST /analyze` | JSON (threadpool) |
| `causal.py` | `/causal` | `POST /runs`, `GET /runs/{id}` | background thread + poll |

### The chat stream (`POST /chats/{id}/messages`)
The core chat endpoint. Persists the user message, auto-titles on the first message, inserts a
placeholder assistant message, commits, then returns a `StreamingResponse`
(`text/event-stream`). The generator emits `sse_start`, streams Claude text deltas via
`llm.stream()` (using the last 40 history rows as context, prepending `file_context` if
provided), captures token counts, persists the final assistant content in a fresh session, and
emits `sse_done`. With no API key it falls back to word-by-word **mock** text.

### The causal chain (`POST /causal/runs`)
The full four-stage chain over one dataset. Runs in a daemon **thread** (30–40+ min), tracked
in an in-memory `_RUNS` dict guarded by a lock (lost on restart — fine for the demo). Stages:
`eda` → `market_research` → `insight_builder` → `synthesis`. The synthesis stage makes one DIAL
`chat_json` call fusing EDA facts + Market Research summary/DAG + validated insights into a JSON
causal report. `GET /causal/runs/{id}` returns stage statuses/timings and, when complete, the
full result.

## Services (`app/services/`)

### `llm.py` — Anthropic client
Wraps `anthropic.AsyncAnthropic` (None if no key → `available=False` drives mock paths).
Mode-keyed system prompts (`BASE`, `EDA`, `MARKET_RESEARCH`). `stream()` is an async generator
yielding `("text"|"input_tokens"|"output_tokens"|"tool_use", data)` tuples by pattern-matching
Anthropic stream events; SDK exceptions map to `LLMError`. `complete()` is the non-streaming
variant. `get_llm()` is lru-cached.

### `file_processor.py`
`detect_file_type` maps extensions to csv/excel/json/parquet/sql/text/other. `process_file`
(async) reads with pandas (csv/excel capped at 50k rows), extracts schema (name/dtype/null_pct/
unique_count, ≤100 cols), numeric `describe()` stats, and a 5-row preview — degrading gracefully
if pandas is missing or the parse fails. `build_file_context` renders a compact markdown block
(schema + sample rows) for injection into LLM prompts.

### `agents/` — the Anthropic agent framework
A simpler, separate track from the DIAL-powered `eda_pipeline`. The `/agents` route uses this;
`/eda` uses the pipeline.

- **`base.py`** — the ABCs:
  - `Tool` — `name`/`description`/`input_schema` + async `execute(inputs, ctx)`;
    `to_anthropic_format()` produces the Anthropic tool spec.
  - `AgentContext` — dataclass carrying `query`, `chat_history`, `files`, `config`, `metadata`.
  - `BaseAgent` — class attrs `name`/`description`/`mode`/`tools`. `stream(ctx)` is a
    single-turn Claude call with a **tool-use loop** (emits `sse_agent_step`/`sse_delta`,
    executes tools on `tool_use` events and appends results back into messages). `run_once(ctx)`
    collects deltas into one string for agent-to-agent chaining.
- **`eda.py`** — `EDAAgent` (mode "eda") injects file schema/preview context before delegating
  to base streaming.
- **`market_research.py`** — `MarketResearchAgent` (mode "market_research"), a thin pass-through.
- **`registry.py`** — `_REGISTRY = {"eda": EDAAgent, "market_research": MarketResearchAgent}`.
  This is the single extension point: subclass `BaseAgent`, register it, and it is immediately
  available at `POST /api/agents/runs`.

### `eda_pipeline/` — the full DIAL + LangGraph EDA pipeline
Documented in detail in [04 — EDA Pipeline](04-eda-pipeline.md). Public API:
`run_initial_eda` and `answer_followup`.

## Cross-cutting notes

- **Two LLM providers** (Anthropic and DIAL), each with mock modes — fully demoable offline.
- **Streaming vs polling** — SSE on chat/agents; threadpool JSON on eda/market-research;
  background thread + polling on causal.
- **Shared state** — SQLite shared with Express (additive migrations only); causal runs are
  in-memory and single-worker.
- **External integrations imported from the repo root** — `market_research`, `insight_builder`
  (mounted + orchestrator), and `tools/explore_dataset.py` (subprocess) — none live inside
  `backend_fastapi/app`.
