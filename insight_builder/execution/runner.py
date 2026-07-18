"""Runs a rendered Tier A script in a subprocess and captures its single JSON stdout line.

Every script is persisted to disk before execution so the run is fully auditable.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

SCRIPT_TIMEOUT_SECONDS = 15


def run_script(script_text: str, audit_dir: Path) -> dict[str, Any]:
    audit_dir.mkdir(parents=True, exist_ok=True)
    script_path = audit_dir / f"{uuid.uuid4().hex}.py"
    script_path.write_text(script_text, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "script_path": str(script_path)}

    if proc.returncode != 0:
        return {"error": "execution_failed", "stderr": proc.stderr[-2000:], "script_path": str(script_path)}

    last_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        result = json.loads(last_line)
    except json.JSONDecodeError:
        return {"error": "bad_output", "stdout": proc.stdout[-2000:], "script_path": str(script_path)}

    result["script_path"] = str(script_path)
    return result
