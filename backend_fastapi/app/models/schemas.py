"""Pydantic v2 request / response schemas.

Timestamps are stored in SQLite as Unix milliseconds (INTEGER) to match the
Express backend.  The field validators below convert them to datetime objects
for the API response so consumers get ISO-8601 strings.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ms_to_dt(v: int | datetime | None) -> datetime | None:
    if isinstance(v, int):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc)
    return v


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatCreate(BaseModel):
    title: Optional[str] = None


class ChatRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    last_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _ts(cls, v: Any) -> datetime:
        return _ms_to_dt(v) or datetime.now(timezone.utc)


class ChatListOut(BaseModel):
    chats: list[ChatOut]
    total: int


# ── Message ──────────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=32_000)
    mode: Optional[str] = None          # 'eda' | 'market_research' | None
    file_context: Optional[str] = None  # pre-built context string from file(s)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    role: str
    content: str
    mode: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _ts(cls, v: Any) -> datetime:
        return _ms_to_dt(v) or datetime.now(timezone.utc)


class ChatHistoryOut(BaseModel):
    chat: ChatOut
    messages: list[MessageOut]


# ── File ─────────────────────────────────────────────────────────────────────

class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    file_type: str
    size: int
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _ts(cls, v: Any) -> datetime:
        return _ms_to_dt(v) or datetime.now(timezone.utc)


class FileDetailOut(FileOut):
    schema_json: Optional[str] = None
    preview_json: Optional[str] = None


class FileListOut(BaseModel):
    files: list[FileOut]
    total: int
    total_size: int


# ── Agent ─────────────────────────────────────────────────────────────────────

class AgentRunCreate(BaseModel):
    agent_type: str = Field(..., pattern=r"^[a-z_]+$")
    chat_id: Optional[str] = None
    query: str = Field(..., min_length=1, max_length=32_000)
    file_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: Optional[str] = None
    agent_type: str
    status: str
    input_payload: Optional[str] = None
    output_payload: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class AgentInfo(BaseModel):
    name: str
    description: str
    mode: Optional[str] = None


class AgentListOut(BaseModel):
    agents: list[AgentInfo]
