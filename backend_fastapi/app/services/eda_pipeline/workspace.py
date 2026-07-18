"""Per-session workspace layout on disk.

Everything a session produces is namespaced under
``<eda_workspace_dir>/<session_id>/`` so sessions never collide and a chat can
be wiped by deleting one directory.

    <session_id>/
        run/                 explore_dataset.py output (notebook, plots, profile.json, ...)
        facts.md             concise, always-in-context knowledge file
        detailed.tmp.md      transient detailed writeup (chunked then deleted)
        chroma/              persistent Chroma collection for this session
        bm25.json            chunk texts + ids for the BM25 half of hybrid search
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

_s = get_settings()

_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


def _safe(session_id: str) -> str:
    """Filesystem-safe session id (chat ids are UUIDs, but be defensive)."""
    return _SAFE.sub("_", session_id)[:64] or "default"


@dataclass(frozen=True)
class Workspace:
    """Resolved paths for one session. Directories are created on access."""

    session_id: str
    root: Path

    @classmethod
    def for_session(cls, session_id: str) -> "Workspace":
        root = _s.eda_workspace_dir / _safe(session_id)
        root.mkdir(parents=True, exist_ok=True)
        return cls(session_id=session_id, root=root)

    # ── Sub-paths ──────────────────────────────────────────────────────────
    @property
    def run_dir(self) -> Path:
        p = self.root / "run"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def notebook_path(self) -> Path:
        return self.run_dir / "data_exploration.ipynb"

    @property
    def profile_path(self) -> Path:
        return self.run_dir / "profile.json"

    @property
    def facts_path(self) -> Path:
        return self.root / "facts.md"

    @property
    def detailed_tmp_path(self) -> Path:
        return self.root / "detailed.tmp.md"

    @property
    def chroma_dir(self) -> Path:
        p = self.root / "chroma"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def bm25_path(self) -> Path:
        return self.root / "bm25.json"

    @property
    def collection_name(self) -> str:
        # Chroma collection names: 3-63 chars, alphanumeric/._- , start/end alnum.
        return f"eda_{_safe(self.session_id)}"[:63]
