"""Run ``tools/explore_dataset.py`` and parse the executed notebook.

Responsibilities
----------------
* ``ensure_kernel``     — register the current interpreter as the ``python3``
  Jupyter kernel so ``nbclient`` can execute the notebook.
* ``run_explorer``      — invoke the exploration script as a subprocess (it
  generates *and executes* the notebook, embedding plots as PNG outputs).
* ``parse_notebook``    — turn the executed ``.ipynb`` into ``ParsedCell`` objects
  (source + text output + base64 images), addressable by integer index.
* ``build_llm_content`` — assemble an OpenAI-style multimodal ``content`` list
  (interleaved text + ``image_url`` blocks) for the vision model.
* ``get_cell`` / ``render_cell`` — support the ReAct ``fetch_cell`` tool.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)
_s = get_settings()

_MAX_TEXT_PER_CELL = 4000       # truncate huge textual outputs sent to the LLM
_MAX_IMAGES_TO_LLM = 24         # safety cap on images per analysis call


# ══════════════════════════════════════════════════════════════════════════════
# Parsed cell model
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ParsedCell:
    index: int                          # 0-based position in the notebook
    cell_type: str                      # "code" | "markdown"
    source: str
    text_output: str = ""
    images: list[str] = field(default_factory=list)   # base64 PNG (no data-URI prefix)
    had_error: bool = False

    @property
    def is_code(self) -> bool:
        return self.cell_type == "code"

    def summary_header(self) -> str:
        kind = self.cell_type.upper()
        extra = f", {len(self.images)} image(s)" if self.images else ""
        err = ", ERROR" if self.had_error else ""
        return f"Cell {self.index} [{kind}{extra}{err}]"


# ══════════════════════════════════════════════════════════════════════════════
# Kernel registration
# ══════════════════════════════════════════════════════════════════════════════
def ensure_kernel(name: str = "python3") -> bool:
    """Make sure a ``python3`` kernelspec pointing at *this* interpreter exists."""
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        ksm = KernelSpecManager()
        if name in ksm.find_kernel_specs():
            return True
    except Exception:  # jupyter_client not importable yet — fall through to install
        pass
    try:
        from ipykernel import kernelspec

        kernelspec.install(user=True, kernel_name=name, display_name="Python 3 (CausalSense)")
        logger.info("Registered Jupyter kernelspec %r → %s", name, sys.executable)
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not register kernelspec %r: %s", name, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Run the exploration script
# ══════════════════════════════════════════════════════════════════════════════
def run_explorer(
    dataset_path: Path,
    ws: Workspace,
    *,
    target: Optional[str] = None,
    time_col: Optional[str] = None,
    timeout: int = 900,
) -> dict[str, Any]:
    """
    Execute ``explore_dataset.py`` into ``ws.run_dir`` with the notebook run.

    Returns ``{"ok", "notebook", "profile", "stdout", "stderr", "returncode"}``.
    """
    ensure_kernel()
    script = _s.eda_explorer_script
    if not script.exists():
        raise FileNotFoundError(f"Explorer script not found: {script}")

    cmd = [
        sys.executable, str(script), str(dataset_path),
        "--output-dir", str(ws.run_dir),
        "--sample-rows", str(_s.eda_sample_rows),
        "--execute-notebook",
    ]
    if target:
        cmd += ["--target", target]
    if time_col:
        cmd += ["--time-col", time_col]

    logger.info("Running explorer: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        logger.error("Explorer failed (%s): %s", proc.returncode, proc.stderr[-2000:])

    profile: dict[str, Any] = {}
    if ws.profile_path.exists():
        try:
            profile = json.loads(ws.profile_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Could not parse profile.json")

    return {
        "ok": proc.returncode == 0 and ws.notebook_path.exists(),
        "notebook": ws.notebook_path if ws.notebook_path.exists() else None,
        "profile": profile,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "returncode": proc.returncode,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Parse notebook → cells
# ══════════════════════════════════════════════════════════════════════════════
def _join(src: Any) -> str:
    return "".join(src) if isinstance(src, list) else (src or "")


def _extract_outputs(outputs: list[dict]) -> tuple[str, list[str], bool]:
    """Return (text_output, images_b64, had_error) from a code cell's outputs."""
    texts: list[str] = []
    images: list[str] = []
    had_error = False
    for out in outputs or []:
        otype = out.get("output_type")
        if otype == "stream":
            texts.append(_join(out.get("text")))
        elif otype in ("execute_result", "display_data"):
            data = out.get("data", {})
            if "image/png" in data:
                img = data["image/png"]
                images.append(img if isinstance(img, str) else "".join(img))
            if "text/plain" in data:
                texts.append(_join(data["text/plain"]))
        elif otype == "error":
            had_error = True
            texts.append(f"{out.get('ename')}: {out.get('evalue')}")
    text = "\n".join(t for t in texts if t).strip()
    if len(text) > _MAX_TEXT_PER_CELL:
        text = text[:_MAX_TEXT_PER_CELL] + "\n… [truncated]"
    return text, images, had_error


