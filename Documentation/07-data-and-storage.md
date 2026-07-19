# 07 — Data & Storage

All persistent state lives under **`backend/data/`** and is shared between the FastAPI backend
and the legacy Express backend. This directory is git-ignored.

```
backend/data/
├── causalsense.db            SQLite database (WAL mode)
├── causalsense.db-shm        WAL shared-memory
├── causalsense.db-wal        WAL log
├── uploads/                  uploaded dataset files (named {uuid}{ext})
└── eda_workspace/            per-EDA-session artifacts
    └── <safe_session_id>/
        ├── run/              executed notebook, plots, profile.json
        ├── facts.md          concise always-in-context knowledge base
        ├── detailed.tmp.md   transient detailed writeup (chunked then deleted)
        ├── chroma/           Chroma dense vector store
        ├── bm25.json         persisted BM25 sparse corpus
        └── insight_audit/    (causal runs) rendered scripts + coerced_dataset.csv
```

## SQLite database

The database is shared. The **Express backend owns the original schema**; the **FastAPI backend
adds one table and a few nullable columns** via idempotent additive `ALTER TABLE` migrations run
on startup (`app/database.py` → `create_tables()`), so both backends can read and write the same
file. Timestamps on the shared tables are stored as **Unix milliseconds (INTEGER)**.

### `chats`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID string |
| `title` | TEXT | |
| `created_at` | INTEGER | Unix ms |
| `updated_at` | INTEGER | Unix ms |

Relationships: `messages` (cascade delete), `agent_runs`.

### `messages`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `chat_id` | TEXT FK → chats | ON DELETE CASCADE |
| `role` | TEXT | `user` \| `assistant` |
| `content` | TEXT | |
| `created_at` | INTEGER | Unix ms |
| `mode` | TEXT | **FastAPI-added**, nullable |
| `input_tokens` | INTEGER | **FastAPI-added**, nullable |
| `output_tokens` | INTEGER | **FastAPI-added**, nullable |

### `files`
| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `name` | TEXT | nullable |
| `original_name` | TEXT | |
| `size` | INTEGER | |
| `file_type` | TEXT | csv/excel/json/parquet/sql/text/other |
| `mime_type` | TEXT | |
| `disk_path` | TEXT | absolute path under `uploads/` |
| `created_at` | INTEGER | Unix ms |
| `row_count` | INTEGER | **FastAPI-added**, nullable |
| `column_count` | INTEGER | **FastAPI-added**, nullable |
| `schema_json` | TEXT | **FastAPI-added** — extracted column schema (JSON) |
| `preview_json` | TEXT | **FastAPI-added** — 5-row preview (JSON) |

### `agent_runs` (FastAPI-only)
Uses ISO-8601 `DateTime` columns (not Unix ms).

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | |
| `chat_id` | TEXT FK → chats | ON DELETE SET NULL |
| `agent_type` | TEXT | e.g. `eda`, `market_research` |
| `status` | TEXT | pending \| running \| completed \| failed |
| `input_payload` | JSON | |
| `output_payload` | JSON | |
| `steps_json` | JSON[] | structured step log |
| `error` | TEXT | |
| `started_at` / `completed_at` / `created_at` | DateTime | |

Pragmas set on startup: **WAL** journal mode, `foreign_keys=ON`, `synchronous=NORMAL`.

## Uploaded files

Written by `POST /api/files/upload` to `uploads/{uuid}{ext}` via aiofiles. On upload,
`file_processor.process_file` reads the file with pandas (csv/excel capped at 50k rows) and
extracts `row_count`, `column_count`, a column schema (name/dtype/null_pct/unique_count, ≤100
cols) stored in `schema_json`, and a 5-row `preview_json`. Limits: 100 MB max; extensions
csv/tsv/xlsx/xls/json/parquet/sql/txt.

## EDA workspace

Each EDA session gets an isolated directory under `eda_workspace/<safe_session_id>/` (see
[04 — EDA Pipeline](04-eda-pipeline.md)). The Causal Analysis chain reuses this layout under a
`causal-<run_id>` session id, adding an `insight_audit/` directory containing every rendered
statistical script and the `coerced_dataset.csv` that those scripts read.

## In-memory state (not persisted)

- **Causal runs** (`app/routers/causal.py`) — tracked in a module-level `_RUNS` dict. This is
  why the backend runs with a single worker and why causal runs are lost on restart. Acceptable
  for the demo.
- **Insight Builder sessions** (`insight_builder/api/sessions.py`) — an in-memory dict plus one
  `tempfile.mkdtemp` scratch root per process. There is no TTL reaper; sessions persist until
  explicitly deleted via `DELETE /api/insight/datasets/{id}`.

## The `output.json` contract

`output.json` is the serialized `AnalysisResult` from Market Research (report + causal DAG). It
is the hand-off between Market Research and Insight Builder. Insight Builder resolves it in this
precedence order (`context/market.py` → `resolve_artifact_path`):

1. An explicit path passed to the pipeline.
2. The `INSIGHT_MARKET_RESEARCH_PATH` environment variable.
3. `output.json` sitting next to the dataset file.

If absent or malformed, the market-dependent graph nodes skip and the report notes why. See
[06 — Market Research](06-market-research.md) for the field-by-field contract.
