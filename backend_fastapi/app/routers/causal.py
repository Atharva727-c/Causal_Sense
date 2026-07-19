"""Causal Analysis — chains the whole toolchain over one uploaded dataset:

    EDA (notebook + vision LLM)  →  Market Research (profile + web + DAG)
        →  Insight Builder (validated statistical insights, fed the MR artifact)
        →  LLM synthesis into one curated causal report.

The chain takes 30-40+ minutes (Insight Builder dominates), so runs execute in
a background thread and the frontend polls ``GET /causal/runs/{id}`` for stage
progress, rendering the full report when the run completes. Runs are kept
in-memory — fine for the demo, lost on restart.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.database import get_db
from app.models.db import UploadedFile
from app.services.eda_pipeline import run_initial_eda
from app.services.eda_pipeline import dial
from app.services.eda_pipeline.facts import FactsFile
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/causal", tags=["Causal Analysis"])

_SUPPORTED = {".csv", ".xlsx", ".xls"}
_STAGES = ["eda", "market_research", "insight_builder", "synthesis"]

_RUNS: dict[str, dict[str, Any]] = {}
_RUNS_LOCK = threading.Lock()


class CausalRunRequest(BaseModel):
    file_id: str = Field(..., description="Id of a previously uploaded file")


def _new_run(filename: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    with _RUNS_LOCK:
        _RUNS[run_id] = {
            "run_id": run_id,
            "file": filename,
            "status": "running",          # running | completed | failed
            "stage": _STAGES[0],
            "stages": {s: {"status": "pending", "seconds": None} for s in _STAGES},
            "error": None,
            "result": None,
            "started_at": time.time(),
        }
    return run_id


def _stage_start(run_id: str, stage: str) -> float:
    with _RUNS_LOCK:
        run = _RUNS[run_id]
        run["stage"] = stage
        run["stages"][stage]["status"] = "running"
    logger.info("Causal run %s: stage %s started", run_id, stage)
    return time.time()


def _stage_done(run_id: str, stage: str, t0: float) -> None:
    with _RUNS_LOCK:
        _RUNS[run_id]["stages"][stage]["status"] = "done"
        _RUNS[run_id]["stages"][stage]["seconds"] = round(time.time() - t0, 1)
    logger.info("Causal run %s: stage %s done (%.0fs)", run_id, stage, time.time() - t0)


def _synthesize(eda_facts: str, mr: dict, report: dict) -> dict:
    """One DIAL call that fuses the three stage outputs into a causal report."""
    dag = mr.get("dag") or {}
    top_insights = report.get("top_insights") or (report.get("insights") or [])[:10]
    insight_lines = [
        str(i.get("narrative", ""))[:300] for i in top_insights if i.get("narrative")
    ]
    mr_summary = (mr.get("market_research") or {}).get("executive_summary", "")
    findings = [
        f.get("title", "") for f in (mr.get("market_research") or {}).get("key_findings", [])
    ]

    if not dial.available():
        return {
            "executive_summary": "[Mock] DIAL not configured — synthesis unavailable; see the stage outputs below.",
            "causal_story": mr_summary,
            "key_drivers": [],
            "recommendations": [],
        }

    system = (
        "You are CausalSense, a causal-inference analyst. You are given the outputs of three "
        "analyses of ONE dataset: (A) EDA facts, (B) market research with a hypothesised causal "
        "DAG, (C) statistically validated insights. Fuse them into one coherent causal report. "
        "Ground every claim in the provided material — cite which analysis supports it. "
        "Never invent numbers."
    )
    user = (
        f"(A) EDA FACTS:\n{eda_facts[:6000]}\n\n"
        f"(B) MARKET RESEARCH SUMMARY:\n{mr_summary}\nKey findings: {json.dumps(findings)}\n"
        f"CAUSAL DAG (nodes/edges): {json.dumps(dag)[:8000]}\n\n"
        f"(C) VALIDATED INSIGHTS:\n" + "\n".join(f"- {ln}" for ln in insight_lines) + "\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        "{\n"
        '  "executive_summary": "<3-5 sentence executive summary of the causal picture>",\n'
        '  "causal_story": "<Markdown: the causal narrative — what drives what, through which '
        'mechanisms, where the DAG is supported or contradicted by the validated insights>",\n'
        '  "key_drivers": [{"driver": "...", "effect": "...", "mechanism": "...", '
        '"evidence": "<which analysis/insight supports this>", "confidence": "high|medium|low"}],\n'
        '  "recommendations": [{"action": "...", "rationale": "...", "priority": "high|medium|low"}]\n'
        "}\n"
        "3-6 key_drivers, 3-5 recommendations."
    )
    return dial.chat_json(system, [{"type": "text", "text": user}])


def _trim_report(report: dict) -> dict:
    """Keep the pieces the UI renders; drop the bulky raw KPI list."""
    keep = [
        "schema", "n_rows", "domain", "n_candidates_generated", "n_candidates_after_triage",
        "n_executed", "n_validated", "executive_summary", "top_insights", "top_kpis",
    ]
    out = {k: report[k] for k in keep if k in report}
    out["insights"] = (report.get("insights") or [])[:20]
    return out


def _run_chain(run_id: str, dataset_path: str, filename: str) -> None:
    try:
        ws = Workspace.for_session(f"causal-{run_id}")

        # ── Stage 1: EDA ──────────────────────────────────────────────────────
        t0 = _stage_start(run_id, "eda")
        eda = run_initial_eda(f"causal-{run_id}", dataset_path)
        if not eda.get("ok"):
            raise RuntimeError(f"EDA stage failed: {eda.get('error')} {eda.get('stderr', '')[:500]}")
        eda_facts = FactsFile(ws).read()
        _stage_done(run_id, "eda", t0)

        # ── Stage 2: Market Research ─────────────────────────────────────────
        t0 = _stage_start(run_id, "market_research")
        from market_research import analyze_file

        mr = analyze_file(dataset_path, None, filename).model_dump()
        artifact_path = ws.root / "market_research.json"
        artifact_path.write_text(json.dumps(mr), encoding="utf-8")
        _stage_done(run_id, "market_research", t0)

        # ── Stage 3: Insight Builder (fed the MR artifact) ───────────────────
        t0 = _stage_start(run_id, "insight_builder")
        from insight_builder.orchestrator import run_pipeline

        report = run_pipeline(
            dataset_path,
            domain=(mr.get("data_profile") or {}).get("domain"),
            audit_dir=str(ws.root / "insight_audit"),
            market_research_path=str(artifact_path),
        )
        _stage_done(run_id, "insight_builder", t0)

        # ── Stage 4: Synthesis ───────────────────────────────────────────────
        t0 = _stage_start(run_id, "synthesis")
        synthesis = _synthesize(eda_facts, mr, report)
        _stage_done(run_id, "synthesis", t0)

        result = {
            "file": filename,
            "eda": {"response": eda.get("response", ""), "images": eda.get("images", {})},
            "market_research": mr,
            "insights": _trim_report(report),
            "synthesis": synthesis,
        }
        with _RUNS_LOCK:
            _RUNS[run_id]["status"] = "completed"
            _RUNS[run_id]["result"] = result
        logger.info("Causal run %s completed", run_id)
    except Exception as exc:
        logger.exception("Causal run %s failed", run_id)
        with _RUNS_LOCK:
            run = _RUNS[run_id]
            run["status"] = "failed"
            run["error"] = str(exc)
            if run["stage"] in run["stages"]:
                run["stages"][run["stage"]]["status"] = "failed"


@router.post("/runs", summary="Start a full causal-analysis pipeline run (background)")
async def create_run(body: CausalRunRequest, db: AsyncSession = Depends(get_db)):
    f = await db.get(UploadedFile, body.file_id)
    if f is None:
        raise NotFoundError(f"File '{body.file_id}' not found")
    disk_path = Path(f.disk_path)
    if not disk_path.exists():
        raise NotFoundError("File data not found on disk.")
    if disk_path.suffix.lower() not in _SUPPORTED:
        raise AppError(
            f"Causal analysis supports {', '.join(sorted(_SUPPORTED))} files only.",
            status_code=400,
            code="unsupported_file_type",
        )

    run_id = _new_run(f.original_name)
    threading.Thread(
        target=_run_chain, args=(run_id, str(disk_path), f.original_name), daemon=True
    ).start()
    return {"run_id": run_id, "stages": _STAGES}


@router.get("/runs/{run_id}", summary="Poll causal run progress / fetch the report")
def get_run(run_id: str):
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
        if run is None:
            raise NotFoundError(f"Causal run '{run_id}' not found")
        out = {k: v for k, v in run.items() if k != "result"}
        out = json.loads(json.dumps(out))  # deep copy of the mutable bits
        if run["status"] == "completed":
            out["result"] = run["result"]
    out["elapsed_seconds"] = round(time.time() - out.pop("started_at"), 1)
    return out
