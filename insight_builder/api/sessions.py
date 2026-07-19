"""In-memory session store mapping a session_id to its own scratch directory.

Every uploaded artifact (dataset, optional market-research JSON) lives only
inside its session's directory, and that directory is only ever removed by an
explicit delete_session() call (from the DELETE /datasets/{id} endpoint) --
nothing here auto-expires yet. A caller that never deletes its session will
leak disk space just like run_pipeline's own default tempfile.mkdtemp()
behavior; production use of this API should add a TTL-based reaper, but the
API always tracks and can clean up what it created, which the bare library
call does not.
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from insight_builder.context.market import MarketContext

_SESSIONS_ROOT = Path(tempfile.mkdtemp(prefix="insight_api_sessions_"))


@dataclass
class Session:
    session_id: str
    dir: Path
    dataset_path: Path
    filename: str
    domain: str | None = None
    market_research_path: Path | None = None
    # Loaded once (at analyze time or artifact upload) and reused by /chat so
    # every conversational answer can carry the same market annotations.
    market_context: MarketContext | None = None
    # The full (unranked) business-fact KPI list from the last /analyze call,
    # cached so a later "show me more KPIs" request can re-rank and paginate
    # through the same underlying facts instead of re-running the whole
    # (expensive) candidate pipeline just to look further down the list.
    kpi_cache: list[dict[str, Any]] | None = None
    # The full validated-insights list (already rank_score-sorted) from the
    # last /analyze call, cached so a later "show me more insights" request
    # can page further down the same ordering instead of re-running the
    # pipeline just to look further down the list.
    insights_cache: list[dict[str, Any]] | None = None
    audit_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.audit_dir = self.dir / "audit"


_SESSIONS: dict[str, Session] = {}


def create_session(filename: str, content: bytes) -> Session:
    session_id = uuid.uuid4().hex
    session_dir = _SESSIONS_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = session_dir / f"dataset{Path(filename).suffix.lower()}"
    dataset_path.write_bytes(content)

    session = Session(session_id=session_id, dir=session_dir, dataset_path=dataset_path, filename=filename)
    _SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _SESSIONS.get(session_id)


def delete_session(session_id: str) -> bool:
    session = _SESSIONS.pop(session_id, None)
    if session is None:
        return False
    shutil.rmtree(session.dir, ignore_errors=True)
    return True
