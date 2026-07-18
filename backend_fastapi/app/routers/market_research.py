"""Market Research endpoints — runs the real `market_research` package
(repo root) against an uploaded file and returns its structured output
(profile + research report + optional causal DAG), i.e. the same shape as
the package's output.json artifact."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.database import get_db
from app.models.db import UploadedFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market-research", tags=["Market Research"])

_SUPPORTED = {".csv", ".xlsx", ".xls"}


class MarketResearchRequest(BaseModel):
    file_id: str = Field(..., description="Id of a previously uploaded file")
    description: str | None = Field(None, description="Optional user-supplied dataset description")


@router.post("/analyze", summary="Run the full market-research pipeline on an uploaded file")
async def analyze(body: MarketResearchRequest, db: AsyncSession = Depends(get_db)):
    f = await db.get(UploadedFile, body.file_id)
    if f is None:
        raise NotFoundError(f"File '{body.file_id}' not found")
    disk_path = Path(f.disk_path)
    if not disk_path.exists():
        raise NotFoundError("File data not found on disk.")
    if disk_path.suffix.lower() not in _SUPPORTED:
        raise AppError(
            f"Market research supports {', '.join(sorted(_SUPPORTED))} files only.",
            status_code=400,
            code="unsupported_file_type",
        )

    # Lazy import: the package lives at the repo root (sys.path set up in main.py).
    from market_research import analyze_file

    logger.info("Market research starting on %s", f.original_name)
    result = await run_in_threadpool(
        analyze_file, str(disk_path), body.description, f.original_name
    )
    logger.info("Market research finished on %s", f.original_name)
    return result.model_dump()
