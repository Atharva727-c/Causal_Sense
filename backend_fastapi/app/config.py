from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve paths relative to this file so the server can be run from any CWD.
_HERE = Path(__file__).parent          # backend_fastapi/app/
_ROOT = _HERE.parent                   # backend_fastapi/
_SHARED_DATA = _ROOT.parent / "backend" / "data"  # shared with Express backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "CausalSense API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8001

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 4096
    claude_timeout: float = 120.0

    # ── EPAM DIAL (Azure OpenAI proxy) — powers the EDA pipeline ───────────────
    dial_api_key: str = ""
    dial_endpoint: str = "https://ai-proxy.lab.epam.com"
    dial_api_version: str = "2024-02-01"
    dial_chat_deployment: str = "gpt-5.5-2026-04-24-reasoning"
    dial_embeddings_deployment: str = "text-embedding-3-large"
    dial_timeout: float = 180.0
    # Reasoning models reject `temperature`; leave True to omit it on chat calls.
    dial_is_reasoning_model: bool = True
    dial_max_completion_tokens: int = 8192

    # ── EDA pipeline ──────────────────────────────────────────────────────────
    eda_send_plot_images: bool = True          # send PNGs to the vision model
    eda_vector_top_k: int = 5                  # chunks returned by the retriever
    eda_chunk_size: int = 1200                 # chars per detailed-file chunk
    eda_chunk_overlap: int = 150
    eda_sample_rows: int = 100_000             # passed to explore_dataset.py
    eda_explorer_script: Path = _ROOT.parent / "tools" / "explore_dataset.py"
    eda_workspace_dir: Path = _SHARED_DATA / "eda_workspace"
    eda_react_max_iterations: int = 8

    # ── Storage ───────────────────────────────────────────────────────────────
    # Shared with Express backend by default; override via env if needed.
    upload_dir: Path = _SHARED_DATA / "uploads"
    max_upload_bytes: int = 100 * 1024 * 1024  # 100 MB (matches Express)
    allowed_extensions: frozenset[str] = frozenset(
        {".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet", ".sql", ".txt"}
    )

    # ── Database ──────────────────────────────────────────────────────────────
    # Shared SQLite DB with Express backend.
    database_url: str = f"sqlite+aiosqlite:///{_SHARED_DATA / 'causalsense.db'}"

    # ── Agent ─────────────────────────────────────────────────────────────────
    agent_timeout: int = 300
    max_tool_iterations: int = 10
    enable_mock: bool = True   # word-by-word mock when no API key

    @field_validator("upload_dir", "eda_workspace_dir", mode="before")
    @classmethod
    def ensure_dir(cls, v: Path | str) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
