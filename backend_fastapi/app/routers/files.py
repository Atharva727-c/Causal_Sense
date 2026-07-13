"""File management endpoints — upload, list, download, delete."""
from __future__ import annotations
import json
import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import (
    FileTooLargeError, NotFoundError, UnsupportedFileTypeError,
)
from app.database import get_db
from app.models.db import UploadedFile
from app.services.file_processor import detect_file_type, process_file

logger = logging.getLogger(__name__)
_s = get_settings()
router = APIRouter(prefix="/files", tags=["Files"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(f: UploadedFile) -> dict:
    from datetime import datetime, timezone
    ts = datetime.fromtimestamp(f.created_at / 1000, tz=timezone.utc).isoformat()
    return {
        "id": f.id,
        "name": f.name or f.id,
        "originalName": f.original_name,
        "size": f.size,
        "fileType": f.file_type.upper(),
        "mimeType": f.mime_type or "application/octet-stream",
        "rowCount": f.row_count,
        "columnCount": f.column_count,
        "createdAt": ts,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", summary="List uploaded files")
async def list_files(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UploadedFile).order_by(UploadedFile.created_at.desc())
    )
    files = result.scalars().all()
    total_size = sum(f.size for f in files)
    return {
        "files": [_serialize(f) for f in files],
        "total": len(files),
        "totalSize": total_size,
    }


async def _do_upload(file: UploadFile, db: AsyncSession) -> dict:
    """Shared upload logic used by both /upload and POST /."""
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in _s.allowed_extensions:
        raise UnsupportedFileTypeError(
            f"Extension '{ext}' is not supported. "
            f"Allowed: {', '.join(sorted(_s.allowed_extensions))}"
        )

    contents = await file.read()
    if len(contents) > _s.max_upload_bytes:
        raise FileTooLargeError(
            f"File exceeds the {_s.max_upload_bytes // 1_048_576} MB limit."
        )

    file_id = str(uuid.uuid4())
    disk_path = _s.upload_dir / f"{file_id}{ext}"
    async with aiofiles.open(disk_path, "wb") as fh:
        await fh.write(contents)

    file_type = detect_file_type(filename)
    meta = await process_file(disk_path, file_type)

    db_file = UploadedFile(
        id=file_id,
        name=f"{file_id}{ext}",
        original_name=filename,
        size=len(contents),
        file_type=file_type.upper(),
        mime_type=file.content_type or "application/octet-stream",
        disk_path=str(disk_path),
        row_count=meta.get("row_count"),
        column_count=meta.get("column_count"),
        schema_json=json.dumps(meta.get("schema", [])),
        preview_json=json.dumps(meta.get("preview", [])),
    )
    db.add(db_file)
    await db.flush()
    await db.refresh(db_file)
    return _serialize(db_file)


@router.post("/upload", status_code=201, summary="Upload a file (Express-compatible path)")
async def upload_file_compat(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await _do_upload(file, db)


@router.post("", status_code=201, summary="Upload a file")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await _do_upload(file, db)


@router.get("/{file_id}", summary="Get file metadata")
async def get_file(file_id: str, db: AsyncSession = Depends(get_db)):
    f = await db.get(UploadedFile, file_id)
    if f is None:
        raise NotFoundError(f"File '{file_id}' not found")
    detail = _serialize(f)
    if f.schema_json:
        detail["schema"] = json.loads(f.schema_json)
    if f.preview_json:
        detail["preview"] = json.loads(f.preview_json)
    return detail


@router.get("/{file_id}/download", summary="Download a file")
async def download_file(file_id: str, db: AsyncSession = Depends(get_db)):
    f = await db.get(UploadedFile, file_id)
    if f is None:
        raise NotFoundError(f"File '{file_id}' not found")
    path = Path(f.disk_path)
    if not path.exists():
        raise NotFoundError("File data not found on disk.")
    return FileResponse(
        path=str(path),
        filename=f.original_name,
        media_type=f.mime_type or "application/octet-stream",
    )


@router.delete("/{file_id}", status_code=204, summary="Delete a file")
async def delete_file(file_id: str, db: AsyncSession = Depends(get_db)):
    f = await db.get(UploadedFile, file_id)
    if f is None:
        raise NotFoundError(f"File '{file_id}' not found")
    try:
        Path(f.disk_path).unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not remove file from disk (%s): %s", f.disk_path, exc)
    await db.delete(f)
