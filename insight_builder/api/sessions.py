"""In-memory session store mapping a session_id to its own scratch directory.

Every uploaded dataset lives only inside its session's directory, and that
directory is only ever removed by an explicit delete_session() call (from the
DELETE /datasets/{id} endpoint) -- nothing here auto-expires yet. A caller
that never deletes its session will leak disk space just like run_pipeline's
own default tempfile.mkdtemp() behavior; production use of this API should
add a TTL-based reaper, but the API always tracks and can clean up what it
created, which the bare library call does not.
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_SESSIONS_ROOT = Path(tempfile.mkdtemp(prefix="insight_api_sessions_"))


@dataclass
class Session:
    session_id: str
    dir: Path
    csv_path: Path
    filename: str
    domain: str | None = None
    audit_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.audit_dir = self.dir / "audit"


_SESSIONS: dict[str, Session] = {}


def create_session(filename: str, content: bytes) -> Session:
    session_id = uuid.uuid4().hex
    session_dir = _SESSIONS_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    csv_path = session_dir / "dataset.csv"
    csv_path.write_bytes(content)

    session = Session(session_id=session_id, dir=session_dir, csv_path=csv_path, filename=filename)
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
