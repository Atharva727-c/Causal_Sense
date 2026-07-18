"""Attaches market-research context to already-computed insights.

Enrichment is annotation, never mutation of the statistics: an insight's
numbers, gates, and ordering are decided entirely by the data. This module
only adds a `market_context` list (relevant external findings, with sources)
so the narrative "charges vary by smoker status" can be shown next to
"smoking is a permitted premium-rating factor" — context, not evidence.
"""
from __future__ import annotations

from typing import Any, Iterable

from insight_builder.context.market import MarketContext

MAX_FINDINGS_PER_INSIGHT = 2


def _insight_columns(insight: dict[str, Any]) -> set[str]:
    columns = insight.get("columns") or {}
    out: set[str] = set()
    for value in columns.values():
        if isinstance(value, str):
            out.add(value)
        elif isinstance(value, (list, tuple)):
            out.update(v for v in value if isinstance(v, str))
    return out


def attach_market_context(insights: Iterable[dict[str, Any]], context: MarketContext) -> int:
    """Annotate each insight in place with up to MAX_FINDINGS_PER_INSIGHT
    findings whose text mentions one of the insight's columns. Returns how
    many insights received at least one annotation."""
    enriched = 0
    for insight in insights:
        cols = _insight_columns(insight)
        if not cols:
            continue
        matches = []
        for finding in context.findings:
            overlap = cols & finding.matched_columns
            if overlap:
                matches.append((len(overlap), finding))
        if not matches:
            continue
        matches.sort(key=lambda m: -m[0])
        insight["market_context"] = [
            finding.as_context() for _, finding in matches[:MAX_FINDINGS_PER_INSIGHT]
        ]
        enriched += 1
    return enriched
