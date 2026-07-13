"""Agent run endpoints — create, stream, and poll runs."""
from __future__ import annotations
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import sse_delta, sse_done, sse_error
from app.core.exceptions import NotFoundError
from app.database import AsyncSessionLocal, get_db
from app.models.db import AgentRun, UploadedFile
from app.models.schemas import AgentRunCreate, AgentRunOut
from app.services.agents.base import AgentContext
from app.services.agents.registry import get_agent, list_agents
from app.services.llm import get_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agents"])


# ── Discovery ─────────────────────────────────────────────────────────────────

@router.get("", summary="List available agents")
async def list_available_agents():
    return {"agents": list_agents()}


# ── Run endpoints ─────────────────────────────────────────────────────────────

@router.post(
    "/runs",
    status_code=200,
    summary="Create and stream an agent run",
    response_description="text/event-stream — same SSE format as /chats/{id}/messages",
)
async def create_run(
    body: AgentRunCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Start an agent run and stream its output.

    The run record is persisted in ``agent_runs`` so status can be polled
    via ``GET /agents/runs/{id}``.

    **Event types** (same wire format as chat streaming):
    - ``delta`` — text token from the LLM
    - ``agent_step`` — agent reasoning/planning step (for UI progress display)
    - ``tool_use`` — agent calling a tool
    - ``tool_result`` — tool response fed back to the agent
    - ``done`` — run complete
    - ``error`` — unrecoverable error
    """
    # Validate agent type.
    try:
        agent = get_agent(body.agent_type)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    llm = get_llm()

    # Load file context if file IDs were provided.
    files_ctx: list[dict] = []
    if body.file_ids:
        result = await db.execute(
            select(UploadedFile).where(UploadedFile.id.in_(body.file_ids))
        )
        for f in result.scalars().all():
            files_ctx.append({
                "name": f.original_name,
                "type": f.file_type,
                "schema": json.loads(f.schema_json or "[]"),
                "preview": json.loads(f.preview_json or "[]"),
                "row_count": f.row_count,
                "column_count": f.column_count,
            })

    # Create run record in DB.
    run_id = str(uuid.uuid4())
    run = AgentRun(
        id=run_id,
        chat_id=body.chat_id,
        agent_type=body.agent_type,
        status="running",
        input_payload=json.dumps({"query": body.query, "config": body.config}),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()

    ctx = AgentContext(query=body.query, files=files_ctx, config=body.config)

    async def event_stream():
        accumulated = ""
        try:
            if llm.available:
                async for chunk in agent.stream(ctx):
                    if '"delta"' in chunk:
                        try:
                            payload = json.loads(chunk[5:].strip())
                            accumulated += payload.get("delta", "")
                        except Exception:
                            pass
                    yield chunk
            else:
                # Mock word-by-word (same as chat endpoint)
                for word in llm.mock_text(agent.mode).split():
                    chunk_str = word + " "
                    accumulated += chunk_str
                    yield sse_delta(chunk_str)
                    await asyncio.sleep(0.04)
                yield sse_done(run_id)

            async with AsyncSessionLocal() as session:
                r = await session.get(AgentRun, run_id)
                if r:
                    r.status = "completed"
                    r.output_payload = json.dumps({"content": accumulated.strip()})
                    r.completed_at = datetime.now(timezone.utc)
                    await session.commit()

        except Exception as exc:
            logger.exception("Agent run %s failed", run_id)
            async with AsyncSessionLocal() as session:
                r = await session.get(AgentRun, run_id)
                if r:
                    r.status = "failed"
                    r.error = str(exc)
                    r.completed_at = datetime.now(timezone.utc)
                    await session.commit()
            yield sse_error("agent_error", str(exc))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/runs/{run_id}", response_model=AgentRunOut, summary="Poll agent run status")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError(f"Agent run '{run_id}' not found")
    return run
