"""Chat CRUD + SSE streaming endpoint.

SSE wire format is 100% compatible with the existing Express backend so the
React frontend needs zero changes when pointing at this server.
"""
from __future__ import annotations
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events import sse_delta, sse_done, sse_error, sse_start
from app.core.exceptions import NotFoundError
from app.database import AsyncSessionLocal, get_db
from app.models.db import Chat, Message
from app.models.schemas import (
    ChatCreate, ChatOut, ChatRename, MessageCreate,
)
from app.services.llm import get_llm, get_system_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats", tags=["Chats"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_chat(db: AsyncSession, chat_id: str) -> Chat:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if chat is None:
        raise NotFoundError(f"Chat '{chat_id}' not found")
    return chat


def _auto_title(content: str) -> str:
    return (content[:52] + "…") if len(content) > 52 else content


def _serialize_chat(chat: Chat, last_msg: str | None = None) -> dict:
    from datetime import datetime, timezone
    def ms_to_iso(ts: int) -> str:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

    return {
        "id": chat.id,
        "title": chat.title,
        "lastMessage": last_msg,
        "createdAt": ms_to_iso(chat.created_at),
        "updatedAt": ms_to_iso(chat.updated_at),
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", summary="List all chats")
async def list_chats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Chat).order_by(Chat.updated_at.desc())
    )
    chats = result.scalars().all()

    chat_outs: list[dict] = []
    for chat in chats:
        msg_result = await db.execute(
            select(Message.content)
            .where(Message.chat_id == chat.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last = msg_result.scalar_one_or_none()
        chat_outs.append(_serialize_chat(chat, last))

    return {"chats": chat_outs, "total": len(chat_outs)}


@router.post("", status_code=201, summary="Create a chat")
async def create_chat(body: ChatCreate, db: AsyncSession = Depends(get_db)):
    chat = Chat(id=str(uuid.uuid4()), title=body.title or "New Chat")
    db.add(chat)
    await db.flush()
    await db.refresh(chat)
    return _serialize_chat(chat)


@router.get("/{chat_id}", summary="Get chat + messages")
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.messages))
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise NotFoundError(f"Chat '{chat_id}' not found")

    from datetime import datetime, timezone
    def ms_to_iso(ts: int) -> str:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

    messages = [
        {
            "id": m.id,
            "chatId": m.chat_id,
            "role": m.role,
            "content": m.content,
            "mode": m.mode,
            "timestamp": ms_to_iso(m.created_at),
        }
        for m in chat.messages
    ]
    return {**_serialize_chat(chat), "messages": messages}


@router.patch("/{chat_id}", summary="Rename a chat")
async def rename_chat(
    chat_id: str,
    body: ChatRename,
    db: AsyncSession = Depends(get_db),
):
    chat = await _get_chat(db, chat_id)
    chat.title = body.title
    await db.flush()
    await db.refresh(chat)
    return _serialize_chat(chat)


@router.delete("/{chat_id}", status_code=204, summary="Delete a chat")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    chat = await _get_chat(db, chat_id)
    await db.delete(chat)


# ── Streaming message endpoint ────────────────────────────────────────────────

@router.post("/{chat_id}/messages", summary="Send a message (SSE stream)")
async def send_message(
    chat_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a ``text/event-stream`` response.

    Wire format (identical to Express backend):
    ```
    data: {"event":"start","userMsgId":"<uuid>"}
    data: {"delta":"<text chunk>"}
    data: {"event":"done","assistantMsgId":"<uuid>","title":"<title>"}
    ```
    """
    # ── Phase 1: DB setup (uses injected session) ─────────────────────────────
    chat = await _get_chat(db, chat_id)

    # Load existing messages BEFORE inserting the new one.
    msg_result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    history_rows = msg_result.scalars().all()

    # Persist user message.
    user_msg_id = str(uuid.uuid4())
    user_msg = Message(
        id=user_msg_id,
        chat_id=chat_id,
        role="user",
        content=body.content,
        mode=body.mode,
    )
    db.add(user_msg)

    # Auto-title on first message.
    is_first_message = len(history_rows) == 0
    if is_first_message:
        chat.title = _auto_title(body.content)

    # Placeholder assistant message (content filled in by the generator).
    assistant_id = str(uuid.uuid4())
    assistant_msg = Message(
        id=assistant_id,
        chat_id=chat_id,
        role="assistant",
        content="",
        mode=body.mode,
    )
    db.add(assistant_msg)
    await db.commit()

    # Build Anthropic message list from history + new user message.
    anthropic_messages = [
        {"role": m.role, "content": m.content}
        for m in history_rows[-40:]  # last 40 rows → ~20 turns, matching Express
    ]
    user_content = body.content
    if body.file_context:
        user_content = f"[Context — uploaded files: {body.file_context}]\n\n{body.content}"
    anthropic_messages.append({"role": "user", "content": user_content})

    system = get_system_prompt(body.mode)
    llm = get_llm()
    final_title = chat.title  # capture for SSE done event

    # ── Phase 2: Streaming generator (uses its own fresh session for the save) ──
    async def event_stream():
        yield sse_start(user_msg_id)
        accumulated = ""
        in_tok: int | None = None
        out_tok: int | None = None

        if llm.available:
            try:
                async for etype, edata in llm.stream(
                    anthropic_messages, system=system
                ):
                    if etype == "text":
                        chunk = edata["text"]
                        accumulated += chunk
                        yield sse_delta(chunk)
                    elif etype == "input_tokens":
                        in_tok = edata["count"]
                    elif etype == "output_tokens":
                        out_tok = edata["count"]
            except Exception as exc:
                logger.exception("LLM stream error in chat %s", chat_id)
                yield sse_error("stream_error", str(exc))
                return
        else:
            for word in llm.mock_text(body.mode).split():
                chunk = word + " "
                accumulated += chunk
                yield sse_delta(chunk)
                await asyncio.sleep(0.04)

        # Persist final assistant content with a fresh session.
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Message).where(Message.id == assistant_id)
            )
            msg = result.scalar_one_or_none()
            if msg:
                msg.content = accumulated.strip()
                msg.input_tokens = in_tok
                msg.output_tokens = out_tok
                await session.commit()

        yield sse_done(assistant_id, final_title)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
