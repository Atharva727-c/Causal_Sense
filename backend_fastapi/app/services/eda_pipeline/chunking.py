"""Chunk the transient *detailed* writeup into metadata-rich vector-store chunks.

The LLM writes the detailed file as marker-delimited blocks so cell numbers and
section labels round-trip into chunk metadata deterministically (no fragile
prose parsing). Marker syntax, one per line, immediately before its block::

    [[CELL=5 | SECTION=Univariate Analysis | KIND=cell]]
    ...prose about notebook cell 5...

    [[SECTION=Promising Transformations | KIND=step8]]
    ...prose for checklist step 8 (no specific cell)...

Recognised keys: ``CELL`` (int), ``SECTION`` (str), ``KIND`` (str). Anything
before the first marker becomes an ``overview`` block. Each block is then split
into overlapping, size-bounded chunks; metadata is attached to every chunk.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_MARKER = re.compile(r"^\s*\[\[(.+?)\]\]\s*$", re.MULTILINE)


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# Marker parsing
# ══════════════════════════════════════════════════════════════════════════════
def _parse_marker(raw: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for part in raw.split("|"):
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        key, val = key.strip().upper(), val.strip()
        if key == "CELL":
            try:
                meta["cell_index"] = int(re.sub(r"\D", "", val))
            except ValueError:
                pass
        elif key == "SECTION":
            meta["section"] = val
        elif key == "KIND":
            meta["kind"] = val
    return meta


def _split_blocks(text: str) -> list[tuple[dict[str, Any], str]]:
    """Split marker-delimited text into (metadata, content) blocks."""
    markers = list(_MARKER.finditer(text))
    if not markers:
        return [({"section": "overview", "kind": "overview"}, text.strip())] if text.strip() else []

    blocks: list[tuple[dict[str, Any], str]] = []
    # Preamble before the first marker.
    pre = text[: markers[0].start()].strip()
    if pre:
        blocks.append(({"section": "overview", "kind": "overview"}, pre))

    for i, m in enumerate(markers):
        meta = _parse_marker(m.group(1))
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        content = text[start:end].strip()
        if content:
            blocks.append((meta, content))
    return blocks


# ══════════════════════════════════════════════════════════════════════════════
# Size-bounded splitting (paragraph-aware, deterministic, dependency-free)
# ══════════════════════════════════════════════════════════════════════════════
def split_text(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}".strip()
            continue
        if buf:
            chunks.append(buf)
        if len(para) <= size:
            buf = para
        else:  # a single oversized paragraph — hard-split with overlap
            step = max(size - overlap, 1)
            for i in range(0, len(para), step):
                chunks.append(para[i : i + size])
            buf = ""
    if buf:
        chunks.append(buf)

    # Prepend a short overlap tail from the previous chunk for continuity.
    if overlap > 0 and len(chunks) > 1:
        stitched = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            tail = prev[-overlap:]
            stitched.append(f"{tail}\n{cur}" if not cur.startswith(tail) else cur)
        chunks = stitched
    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════
def chunk_detailed(
    text: str,
    *,
    session_id: str,
    source: str = "turn1",
    size: int = 1200,
    overlap: int = 150,
) -> list[Chunk]:
    """Parse markers, split each block, and emit metadata-tagged chunks."""
    chunks: list[Chunk] = []
    for meta, content in _split_blocks(text):
        base = {
            "session_id": session_id,
            "source": source,
            "section": meta.get("section", "general"),
            "kind": meta.get("kind", "note"),
            "cell_index": int(meta.get("cell_index", -1)),  # Chroma needs a concrete value
        }
        for piece in split_text(content, size, overlap):
            piece = piece.strip()
            if not piece:
                continue
            idx = len(chunks)
            digest = hashlib.md5(f"{session_id}:{source}:{idx}:{piece[:80]}".encode()).hexdigest()[:16]
            chunks.append(Chunk(
                id=f"{source}-{idx}-{digest}",
                text=piece,
                metadata={**base, "chunk_index": idx},
            ))
    return chunks
