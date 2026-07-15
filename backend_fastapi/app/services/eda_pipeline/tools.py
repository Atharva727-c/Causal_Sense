"""LangChain tools for the ReAct follow-up agent, bound to one session.

* ``retrieve_context(query)`` — top-k hybrid chunks from the session vector
  store, each tagged with the ``cell_index`` it came from.
* ``fetch_cell(cell_index)`` — the exact code + output of a notebook cell, so
  the agent can verify a number or inspect the code behind a retrieved chunk.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.services.eda_pipeline import notebook as nb
from app.services.eda_pipeline.vectorstore import HybridVectorStore
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)
_s = get_settings()


def make_tools(ws: Workspace, store: HybridVectorStore) -> list[Any]:
    from langchain_core.tools import StructuredTool

    def retrieve_context(query: str) -> str:
        """Search the detailed EDA analysis for the most relevant passages.

        Use this to pull specific findings, statistics, or interpretations that
        are not already in the session facts. Returns up to 5 passages, each
        labelled with the notebook cell_index it derives from (pass that to
        fetch_cell to inspect the underlying code + output).

        Args:
            query: A focused natural-language search query.
        """
        hits = store.search(query, k=_s.eda_vector_top_k)
        if not hits:
            return "No relevant passages found in the analysis."
        blocks = []
        for i, h in enumerate(hits, 1):
            m = h["metadata"]
            cell = m.get("cell_index", -1)
            cite = f"cell_index={cell}" if cell is not None and cell >= 0 else "no specific cell"
            blocks.append(
                f"[{i}] (section={m.get('section','?')}, kind={m.get('kind','?')}, {cite})\n{h['text']}"
            )
        return "\n\n".join(blocks)

    def fetch_cell(cell_index: int) -> str:
        """Fetch the exact code and output of one notebook cell by its index.

        Use after retrieve_context surfaces a chunk that cites a cell_index you
        need to inspect precisely (e.g. to confirm a statistic or see the code).

        Args:
            cell_index: The integer cell index shown in retrieved passages.
        """
        if not ws.notebook_path.exists():
            return "The notebook is not available for this session."
        cells = nb.parse_notebook(ws.notebook_path)
        cell = nb.get_cell(cells, int(cell_index))
        if cell is None:
            valid = ", ".join(str(c.index) for c in cells)
            return f"No cell with index {cell_index}. Valid indices: {valid}."
        return nb.render_cell(cell)

    return [
        StructuredTool.from_function(
            retrieve_context,
            name="retrieve_context",
            description="Search the detailed EDA analysis for relevant passages (top-k hybrid retrieval).",
        ),
        StructuredTool.from_function(
            fetch_cell,
            name="fetch_cell",
            description="Fetch exact code + output of a notebook cell by its integer index.",
        ),
    ]
