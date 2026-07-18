"""
CausalSense EDA pipeline
========================

A turn-based, DIAL-powered exploratory-data-analysis flow that lives *alongside*
the existing Anthropic agents (they are untouched).

Turn 1 (``run_initial_eda``)
    1. Execute ``tools/explore_dataset.py`` on the uploaded dataset (checklist
       steps 1-6) → an executed Jupyter notebook + plots + profile.
    2. Parse the notebook into structured cells (code / text / images).
    3. Ask the vision LLM to reason over every cell + plot, then carry out
       checklist steps 7-10 (solve-manually, transforms, extra data, learnings).
    4. Persist a concise **facts file** (always in LLM context) and a transient
       **detailed file** that is chunked (with per-cell metadata) into a Chroma
       vector store, then deleted.
    5. Return a polished user response + 5 suggested follow-up questions.

Turn N (``answer_followup``)
    A LangGraph ReAct agent answers with the facts file in context plus two
    tools: ``retrieve_context`` (top-k hybrid chunks) and ``fetch_cell``
    (raw code + output for a notebook cell referenced by a retrieved chunk).

Public entry points live in :mod:`app.services.eda_pipeline.pipeline`.
"""
from __future__ import annotations

from app.services.eda_pipeline.pipeline import answer_followup, run_initial_eda

__all__ = ["run_initial_eda", "answer_followup"]
