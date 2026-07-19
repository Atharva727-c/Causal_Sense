"""The insight pipeline as an explicit state graph.

Ingestion -> candidate generation (generic + optional domain-LLM + optional
market-research DAG) -> triage -> sandboxed parallel execution -> statistical
gates -> narration -> optional market enrichment -> ranking -> report.

Control flow is deterministic and data-driven (see graph/engine.py for why
this is a workflow graph and not an LLM tool loop). The two external
capabilities — the LLM endpoint and the Market Researcher artifact — are
conditional, error-isolated nodes: when either is absent or failing, the
pipeline still produces the full deterministic report.

Nothing in this file references a specific dataset's column names — it only
ever looks at the roles produced by schema inference.
"""
from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from insight_builder.context.dag_hypotheses import derive_dag_candidates
from insight_builder.context.enricher import attach_market_context
from insight_builder.context.market import load_market_context, resolve_artifact_path
from insight_builder.context.summary import generate_executive_summary
from insight_builder.domain.knowledge_agent import get_domain_hypotheses
from insight_builder.domain.schema_mapper import map_domain_hypotheses
from insight_builder.execution.renderer import render_script
from insight_builder.execution.runner import run_script
from insight_builder.graph.engine import StateGraph
from insight_builder.hypotheses.generator import generate_candidates
from insight_builder.hypotheses.triage import screen_candidates
from insight_builder.ingestion.loader import load_dataset, write_coerced_csv
from insight_builder.ingestion.schema import coerced_dataframe, infer_schema
from insight_builder.kpi_ranking import rank_business_kpis
from insight_builder.narration.narrator import narrate, narrate_not_significant, narrate_test_failed
from insight_builder.qa.llm_client import llm_available
from insight_builder.validation.gates import apply_gates

MAX_EXECUTION_WORKERS = 8

# Candidate keys carried through onto the executed result so provenance and
# market-research annotations survive into the report.
_CANDIDATE_METADATA_KEYS = ("type", "source", "label", "market_rationale", "market_confidence")

# KPI/ratio/top-N/cross-drill-down facts are reported numbers, not discovered
# hypotheses — they carry no p-value and skip the significance/effect-size/BH gates.
FACT_TYPES = {"ratio", "top_n", "cross_top_n", "concentration"}


