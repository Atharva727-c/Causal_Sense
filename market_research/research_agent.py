"""Orchestrates the market research step: plans web search queries appropriate
to the dataset's mode (time-bounded vs column-context), runs them, and
synthesizes the results into a structured MarketResearchReport via the LLM."""

from __future__ import annotations

from datetime import date

from .llm_client import chat_json
from .models import DataProfile, KeyFinding, MarketResearchReport, Recommendation, SourceRef
from .search_client import search_many

_MAX_SOURCES_FOR_SYNTHESIS = 20
_SNIPPET_MAX_CHARS = 350


def _mode_for(profile: DataProfile) -> str:
    return "time_bounded" if profile.timeline.has_timeline else "column_context"


_QUERY_PLANNER_SYSTEM_PROMPT = (
    "You are a market research analyst planning targeted web searches to understand the "
    "market context behind a dataset. Produce specific, high-signal search queries -- not "
    "generic ones."
)


def plan_research_queries(profile: DataProfile, mode: str) -> list[str]:
    key_columns = "\n".join(
        f"- {c.name} ({c.role}): {c.sample_values[:3]}"
        for c in profile.columns
        if c.role in ("categorical", "numeric")
    )
    if mode == "time_bounded":
        timeline_instruction = (
            f"The dataset covers the date range {profile.timeline.start_date} to "
            f"{profile.timeline.end_date}. Every query MUST include that specific year range "
            "(or the specific years within it) so results are grounded in that window, e.g. "
            "market trends, demand shifts, cost/pricing pressures, competitive or regulatory "
            "events during those years. Today's date is "
            f"{date.today().isoformat()}, so this window may be historical -- frame queries to "
            "find retrospective/historical market context, not current news."
        )
    else:
        timeline_instruction = (
            "The dataset has no reliable date range. Do NOT include specific years in the "
            "queries. Focus on the general/current market structure, industry sizing, "
            "competitive landscape, and customer segment context implied by the dataset's "
            "columns and domain."
        )

    prompt = (
        f"Dataset domain: {profile.domain}\n"
        f"Dataset description: {profile.description}\n\n"
        f"Key columns:\n{key_columns}\n\n"
        f"{timeline_instruction}\n\n"
        "Return JSON: {\"queries\": [list of 4 to 6 distinct search query strings]}"
    )
    result = chat_json(_QUERY_PLANNER_SYSTEM_PROMPT, prompt)
    queries = result.get("queries", [])
    return [q for q in queries if isinstance(q, str) and q.strip()][:6]


def run_searches(queries: list[str]) -> list[dict]:
    return search_many(queries, max_results_per_query=4)


_SYNTHESIS_SYSTEM_PROMPT = (
    "You are a senior market research analyst. You are given a dataset profile and a batch of "
    "raw web search results. Synthesize them into a structured market research report. Ground "
    "every key finding in the provided sources (cite them by index). Be concrete and specific to "
    "this dataset's domain -- avoid generic filler."
)


def synthesize_report(profile: DataProfile, mode: str, sources: list[dict]) -> MarketResearchReport:
    numbered_sources = [s for s in sources if s.get("url")][:_MAX_SOURCES_FOR_SYNTHESIS]
    sources_block = "\n".join(
        f"[{i}] {s.get('title', '')} ({s.get('url', '')})\n"
        f"    {(s.get('content') or '')[:_SNIPPET_MAX_CHARS]}"
        for i, s in enumerate(numbered_sources)
    ) or "(no web search results were available)"

    timeline_note = (
        f"Dataset date range: {profile.timeline.start_date} to {profile.timeline.end_date}."
        if profile.timeline.has_timeline
        else "Dataset has no date range; research is general/current market context, not time-bound."
    )

    prompt = (
        f"Dataset domain: {profile.domain}\n"
        f"Dataset description: {profile.description}\n"
        f"{timeline_note}\n\n"
        f"Web search sources:\n{sources_block}\n\n"
        "Return JSON matching this shape exactly:\n"
        "{\n"
        '  "executive_summary": "2-4 sentence overview",\n'
        '  "key_findings": [{"title": "...", "detail": "...", "source_indices": [0, 2]}],\n'
        '  "opportunities": ["..."],\n'
        '  "risks": ["..."],\n'
        '  "recommendations": [{"recommendation": "...", "rationale": "...", "priority": "high|medium|low"}]\n'
        "}\n"
        "Include 3-6 key_findings, 2-5 opportunities, 2-5 risks, and 3-6 recommendations. "
        "source_indices must refer to the bracketed numbers above; use an empty list if a "
        "finding is general reasoning rather than sourced from a specific result."
    )
    result = chat_json(_SYNTHESIS_SYSTEM_PROMPT, prompt)

    def _resolve_sources(indices: list[int]) -> list[SourceRef]:
        refs = []
        for i in indices or []:
            if isinstance(i, int) and 0 <= i < len(numbered_sources):
                s = numbered_sources[i]
                refs.append(SourceRef(title=s.get("title", ""), url=s.get("url", ""), snippet=(s.get("content") or "")[:_SNIPPET_MAX_CHARS]))
        return refs

    key_findings = [
        KeyFinding(title=f.get("title", ""), detail=f.get("detail", ""), sources=_resolve_sources(f.get("source_indices", [])))
        for f in result.get("key_findings", [])
    ]
    recommendations = [
        Recommendation(
            recommendation=r.get("recommendation", ""),
            rationale=r.get("rationale", ""),
            priority=r.get("priority", "medium") if r.get("priority") in ("high", "medium", "low") else "medium",
        )
        for r in result.get("recommendations", [])
    ]
    all_sources = [
        SourceRef(title=s.get("title", ""), url=s.get("url", ""), snippet=(s.get("content") or "")[:_SNIPPET_MAX_CHARS])
        for s in numbered_sources
    ]

    return MarketResearchReport(
        mode=mode,
        executive_summary=result.get("executive_summary", ""),
        domain=profile.domain,
        timeline=profile.timeline,
        key_findings=key_findings,
        opportunities=[o for o in result.get("opportunities", []) if isinstance(o, str)],
        risks=[r for r in result.get("risks", []) if isinstance(r, str)],
        recommendations=recommendations,
        sources=all_sources,
    )


def run_market_research(profile: DataProfile) -> MarketResearchReport:
    mode = _mode_for(profile)
    queries = plan_research_queries(profile, mode)
    sources = run_searches(queries)
    return synthesize_report(profile, mode, sources)
