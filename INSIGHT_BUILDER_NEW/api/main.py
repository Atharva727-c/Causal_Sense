"""HTTP API for a frontend: upload a dataset (CSV or Excel), optionally attach
a Market Researcher artifact, get the full insight report for display, and ask
ad-hoc questions against it (Tier A -> Tier B routing).

Run locally with: uvicorn insight_builder.api.main:app --reload
"""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from insight_builder.api.sessions import create_session, delete_session, get_session
from insight_builder.context.market import load_market_context, resolve_artifact_path
from insight_builder.ingestion.loader import SUPPORTED_SUFFIXES, dataset_columns, is_supported_dataset
from insight_builder.kpi_ranking import rank_business_kpis
from insight_builder.orchestrator import run_pipeline
from insight_builder.qa.answer import answer_question

app = FastAPI(title="Insight Builder API")

# Dev-friendly default; a real deployment should restrict this to the actual
# frontend origin(s) rather than allowing every origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    domain: str | None = None
    # Server-side path to a Market Researcher output.json; the uploaded-file
    # route (POST .../market-research) takes precedence over this.
    market_research_path: str | None = None


class ChatRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/datasets")
async def upload_dataset(file: UploadFile) -> dict:
    if not file.filename or not is_supported_dataset(file.filename):
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise HTTPException(status_code=400, detail=f"Unsupported file type; supported: {supported}")
    content = await file.read()
    session = create_session(file.filename, content)
    return {"session_id": session.session_id, "filename": session.filename}


@app.post("/datasets/{session_id}/market-research")
async def attach_market_research(session_id: str, file: UploadFile) -> dict:
    """Attach a Market Researcher output.json to the session. Optional: when
    absent, analysis runs on the dataset alone."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    content = await file.read()
    try:
        json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="File is not valid JSON")

    artifact_path = session.dir / "market_research.json"
    artifact_path.write_bytes(content)
    session.market_research_path = artifact_path
    session.market_context = None  # reloaded lazily against the dataset schema
    return {"attached": True, "session_id": session_id}


def _session_market_context(session, explicit_path: str | None = None):
    """Resolve+load the session's market context once and cache it; any
    failure (missing/invalid artifact) just means no context."""
    if session.market_context is not None:
        return session.market_context
    artifact = (
        session.market_research_path
        if session.market_research_path is not None
        else resolve_artifact_path(session.dataset_path, explicit_path)
    )
    if artifact is None:
        return None
    columns = dataset_columns(session.dataset_path)
    context = load_market_context(artifact, column_names=columns)
    if context is not None and not context.matches_dataset(columns):
        context = None  # artifact describes a different dataset
    session.market_context = context
    return session.market_context


@app.post("/datasets/{session_id}/analyze")
def analyze(session_id: str, body: AnalyzeRequest) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    market_path = (
        str(session.market_research_path)
        if session.market_research_path is not None
        else body.market_research_path
    )
    report = run_pipeline(
        str(session.dataset_path),
        domain=body.domain,
        audit_dir=str(session.audit_dir),
        market_research_path=market_path,
    )
    # Prime the chat-time cache with the same artifact analyze used.
    _session_market_context(session, market_path)
    # Cache the full (unranked) KPI fact list so GET .../kpis can page further
    # down the same ranking without re-running the whole candidate pipeline.
    session.kpi_cache = report["kpis"]
    return report


@app.get("/datasets/{session_id}/kpis")
def kpis(session_id: str, offset: int = 0, limit: int = 10) -> dict:
    """Paginate through the business-fact KPIs from the last /analyze call,
    ranked exactly like top_kpis was (so "show me more" always continues the
    same ordering rather than a differently-scored list). Call /analyze at
    least once first -- KPIs aren't computed from scratch here."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if session.kpi_cache is None:
        raise HTTPException(status_code=400, detail="No analysis yet; call POST .../analyze first")
    if offset < 0 or limit < 1:
        raise HTTPException(status_code=400, detail="offset must be >= 0 and limit must be >= 1")

    ranked = rank_business_kpis(session.kpi_cache, top_n=offset + limit)
    page = ranked[offset:offset + limit]
    return {
        "kpis": page,
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "total_available": len(session.kpi_cache),
        "has_more": offset + len(page) < len(session.kpi_cache),
    }


@app.post("/datasets/{session_id}/chat")
def chat(session_id: str, body: ChatRequest) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    return answer_question(
        str(session.dataset_path),
        body.question,
        audit_dir=str(session.audit_dir),
        market_context=_session_market_context(session),
    )


@app.delete("/datasets/{session_id}")
def delete_dataset(session_id: str) -> dict:
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return {"deleted": True}
