"""EDA pipeline endpoints (DIAL + LangGraph ReAct, parallel to the Anthropic agents).

    POST /api/eda/analyze   run turn-1 EDA on an uploaded file
    POST /api/eda/ask       ask a follow-up question in an existing session
    GET  /api/eda/{sid}/facts   inspect the session facts file (debug/UI)

Responses are plain JSON for now (SSE streaming can be layered on later). The
blocking pipeline (subprocess notebook execution, Chroma, sync OpenAI) runs in a
threadpool so the event loop stays responsive.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.db import UploadedFile
from app.services.eda_pipeline import answer_followup, run_initial_eda
from app.services.eda_pipeline.facts import FactsFile
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eda", tags=["EDA Pipeline"])


# ── Request models ─────────────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    session_id: str = Field(..., description="Chat/session id — namespaces the workspace")
    file_id: str = Field(..., description="Id of a previously uploaded file")
    target: str | None = Field(None, description="Optional target column (else auto-suggested)")
    time_col: str | None = Field(None, description="Optional datetime column for time-series analysis")


class AskRequest(BaseModel):
    session_id: str
    question: str


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.post("/analyze", summary="Run initial EDA on an uploaded dataset (turn 1)")
async def analyze(body: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    f = await db.get(UploadedFile, body.file_id)
    if f is None:
        raise NotFoundError(f"File '{body.file_id}' not found")
    disk_path = Path(f.disk_path)
    if not disk_path.exists():
        raise NotFoundError("File data not found on disk.")

    result = await run_in_threadpool(
        run_initial_eda,
        body.session_id,
        disk_path,
        target=body.target,
        time_col=body.time_col,
    )
    return result


@router.post("/ask", summary="Ask a follow-up question (turn N)")
async def ask(body: AskRequest):
    result = await run_in_threadpool(answer_followup, body.session_id, body.question)
    return result


@router.get("/{session_id}/facts", summary="Inspect the session facts file")
async def get_facts(session_id: str):
    ws = Workspace.for_session(session_id)
    return {"session_id": session_id, "facts": FactsFile(ws).read()}
