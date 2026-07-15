"""CausalSense FastAPI backend.

Architecture summary
====================
- Async throughout (SQLAlchemy 2.0 + aiosqlite, Anthropic async SDK, aiofiles)
- Shared SQLite DB with the Express backend — FastAPI adds ``agent_runs`` table
  and a handful of nullable columns to existing tables via idempotent ALTER TABLE.
- SSE wire format is 100% compatible with the React frontend.
- Agent framework exposes ``BaseAgent`` / ``Tool`` ABCs; teammates extend these
  to wire in their agentic pipelines.

Ports: Express 3001 · FastAPI 8001
"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.core.exceptions import AppError, app_error_handler, generic_error_handler
from app.database import create_tables
from app.routers import agents, chats, eda_pipeline, files

_s = get_settings()
logging.basicConfig(
    level=logging.DEBUG if _s.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the shared data directory exists (SQLite file lives there).
    shared_data = Path(_s.database_url.split("///")[-1]).parent
    shared_data.mkdir(parents=True, exist_ok=True)

    logger.info("Starting %s v%s on port %d", _s.app_name, _s.app_version, _s.port)
    await create_tables()
    yield
    logger.info("Shutting down %s", _s.app_name)


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=_s.app_name,
    version=_s.app_version,
    description="""
## CausalSense API — FastAPI Backend

State-of-the-art async analytics API designed for agentic AI integration.

### Features
- **SSE streaming** — real-time LLM responses, wire-compatible with the React frontend
- **Agent framework** — extensible `BaseAgent` + `Tool` ABCs; register new agents in `registry.py`
- **File processing** — CSV / Excel / JSON / Parquet with schema, preview, and stats extraction
- **Agent run tracking** — persistent history, status polling, structured step logs
- **Shared DB** — reads and writes the same SQLite file as the Express backend

### SSE Event Types (chat & agent streams)
| Event field | When emitted |
|---|---|
| `delta` | LLM text chunk |
| `event: start` | Stream opened (includes `userMsgId`) |
| `event: done` | Stream complete (includes `assistantMsgId`, `title`) |
| `event: agent_step` | Agent reasoning / planning step |
| `event: tool_use` | Agent calling a tool |
| `event: tool_result` | Tool response |
| `event: error` | Unrecoverable error |

### Adding a new agent (for teammates)
1. Create `app/services/agents/your_agent.py` — subclass `BaseAgent`.
2. Optionally add `Tool` subclasses for external calls (web, DB, code-exec, etc.).
3. Register in `app/services/agents/registry.py`.
4. The new agent is immediately available at `POST /api/agents/runs`.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_s.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Exception handlers ─────────────────────────────────────────────────────────
app.add_exception_handler(AppError, app_error_handler)          # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_error_handler)     # type: ignore[arg-type]

# ── Routers ────────────────────────────────────────────────────────────────────
_API = "/api"
app.include_router(chats.router,  prefix=_API)
app.include_router(files.router,  prefix=_API)
app.include_router(agents.router, prefix=_API)
app.include_router(eda_pipeline.router, prefix=_API)

# ── Health / readiness ─────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Liveness probe")
async def health():
    return {"status": "ok", "version": _s.app_version, "port": _s.port}


@app.get("/ready", tags=["System"], summary="Readiness probe")
async def readiness():
    from app.services.llm import get_llm
    llm = get_llm()
    return {
        "status": "ready",
        "llmConfigured": llm.available,
        "model": _s.claude_model,
        "mockMode": not llm.available,
    }
