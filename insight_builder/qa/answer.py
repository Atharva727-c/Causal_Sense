"""Answers one free-text question against a dataset.

Tier A first: intent_parser.py maps the question onto one of the five fixed,
vetted shapes (ratio/group_diff/correlation/trend/chi_square) and it's
executed through the exact same sandboxed templates/gates as the main
pipeline. Tier B (query/ask.py's LLM-generated ad-hoc pandas) only runs when
Tier A genuinely can't express the question, or fails on this data — so a
Tier-A-shaped question is always answered the vetted way when possible.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from insight_builder.context.enricher import attach_market_context
from insight_builder.context.market import MarketContext
from insight_builder.execution.renderer import render_script
from insight_builder.execution.runner import run_script
from insight_builder.ingestion.loader import load_dataset, write_coerced_csv
from insight_builder.ingestion.schema import coerced_dataframe, infer_schema
from insight_builder.narration.narrator import narrate
from insight_builder.qa.intent_parser import parse_intent
from insight_builder.query.ask import ask_question
from insight_builder.validation.gates import gate_1_significant, gate_2_meaningful

_INTENT_TO_COLUMN_KEYS = {
    "ratio": ["numerator_col", "denominator_col", "group_col"],
    "group_diff": ["numeric_col", "categorical_col"],
    "correlation": ["col_a", "col_b"],
    "trend": ["numeric_col", "datetime_col"],
    "chi_square": ["col_a", "col_b"],
}


def _enrich(result: dict[str, Any], market_context: MarketContext | None) -> dict[str, Any]:
    """Annotation only: attaches related market findings when the answer's
    columns appear in them; never changes the computed answer."""
    if market_context is not None and result.get("columns"):
        attach_market_context([result], market_context)
    return result


def answer_question(
    dataset_path: str,
    question: str,
    audit_dir: str | None = None,
    market_context: MarketContext | None = None,
) -> dict[str, Any]:
    raw_df = load_dataset(dataset_path)
    schema = infer_schema(raw_df)
    clean_df = coerced_dataframe(raw_df, schema)
    schema_roles = {name: profile.role for name, profile in schema.items()}

    audit_path = Path(audit_dir) if audit_dir else Path(tempfile.mkdtemp(prefix="qa_audit_"))
    audit_path.mkdir(parents=True, exist_ok=True)

    coerced_csv_path = write_coerced_csv(clean_df, schema, audit_path)

    intent = parse_intent(question, schema_roles)
    intent_type = intent.get("type")

    if intent_type not in _INTENT_TO_COLUMN_KEYS:
        result = ask_question(str(coerced_csv_path), question, audit_dir=str(audit_path))
        result["tier"] = "B"
        result["tier_a_reason"] = intent.get("reason", "unsupported intent shape")
        return result

    columns = {key: intent.get(key) for key in _INTENT_TO_COLUMN_KEYS[intent_type]}
    script_text = render_script({"type": intent_type, "columns": columns}, str(coerced_csv_path))
    result = run_script(script_text, audit_path / "scripts")

    if "error" in result:
        tier_b_result = ask_question(str(coerced_csv_path), question, audit_dir=str(audit_path))
        tier_b_result["tier"] = "B"
        tier_b_result["tier_a_reason"] = f"Tier A failed: {result['error']}"
        return tier_b_result

    result["question"] = question
    result["tier"] = "A"
    _enrich(result, market_context)

    if "p_value" not in result:
        # ratio (ungrouped) carries no p-value — it's a reported fact, not a hypothesis test.
        result["confidence_tier"] = "business_fact"
        result["narrative"] = f"[Business Fact] {narrate(result)}"
    elif gate_1_significant(result) and gate_2_meaningful(result):
        # A single ad-hoc question has no batch to Benjamini-Hochberg-correct against,
        # so only gates 1-2 apply here (gate 3 in validation/gates.py is a batch-only step).
        result["confidence_tier"] = "validated"
        result["narrative"] = f"[Validated] {narrate(result)}"
    else:
        result["confidence_tier"] = "not_significant"
        p = result.get("p_value")
        eff = result.get("effect_size")
        result["narrative"] = (
            f"[Not Significant] {narrate(result)} "
            f"(p={p:.3f}, effect_size={eff:.3f} — does not clear the significance/effect-size bar.)"
        )

    return result
