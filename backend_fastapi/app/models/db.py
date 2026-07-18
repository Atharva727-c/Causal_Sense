"""SQLAlchemy 2.0 ORM models.

Shared tables (chats, messages, files) preserve the Express schema:
  - Timestamps stored as INTEGER (Unix milliseconds).
  - Column names match Express exactly so both backends can read the same rows.

New table (agent_runs) is FastAPI-only and uses ISO DateTime.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Shared with Express ───────────────────────────────────────────────────────

class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), default="New Chat")
    created_at: Mapped[int] = mapped_column(Integer, default=_now_ms)
    updated_at: Mapped[int] = mapped_column(Integer, default=_now_ms, onupdate=_now_ms)

    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="select",
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        "AgentRun",
        back_populates="chat",
        cascade="all, delete-orphan",
        lazy="select",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))        # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int] = mapped_column(Integer, default=_now_ms)

    # FastAPI-added columns (added via ALTER TABLE migration on first startup).
    mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    chat: Mapped[Chat] = relationship("Chat", back_populates="messages")


class UploadedFile(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Express sets `name` to the UUID-based disk filename; FastAPI leaves it NULL.
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    file_type: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    disk_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[int] = mapped_column(Integer, default=_now_ms)

    # FastAPI-added columns (added via ALTER TABLE migration on first startup).
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    column_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    schema_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preview_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ── FastAPI-only ──────────────────────────────────────────────────────────────

class AgentRun(Base):
    """Tracks each agent invocation with full input/output/step history."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True
    )
    agent_type: Mapped[str] = mapped_column(String(64))
    # pending | running | completed | failed
    status: Mapped[str] = mapped_column(String(16), default="pending")
    input_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    output_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    steps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON[]
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    chat: Mapped[Optional[Chat]] = relationship("Chat", back_populates="agent_runs")