def parse_notebook(nb_path: Path) -> list[ParsedCell]:
    """Load an executed notebook and return structured, index-addressable cells."""
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    cells: list[ParsedCell] = []
    for i, cell in enumerate(nb.get("cells", [])):
        ctype = cell.get("cell_type", "code")
        source = _join(cell.get("source"))
        if ctype == "code":
            text, images, err = _extract_outputs(cell.get("outputs", []))
            cells.append(ParsedCell(i, ctype, source, text, images, err))
        else:
            cells.append(ParsedCell(i, ctype, source))
    return cells


# ══════════════════════════════════════════════════════════════════════════════
# Cell lookup (fetch_cell tool)
# ══════════════════════════════════════════════════════════════════════════════
def get_cell(cells: list[ParsedCell], index: int) -> Optional[ParsedCell]:
    for c in cells:
        if c.index == index:
            return c
    return None


def render_cell(cell: ParsedCell, *, include_images: bool = False) -> str:
    """Human/LLM-readable text rendering of one cell (for the fetch_cell tool)."""
    parts = [f"=== {cell.summary_header()} ==="]
    if cell.source.strip():
        lang = "python" if cell.is_code else "markdown"
        parts.append(f"```{lang}\n{cell.source.strip()}\n```")
    if cell.text_output:
        parts.append(f"Output:\n{cell.text_output}")
    if cell.images:
        note = f"[{len(cell.images)} image output(s) available]"
        parts.append(note)
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Multimodal content for the vision LLM
# ══════════════════════════════════════════════════════════════════════════════
def build_llm_content(
    cells: list[ParsedCell],
    *,
    send_images: bool = True,
    max_images: int = _MAX_IMAGES_TO_LLM,
) -> list[dict[str, Any]]:
    """
    Build an OpenAI-style multimodal ``content`` list: interleaved ``text`` and
    ``image_url`` blocks, one logical section per notebook cell.  Every block is
    prefixed with ``Cell {index}`` so the model can cite cells by number and we
    can round-trip those citations into chunk metadata.
    """
    content: list[dict[str, Any]] = []
    img_budget = max_images
    for cell in cells:
        header = cell.summary_header()
        text_block = [header]
        if cell.source.strip():
            lang = "python" if cell.is_code else "markdown"
            text_block.append(f"```{lang}\n{cell.source.strip()}\n```")
        if cell.text_output:
            text_block.append(f"Output:\n{cell.text_output}")
        content.append({"type": "text", "text": "\n".join(text_block)})

        if send_images and cell.images and img_budget > 0:
            for img in cell.images:
                if img_budget <= 0:
                    break
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img}"},
                })
                img_budget -= 1
    return content


def cells_as_text(cells: list[ParsedCell]) -> str:
    """Plain-text fallback rendering of all cells (used when images are off)."""
    return "\n\n".join(render_cell(c) for c in cells)
