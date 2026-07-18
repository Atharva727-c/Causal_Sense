"""Turn orchestration for the EDA pipeline.

``run_initial_eda``  — turn 1: run the explorer notebook, analyze it (steps 3-10),
persist facts + vector chunks, return a user response + 5 follow-ups.
``answer_followup``  — turn N: ReAct agent answers, then we accumulate new facts
and chunks so knowledge compounds across the conversation.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.services.eda_pipeline import dial, notebook as nb
from app.services.eda_pipeline.agent import run_react
from app.services.eda_pipeline.chunking import chunk_detailed
from app.services.eda_pipeline.facts import FactsFile
from app.services.eda_pipeline.prompts import TURN1_SYSTEM, turn1_output_contract
from app.services.eda_pipeline.vectorstore import get_store
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)
_s = get_settings()

_FOLLOWUP_BLOCK = re.compile(r"<<FOLLOWUPS>>(.*?)<<END>>", re.DOTALL | re.IGNORECASE)
_FOLLOWUP_LINE = re.compile(r"^\s*\d+[.)]\s*(.+?)\s*$", re.MULTILINE)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def strip_followups(text: str) -> tuple[str, list[str]]:
    """Extract & remove a trailing ``<<FOLLOWUPS>>...<<END>>`` block."""
    m = _FOLLOWUP_BLOCK.search(text)
    if not m:
        return text.strip(), []
    questions = [q.strip() for q in _FOLLOWUP_LINE.findall(m.group(1)) if q.strip()]
    clean = (text[: m.start()] + text[m.end():]).strip()
    return clean, questions[:5]


def _index_detailed(ws: Workspace, detailed: str, source: str) -> int:
    """Write the transient detailed file, chunk → vector store, then delete it."""
    if not detailed.strip():
        return 0
    tmp = ws.detailed_tmp_path
    tmp.write_text(detailed, encoding="utf-8")
    try:
        chunks = chunk_detailed(
            detailed,
            session_id=ws.session_id,
            source=source,
            size=_s.eda_chunk_size,
            overlap=_s.eda_chunk_overlap,
        )
        added = get_store(ws).add_chunks(chunks)
    finally:
        tmp.unlink(missing_ok=True)  # transient — purpose served
    return added


# ══════════════════════════════════════════════════════════════════════════════
# Turn 1
# ══════════════════════════════════════════════════════════════════════════════
def run_initial_eda(
    session_id: str,
    dataset_path: str | Path,
    *,
    target: Optional[str] = None,
    time_col: Optional[str] = None,
) -> dict[str, Any]:
    ws = Workspace.for_session(session_id)
    dataset_path = Path(dataset_path)

    # 1) Execute the exploration notebook (checklist steps 1-6).
    run = nb.run_explorer(dataset_path, ws, target=target, time_col=time_col)
    if not run["ok"]:
        return {
            "ok": False,
            "error": "Exploration script failed.",
            "returncode": run["returncode"],
            "stderr": run["stderr"],
        }

    # 2) Parse notebook → structured cells.
    cells = nb.parse_notebook(run["notebook"])

    # 3) Build multimodal content (code + text + plot images) and analyze.
    content = nb.build_llm_content(cells, send_images=_s.eda_send_plot_images)
    content.append({
        "type": "text",
        "text": (
            f"Dataset file: {dataset_path.name}\n"
            f"The above is the full executed notebook (steps 1-6).\n\n{turn1_output_contract()}"
        ),
    })
    result = dial.chat_json(TURN1_SYSTEM, content)

    facts = str(result.get("facts", "")).strip()
    detailed = str(result.get("detailed", "")).strip()
    user_response = str(result.get("user_response", "")).strip()
    followups = [str(q).strip() for q in (result.get("followups") or [])][:5]

    # 4) Persist concise facts (always in context).
    FactsFile(ws).initialize(facts)

    # 5) Chunk the detailed writeup into the vector store, then delete it.
    n_chunks = _index_detailed(ws, detailed, source="turn1")

    return {
        "ok": True,
        "session_id": session_id,
        "response": user_response,
        "followups": followups,
        "artifacts": {
            "notebook": str(run["notebook"]),
            "run_dir": str(ws.run_dir),
            "n_cells": len(cells),
            "n_images": sum(len(c.images) for c in cells),
            "n_chunks": n_chunks,
            "facts_path": str(ws.facts_path),
        },
        "mock": not dial.available(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Turn N
# ══════════════════════════════════════════════════════════════════════════════
def answer_followup(session_id: str, question: str) -> dict[str, Any]:
    ws = Workspace.for_session(session_id)
    if not ws.facts_path.exists():
        return {"ok": False, "error": "No EDA session found. Run the initial analysis first."}

    store = get_store(ws)
    facts = FactsFile(ws).read()

    raw = run_react(ws, store, question, facts)
    answer, followups = strip_followups(raw)

    # Accumulate: append a concise fact + index the answer for future retrieval.
    turn_id = uuid.uuid4().hex[:8]
    FactsFile(ws).append_turn(
        label=f"Follow-up: {question[:80]}",
        facts_markdown=answer[:600],
    )
    detailed_block = f"[[SECTION=Follow-up Q&A | KIND=followup]]\nQ: {question}\n\nA: {answer}"
    _index_detailed(ws, detailed_block, source=f"turn-{turn_id}")

    return {
        "ok": True,
        "session_id": session_id,
        "response": answer,
        "followups": followups,
        "mock": not dial.available(),
    }
