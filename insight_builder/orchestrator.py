"""Ties ingestion -> hypothesis generation -> triage -> Tier A execution -> validation -> narration.

Nothing in this file references a specific dataset's column names — it only
ever looks at the roles produced by schema inference.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from insight_builder.domain.knowledge_agent import get_domain_hypotheses
from insight_builder.domain.schema_mapper import map_domain_hypotheses
from insight_builder.execution.renderer import render_script
from insight_builder.execution.runner import run_script
from insight_builder.hypotheses.generator import generate_candidates
from insight_builder.hypotheses.triage import screen_candidates
from insight_builder.ingestion.schema import coerced_dataframe, infer_schema
from insight_builder.kpi_ranking import rank_business_kpis
from insight_builder.narration.narrator import narrate, narrate_no_trend
from insight_builder.validation.gates import apply_gates


def _dedupe_preferring_labeled(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generic and domain hypothesis generation can propose the same test on the
    same columns; keep one, preferring the domain-labeled version since it
    carries a human-readable KPI/hypothesis name."""
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for cand in candidates:
        key = (cand["type"], tuple(sorted(cand["columns"].items())))
        existing = by_key.get(key)
        if existing is None or (existing.get("label") is None and cand.get("label") is not None):
            by_key[key] = cand
    return list(by_key.values())


def run_pipeline(csv_path: str, domain: str | None = None, audit_dir: str | None = None) -> dict[str, Any]:
    raw_df = pd.read_csv(csv_path)
    schema = infer_schema(raw_df)
    clean_df = coerced_dataframe(raw_df, schema)

    candidates = generate_candidates(schema, clean_df)

    domain_hypotheses = []
    if domain:
        abstract_hypotheses = get_domain_hypotheses(domain)
        domain_hypotheses = map_domain_hypotheses(abstract_hypotheses, schema)
        candidates = _dedupe_preferring_labeled(candidates + domain_hypotheses)

    survivors = screen_candidates(clean_df, candidates)

    audit_path = Path(audit_dir) if audit_dir else Path(tempfile.mkdtemp(prefix="insight_audit_"))
    audit_path.mkdir(parents=True, exist_ok=True)

    coerced_csv_path = audit_path / "coerced_dataset.csv"
    datetime_cols = [n for n, p in schema.items() if p.role == "datetime"]
    to_write = clean_df.copy()
    for c in datetime_cols:
        to_write[c] = to_write[c].dt.strftime("%Y-%m-%d")
    to_write.to_csv(coerced_csv_path, index=False)

    raw_results = []
    for candidate in survivors:
        script_text = render_script(candidate, str(coerced_csv_path))
        result = run_script(script_text, audit_path / "scripts")
        result["type"] = candidate["type"]
        result["source"] = candidate["source"]
        result["label"] = candidate.get("label")
        raw_results.append(result)

    # KPI/ratio/top-N/cross-drill-down facts are reported numbers, not discovered
    # hypotheses — they carry no p-value and skip the significance/effect-size/BH gates.
    FACT_TYPES = {"ratio", "top_n", "cross_top_n", "concentration"}
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

    # confidence_tier tells the user how much weight an insight can bear:
    # "business_fact" is true arithmetic (KPI/top-N/concentration) never run
    # through a hypothesis test; "validated" cleared all three statistical
    # gates; "not_significant" was tested and explicitly failed the gates.
    for kpi in kpi_results:
        kpi["confidence_tier"] = "business_fact"
        kpi["narrative"] = f"[Business Fact] {narrate(kpi)}"

    validated = apply_gates(testable_results)
    for insight in validated:
        insight["confidence_tier"] = "validated"
        insight["narrative"] = f"[Validated] {narrate(insight)}"

    # Trend candidates that were actually tested but didn't clear the gates are
    # reported explicitly as "no significant trend" rather than silently dropped,
    # so a flat/noisy time series shows up as a stated finding, not an absence.
    validated_ids = {id(r) for r in validated}
    non_significant_trends = [
        r for r in testable_results
        if r["type"] == "trend" and "error" not in r and id(r) not in validated_ids
    ]
    for r in non_significant_trends:
        r["confidence_tier"] = "not_significant"
        r["narrative"] = f"[Not Significant] {narrate_no_trend(r)}"

    return {
        "schema": {name: profile.role for name, profile in schema.items()},
        "n_rows": len(raw_df),
        "n_candidates_generated": len(candidates),
        "n_domain_hypotheses": len(domain_hypotheses),
        "n_candidates_after_triage": len(survivors),
        "n_executed": len(raw_results),
        "n_validated": len(validated),
        "kpis": kpi_results,
        "top_kpis": rank_business_kpis(kpi_results, top_n=10),
        "insights": validated,
        "non_significant_trends": non_significant_trends,
        "audit_dir": str(audit_path),
    }
