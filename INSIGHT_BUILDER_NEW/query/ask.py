"""Ties ingestion -> query-code generation -> sandboxed execution for one
free-text question against one dataset.

Answers from this module carry confidence_tier="ad_hoc_query": they are a
one-off computed answer to whatever the user asked, not a hypothesis that
passed the significance/effect-size/BH gates in orchestrator.py, and not a
pre-vetted business fact either. They are tagged as such so the user never
confuses "the model answered my question" with "this is a validated finding".
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from insight_builder.execution.runner import run_script
from insight_builder.ingestion.loader import load_dataset, write_coerced_csv
from insight_builder.ingestion.schema import coerced_dataframe, infer_schema
from insight_builder.qa.language_guard import strip_editorializing
from insight_builder.query.query_agent import generate_query_code, render_query_script


def ask_question(dataset_path: str, question: str, audit_dir: str | None = None) -> dict[str, Any]:
    raw_df = load_dataset(dataset_path)
    schema = infer_schema(raw_df)
    clean_df = coerced_dataframe(raw_df, schema)

    audit_path = Path(audit_dir) if audit_dir else Path(tempfile.mkdtemp(prefix="query_audit_"))
    audit_path.mkdir(parents=True, exist_ok=True)

    coerced_csv_path = write_coerced_csv(clean_df, schema, audit_path)

    code_body = generate_query_code(question, schema)
    if code_body is None:
        return {
            "question": question,
            "confidence_tier": "ad_hoc_query",
            "error": "could_not_generate_safe_query",
            "narrative": "[Ad-hoc Query] Could not generate a safe answer to this question.",
            "audit_dir": str(audit_path),
        }

    script_text = render_query_script(code_body, str(coerced_csv_path))
    result = run_script(script_text, audit_path / "scripts")

    if "error" in result:
        # One regenerate-and-retry: feed the runtime error back so the model
        # can self-correct (e.g. a wrong column reference, a bad aggregation)
        # instead of immediately surfacing a worse answer to the user.
        retry_code = generate_query_code(
            question, schema, feedback=f"the code failed at runtime with this error: {result['error']}"
        )
        if retry_code is not None:
            script_text = render_query_script(retry_code, str(coerced_csv_path))
            result = run_script(script_text, audit_path / "scripts")

    if "error" in result:
        return {
            "question": question,
            "confidence_tier": "ad_hoc_query",
            "error": result["error"],
            "narrative": f"[Ad-hoc Query] Failed to answer: {result['error']}.",
            "audit_dir": str(audit_path),
        }

    answer = result.get("answer")
    explanation = strip_editorializing(result.get("explanation", ""))
    narrative = f"[Ad-hoc Query] Q: {question} -> A: {answer}."
    if explanation:
        narrative += f" {explanation}"
    return {
        "question": question,
        "confidence_tier": "ad_hoc_query",
        "answer": answer,
        "explanation": explanation,
        "narrative": narrative,
        "audit_dir": str(audit_path),
    }
