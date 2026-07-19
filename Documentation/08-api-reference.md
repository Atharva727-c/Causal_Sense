# 08 — API Reference

All endpoints are served by the FastAPI backend on **port 8001** under the `/api` prefix (except
`/health`, `/ready`, and the docs). The frontend reaches them through the Vite proxy. Interactive
docs: **http://localhost:8001/docs** (Swagger) and **/redoc**.

Response conventions: many routers hand-serialize to **camelCase** JSON to match the frontend and
the Express backend. Errors return `{success: false, code, message}` with the appropriate HTTP
status.

## System

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness — `{status, version, port}` |
| GET | `/ready` | Readiness — `{status, llmConfigured, model, mockMode}` |

## Chats — `/api/chats`

| Method | Path | Purpose | Mode |
|---|---|---|---|
| GET | `/api/chats` | List chats (newest first) with each last message → `{chats, total}` | JSON |
| POST | `/api/chats` | Create a chat (body `ChatCreate`) → 201 | JSON |
| GET | `/api/chats/{chat_id}` | Chat + eager-loaded messages | JSON |
| PATCH | `/api/chats/{chat_id}` | Rename (body `ChatRename`) | JSON |
| DELETE | `/api/chats/{chat_id}` | Delete (cascades messages/runs) → 204 | JSON |
| POST | `/api/chats/{chat_id}/messages` | **Send a message → SSE stream** of the assistant reply | **SSE** |

**`POST /chats/{id}/messages`** body: `{content, fileContext?, mode?}` where `mode` is
`eda | market_research | null`. Persists the user message, auto-titles on the first message,
streams Claude deltas (last 40 messages as context), and persists the final assistant message.
Falls back to word-by-word mock text with no API key.

### SSE event types (chat & agent streams)
| Event | When |
|---|---|
| `event: start` | Stream opened (includes `userMsgId`) |
| `delta` | LLM text chunk |
| `event: done` | Stream complete (includes `assistantMsgId`, `title`) |
| `event: agent_step` | Agent reasoning/planning step |
| `event: tool_use` | Agent calling a tool |
| `event: tool_result` | Tool response |
| `event: error` | Unrecoverable error (`code`, `message`) |

## Files — `/api/files`

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/files` | List files → `{files, total, totalSize}` |
| POST | `/api/files/upload` | Multipart upload → 201 (also `POST /api/files`) |
| GET | `/api/files/{file_id}` | Metadata + parsed schema/preview |
| GET | `/api/files/{file_id}/download` | Download the raw file |
| DELETE | `/api/files/{file_id}` | Delete from disk + DB → 204 |

Upload validates extension and size (100 MB max), stores under `uploads/{uuid}{ext}`, and extracts
row/column counts, schema, and a 5-row preview.

## Agents — `/api/agents`

| Method | Path | Purpose | Mode |
|---|---|---|---|
| GET | `/api/agents` | List registered agents | JSON |
| POST | `/api/agents/runs` | **Run an agent → SSE stream**; creates an `agent_runs` row | **SSE** |
| GET | `/api/agents/runs/{run_id}` | Poll run status (`AgentRunOut`) | JSON |

Body `AgentRunCreate`: `{agent_type, chat_id?, query, file_ids[], config{}}`. `agent_type` must be
in the registry (`eda`, `market_research`) or 404. Loads file context, streams the agent's tool-use
loop, and records the outcome on the run row.

## EDA Pipeline — `/api/eda`

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/eda/analyze` | Turn-1 EDA — body `{session_id, file_id, target?, time_col?}` |
| POST | `/api/eda/ask` | Follow-up question — body `{session_id, question}` |
| GET | `/api/eda/{session_id}/facts` | Inspect the session's `facts.md` (debug/UI) |

Both POST endpoints run the blocking pipeline in a threadpool and return JSON
(`response`, `images`, `followups`, `artifacts`, `mock`). See [04 — EDA Pipeline](04-eda-pipeline.md).

## Market Research — `/api/market-research`

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/market-research/analyze` | Body `{file_id, description?}` → full `AnalysisResult` JSON |

Supports `.csv/.xlsx/.xls` only. Runs `market_research.analyze_file` in a threadpool and returns the
data profile, research report, and causal DAG. See [06 — Market Research](06-market-research.md).

## Causal Analysis — `/api/causal`

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/causal/runs` | Start the full 4-stage chain (background thread) → `{run_id, stages}` |
| GET | `/api/causal/runs/{run_id}` | Poll progress; returns stage statuses/timings + full result when complete |

Body `{file_id}` (`.csv/.xlsx/.xls`). Stages: `eda` → `market_research` → `insight_builder` →
`synthesis`. Runs are in-memory (lost on restart); the whole chain takes 30–40+ minutes. The result
contains `{file, eda, market_research, insights, synthesis{executive_summary, causal_story,
key_drivers[], recommendations[]}}`.

## Insight Builder — `/api/insight` (mounted sub-app)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/insight/health` | Liveness |
| POST | `/api/insight/datasets` | Upload a CSV/Excel file → `{session_id, filename}` |
| POST | `/api/insight/datasets/{session_id}/market-research` | Attach a Market Research `output.json` (optional) |
| POST | `/api/insight/datasets/{session_id}/analyze` | Run the full graph (body `{domain?, market_research_path?}`) → report dict |
| GET | `/api/insight/datasets/{session_id}/insights` | Paginated validated insights (`offset`, `limit`) |
| GET | `/api/insight/datasets/{session_id}/kpis` | Paginated business-fact KPIs (`offset`, `limit`) |
| POST | `/api/insight/datasets/{session_id}/chat` | Ad-hoc question (body `{question}`) — Tier A→B |
| DELETE | `/api/insight/datasets/{session_id}` | Delete the session + scratch dir |

The `analyze` response includes counts (`n_rows`, `n_candidates_generated`,
`n_candidates_after_triage`, `n_executed`, `n_validated`), `insights`, `top_insights`, `kpis`/
`top_kpis`, an optional `executive_summary`, the market section, the audit dir, and a `graph_trace`.
See [05 — Insight Builder](05-insight-builder.md).

## Legacy Express backend — `/api` on port 3001 (optional)

The original Node backend exposes only:

| Method | Path |
|---|---|
| GET / POST / PATCH / DELETE | `/api/chats` (+ `/messages`) |
| GET / POST / DELETE | `/api/files` |
| GET | `/health` |

It shares the same SQLite database. The frontend proxies to the FastAPI backend (8001), not this
one, so it is not required to run the product.
