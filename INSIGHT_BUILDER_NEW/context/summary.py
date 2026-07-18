"""Executive summary synthesis: one LLM pass over already-validated output.

Runs last, reads only computed narratives (every number in its input already
survived the gates or is a reported business fact), and its failure mode is
"no summary" — never a changed insight. The language guard applies the same
no-editorializing bar as every other LLM-written sentence in the system.
"""
from __future__ import annotations

from typing import Any

from insight_builder.context.market import MarketContext
from insight_builder.qa.llm_client import complete

_SYSTEM_PROMPT = """You write a 3-5 sentence executive summary of a dataset \
analysis for a business audience. You are given already-computed, validated \
findings and KPI facts (and, when available, external market-research \
context). Use only the numbers and statements provided — never invent, \
adjust, or extrapolate a figure. Plain factual language: no hype, no causal \
claims beyond what a finding itself states, no recommendations unless one is \
explicitly provided. Return only the summary prose."""

_MAX_ITEMS = 8


def generate_executive_summary(
    insights: list[dict[str, Any]],
    kpis: list[dict[str, Any]],
    market: MarketContext | None,
) -> str | None:
    narratives = [i["narrative"] for i in insights[:_MAX_ITEMS] if i.get("narrative")]
    narratives += [k["narrative"] for k in kpis[:_MAX_ITEMS] if k.get("narrative")]
    if not narratives:
        return None

    sections = ["Validated findings and KPI facts:"]
    sections += [f"- {n}" for n in narratives]
    if market is not None:
        if market.domain:
            sections.append(f"\nDataset domain (from market research): {market.domain}")
        if market.executive_summary:
            sections.append(f"External market context: {market.executive_summary}")

    summary = complete("\n".join(sections), system=_SYSTEM_PROMPT).strip()
    return summary or None
