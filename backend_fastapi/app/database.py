from __future__ import annotations
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.debug,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
)


async def create_tables() -> None:
    """Create tables and apply additive migrations (idempotent)."""
    from app.models.db import Base  # local import to avoid circular deps

    async with engine.begin() as conn:
        # Create any tables that don't exist yet (e.g. agent_runs).
        # Tables already created by Express (chats, messages, files) are untouched.
        await conn.run_sync(Base.metadata.create_all)

        # Additive column migrations for shared Express tables.
        # SQLite raises OperationalError if the column already exists; we swallow it.
        new_cols: list[str] = [
            "ALTER TABLE messages ADD COLUMN mode TEXT",
            "ALTER TABLE messages ADD COLUMN input_tokens INTEGER",
            "ALTER TABLE messages ADD COLUMN output_tokens INTEGER",
            "ALTER TABLE files ADD COLUMN row_count INTEGER",
            "ALTER TABLE files ADD COLUMN column_count INTEGER",
            "ALTER TABLE files ADD COLUMN schema_json TEXT",
            "ALTER TABLE files ADD COLUMN preview_json TEXT",
        ]
        for stmt in new_cols:
            try:
                await conn.execute(text(stmt))
                logger.info("Migration applied: %s", stmt)
            except Exception:
                pass  # column already exists

        # Ensure WAL mode and FK enforcement, matching Express pragmas.
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))

    logger.info("Database ready: %s", _settings.database_url)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