def _dedupe_preferring_labeled(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generic, domain, and market-DAG generation can propose the same test on
    the same columns; keep one, preferring a labeled version since it carries
    a human-readable KPI/hypothesis name (and market rationale)."""
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for cand in candidates:
        key = (cand["type"], tuple(sorted(cand["columns"].items())))
        existing = by_key.get(key)
        if existing is None or (existing.get("label") is None and cand.get("label") is not None):
            by_key[key] = cand
    return list(by_key.values())


# --- graph nodes: each is state -> dict of state updates ------------------

def _node_load_dataset(state: dict[str, Any]) -> dict[str, Any]:
    return {"raw_df": load_dataset(state["dataset_path"])}


def _node_infer_schema(state: dict[str, Any]) -> dict[str, Any]:
    schema = infer_schema(state["raw_df"])
    return {"schema": schema, "clean_df": coerced_dataframe(state["raw_df"], schema)}


def _node_persist_coerced(state: dict[str, Any]) -> dict[str, Any]:
    path = write_coerced_csv(state["clean_df"], state["schema"], state["audit_path"])
    return {"coerced_csv_path": path}


def _node_load_market_context(state: dict[str, Any]) -> dict[str, Any]:
    columns = list(state["schema"])
    market = load_market_context(state["market_artifact_path"], column_names=columns)
    if market is None:
        return {"market": None, "market_load_error": "artifact present but unreadable/invalid"}
    if not market.matches_dataset(columns):
        # A stale/mismatched artifact would inject another dataset's domain,
        # findings, and DAG into this analysis — ignore it, loudly.
        return {"market": None, "market_load_error": "artifact describes a different dataset (no column overlap)"}
    return {"market": market}


def _node_generic_candidates(state: dict[str, Any]) -> dict[str, Any]:
    return {"generic_candidates": generate_candidates(state["schema"], state["clean_df"])}


def _effective_domain(state: dict[str, Any]) -> str | None:
    """User-supplied domain wins; otherwise the Market Researcher's detected
    domain fills in, so its artifact upgrades an un-annotated upload to a
    domain-aware analysis for free."""
    if state.get("domain"):
        return state["domain"]
    market = state.get("market")
    return market.domain if market is not None else None


def _node_domain_candidates(state: dict[str, Any]) -> dict[str, Any]:
    abstract = get_domain_hypotheses(_effective_domain(state))
    return {"domain_candidates": map_domain_hypotheses(abstract, state["schema"])}


def _node_dag_candidates(state: dict[str, Any]) -> dict[str, Any]:
    return {"dag_candidates": derive_dag_candidates(state["market"], state["schema"])}


def _node_merge_candidates(state: dict[str, Any]) -> dict[str, Any]:
    merged = _dedupe_preferring_labeled(
        state["generic_candidates"]
        + state.get("domain_candidates", [])
        + state.get("dag_candidates", [])
    )
    return {"candidates": merged}


def _node_triage(state: dict[str, Any]) -> dict[str, Any]:
    return {"survivors": screen_candidates(state["clean_df"], state["candidates"])}


def _node_execute(state: dict[str, Any]) -> dict[str, Any]:
    """Each surviving candidate runs as its own sandboxed subprocess; they are
    independent, so run them on a thread pool (the work is subprocess-bound,
    not GIL-bound). Result order matches candidate order."""
    coerced_csv_path = str(state["coerced_csv_path"])
    scripts_dir = state["audit_path"] / "scripts"

    def _run_one(candidate: dict[str, Any]) -> dict[str, Any]:
        script_text = render_script(candidate, coerced_csv_path)
        result = run_script(script_text, scripts_dir)
        for key in _CANDIDATE_METADATA_KEYS:
            if candidate.get(key) is not None or key == "type":
                result[key] = candidate.get(key)
        return result

    survivors = state["survivors"]
    workers = min(MAX_EXECUTION_WORKERS, max(1, len(survivors)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        raw_results = list(pool.map(_run_one, survivors))
    return {"raw_results": raw_results}


def _node_partition_results(state: dict[str, Any]) -> dict[str, Any]:
    raw_results = state["raw_results"]
    kpi_results = [
        r for r in raw_results
        if r["type"] in FACT_TYPES and r["type"] != "cross_top_n" and "error" not in r
    ]
    testable_results = [r for r in raw_results if r["type"] not in FACT_TYPES]

    # cross_top_n bundles every numeric column into one script run (to avoid a
    # subprocess per numeric column); unbundle it here into one narratable KPI
    # per numeric column.
    for r in raw_results:
        if r["type"] != "cross_top_n" or "error" in r:
            continue
        for numeric_col, group_top in r.get("by_numeric", {}).items():
            if not group_top:
                continue
            kpi_results.append({
                "test": "cross_top_n",
                "type": "cross_top_n",
                "source": r["source"],
                "label": r.get("label"),
                "n": r["n"],
                "columns": {**r["columns"], "numeric_col": numeric_col},
                "group_top": group_top,
                "outliers_removed": {numeric_col: r.get("outliers_removed", {}).get(numeric_col, 0)},
            })
    return {"kpi_results": kpi_results, "testable_results": testable_results}


def _node_validate(state: dict[str, Any]) -> dict[str, Any]:
    testable_results = state["testable_results"]
    validated = apply_gates(testable_results)

    # Every testable candidate is accounted for in the report: it either clears
    # all three gates (validated), ran cleanly but didn't clear them
    # (not_significant), or its script never produced a usable result at all —
    # e.g. a subprocess timeout or crash (failed_tests). None are silently
    # dropped, unlike the earlier trend-only version of this bucket.
    validated_ids = {id(r) for r in validated}
    not_significant = [
        r for r in testable_results
        if "error" not in r and id(r) not in validated_ids
    ]
    failed_tests = [r for r in testable_results if "error" in r]
    return {"validated": validated, "not_significant": not_significant, "failed_tests": failed_tests}


def _node_narrate(state: dict[str, Any]) -> dict[str, Any]:
    # confidence_tier tells the user how much weight an insight can bear:
    # "business_fact" is true arithmetic (KPI/top-N/concentration) never run
    # through a hypothesis test; "validated" cleared all three statistical
    # gates; "not_significant" was tested and explicitly failed the gates;
    # "test_failed" never produced a result to gate on in the first place.
    for kpi in state["kpi_results"]:
        kpi["confidence_tier"] = "business_fact"
        kpi["narrative"] = f"[Business Fact] {narrate(kpi)}"
    for insight in state["validated"]:
        insight["confidence_tier"] = "validated"
        insight["narrative"] = f"[Validated] {narrate(insight)}"
    for r in state["not_significant"]:
        r["confidence_tier"] = "not_significant"
        r["narrative"] = f"[Not Significant] {narrate_not_significant(r)}"
    for r in state["failed_tests"]:
        r["confidence_tier"] = "test_failed"
        r["narrative"] = f"[Test Failed] {narrate_test_failed(r)}"
    return {}


def _node_enrich(state: dict[str, Any]) -> dict[str, Any]:
    market = state["market"]
    enriched = attach_market_context(
        state["validated"] + state["kpi_results"] + state["not_significant"], market
    )
    return {"n_enriched": enriched}


def _node_rank_kpis(state: dict[str, Any]) -> dict[str, Any]:
    return {"top_kpis": rank_business_kpis(state["kpi_results"], top_n=10)}


# Validated insights already come out of apply_gates() sorted by rank_score
# (highest first), so "top" is just the first slice -- no separate ranking
# function needed the way KPIs need one (KPI facts have no single comparable
# score across their differently-shaped types).
TOP_INSIGHTS_COUNT = 10


def _node_top_insights(state: dict[str, Any]) -> dict[str, Any]:
    return {"top_insights": state["validated"][:TOP_INSIGHTS_COUNT]}


def _node_executive_summary(state: dict[str, Any]) -> dict[str, Any]:
    summary = generate_executive_summary(
        state["validated"], state["top_kpis"], state.get("market")
    )
    return {"executive_summary": summary}


def _node_assemble_report(state: dict[str, Any]) -> dict[str, Any]:
    market = state.get("market")
    if market is not None:
        market_section = market.summary_for_report()
        market_section["n_insights_enriched"] = state.get("n_enriched", 0)
    else:
        market_section = {"available": False}
        if state.get("market_load_error"):
            market_section["reason"] = state["market_load_error"]

    return {"report": {
        "schema": {name: profile.role for name, profile in state["schema"].items()},
        "n_rows": len(state["raw_df"]),
        "domain": _effective_domain(state),
        "n_candidates_generated": len(state["candidates"]),
        "n_domain_hypotheses": len(state.get("domain_candidates", [])),
        "n_market_dag_hypotheses": len(state.get("dag_candidates", [])),
        "n_candidates_after_triage": len(state["survivors"]),
        "n_executed": len(state["raw_results"]),
        "n_validated": len(state["validated"]),
        "n_failed_tests": len(state["failed_tests"]),
        "kpis": state["kpi_results"],
        "top_kpis": state["top_kpis"],
        "insights": state["validated"],
        "top_insights": state["top_insights"],
        "not_significant": state["not_significant"],
        "failed_tests": state["failed_tests"],
        "executive_summary": state.get("executive_summary"),
        "market_research": market_section,
        "audit_dir": str(state["audit_path"]),
    }}


# --- graph assembly --------------------------------------------------------

def _market_artifact_present(state: dict[str, Any]) -> bool:
    return state.get("market_artifact_path") is not None


def _market_loaded(state: dict[str, Any]) -> bool:
    return state.get("market") is not None


def _domain_llm_ready(state: dict[str, Any]) -> bool:
    return _effective_domain(state) is not None and llm_available()


def build_insight_graph() -> StateGraph:
    graph = StateGraph(name="insight_pipeline")
    graph.add_node("load_dataset", _node_load_dataset)
    graph.add_node("infer_schema", _node_infer_schema, after=["load_dataset"])
    graph.add_node("persist_coerced", _node_persist_coerced, after=["infer_schema"])
    graph.add_node(
        "load_market_context", _node_load_market_context, after=["infer_schema"],
        condition=_market_artifact_present, condition_label="no market-research artifact",
        optional=True,
    )
    graph.add_node("generic_candidates", _node_generic_candidates, after=["infer_schema"])
    graph.add_node(
        "domain_candidates", _node_domain_candidates, after=["infer_schema", "load_market_context"],
        condition=_domain_llm_ready, condition_label="no domain given/detected, or LLM not configured",
        optional=True,
    )
    graph.add_node(
        "dag_candidates", _node_dag_candidates, after=["load_market_context"],
        condition=lambda s: _market_loaded(s) and s["market"].has_dag,
        condition_label="no market-research causal DAG",
        optional=True,
    )
    graph.add_node(
        "merge_candidates", _node_merge_candidates,
        after=["generic_candidates", "domain_candidates", "dag_candidates"],
    )
    graph.add_node("triage", _node_triage, after=["merge_candidates"])
    graph.add_node("execute", _node_execute, after=["triage", "persist_coerced"])
    graph.add_node("partition_results", _node_partition_results, after=["execute"])
    graph.add_node("validate", _node_validate, after=["partition_results"])
    graph.add_node("narrate", _node_narrate, after=["validate"])
    graph.add_node(
        "enrich_with_market", _node_enrich, after=["narrate"],
        condition=_market_loaded, condition_label="no market context loaded",
        optional=True,
    )
    graph.add_node("rank_kpis", _node_rank_kpis, after=["narrate"])
    graph.add_node("top_insights", _node_top_insights, after=["narrate"])
    graph.add_node(
        "executive_summary", _node_executive_summary, after=["rank_kpis", "enrich_with_market"],
        condition=lambda s: llm_available(), condition_label="LLM not configured",
        optional=True,
    )
    graph.add_node(
        "assemble_report", _node_assemble_report,
        after=["executive_summary", "rank_kpis", "top_insights"],
    )
    return graph


def run_pipeline(
    dataset_path: str,
    domain: str | None = None,
    audit_dir: str | None = None,
    market_research_path: str | None = None,
) -> dict[str, Any]:
    """Full analysis of one uploaded dataset (CSV or Excel).

    market_research_path points at a Market Researcher output.json; when None,
    the artifact is auto-discovered via the INSIGHT_MARKET_RESEARCH_PATH env
    var or an output.json sitting next to the dataset. A missing or invalid
    artifact never fails the run — the report just carries no market section.
    """
    audit_path = Path(audit_dir) if audit_dir else Path(tempfile.mkdtemp(prefix="insight_audit_"))
    audit_path.mkdir(parents=True, exist_ok=True)

    artifact = resolve_artifact_path(dataset_path, market_research_path)
    state: dict[str, Any] = {
        "dataset_path": dataset_path,
        "domain": domain,
        "audit_path": audit_path,
        "market_artifact_path": artifact,
    }

    graph = build_insight_graph()
    final_state, traces = graph.run(state)

    report = final_state["report"]
    report["graph_trace"] = [t.as_dict() for t in traces]
    return report
