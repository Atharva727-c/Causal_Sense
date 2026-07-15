"""The per-session *facts file* — a concise, always-in-context knowledge base.

Unlike the detailed writeup (which is chunked into the vector store and then
deleted), the facts file is small enough to inject verbatim into every LLM
call. It accumulates the distilled, high-signal findings across turns.

It is a plain Markdown file so it's human-inspectable and diff-friendly. We keep
a soft character budget; if it grows past that, the oldest turn sections are
dropped (the vector store still holds the detail).
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)

_MAX_FACTS_CHARS = 12_000
_HEADER = "# Session Facts — CausalSense EDA\n\n"


class FactsFile:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self.path = ws.facts_path

    # ── read ──────────────────────────────────────────────────────────────
    def read(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return ""

    def exists(self) -> bool:
        return self.path.exists() and bool(self.read().strip())

    # ── write / append ──────────────────────────────────────────────────────
    def initialize(self, facts_markdown: str) -> None:
        """Create the facts file from the turn-1 distilled findings."""
        body = _HEADER + facts_markdown.strip() + "\n"
        self.path.write_text(body, encoding="utf-8")
        logger.info("Initialized facts file for %s (%d chars)", self.ws.session_id, len(body))

    def append_turn(self, label: str, facts_markdown: str) -> None:
        """Append a concise block of new facts learned on a later turn."""
        text = facts_markdown.strip()
        if not text:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        block = f"\n## {label} ({ts})\n{text}\n"
        current = self.read() or _HEADER
        self.path.write_text(self._trim(current + block), encoding="utf-8")

    def _trim(self, text: str) -> str:
        if len(text) <= _MAX_FACTS_CHARS:
            return text
        # Keep the header + the most recent tail within budget.
        keep = text[-(_MAX_FACTS_CHARS - len(_HEADER)):]
        cut = keep.find("\n## ")  # start at a clean section boundary if possible
        keep = keep[cut:] if cut != -1 else keep
        logger.info("Trimmed facts file for %s", self.ws.session_id)
        return _HEADER + "_[older facts trimmed — see vector store for detail]_\n" + keep
