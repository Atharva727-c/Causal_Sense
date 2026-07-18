"""HTTP API for a frontend: upload a dataset, get the full insight report for
display, and ask ad-hoc questions against it (Tier A -> Tier B routing).

Run locally with: uvicorn insight_builder.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from insight_builder.api.sessions import create_session, delete_session, get_session
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


class ChatRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/datasets")
async def upload_dataset(file: UploadFile) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")
    content = await file.read()
    session = create_session(file.filename, content)
    return {"session_id": session.session_id, "filename": session.filename}


@app.post("/datasets/{session_id}/analyze")
def analyze(session_id: str, body: AnalyzeRequest) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return run_pipeline(str(session.csv_path), domain=body.domain, audit_dir=str(session.audit_dir))


@app.post("/datasets/{session_id}/chat")
def chat(session_id: str, body: ChatRequest) -> dict:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    return answer_question(str(session.csv_path), body.question, audit_dir=str(session.audit_dir))


@app.delete("/datasets/{session_id}")
def delete_dataset(session_id: str) -> dict:
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return {"deleted": True}
