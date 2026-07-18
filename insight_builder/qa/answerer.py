"""Answers a natural-language question against a dataset.

Flow: LLM parses intent -> sandboxed script computes the real number ->
LLM narrates the already-computed result. The LLM never touches raw data
rows and never invents a number; every figure in the answer traces back to
a script saved under audit_dir.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from insight_builder.execution.renderer import render_script
from insight_builder.execution.runner import run_script
from insight_builder.ingestion.schema import coerced_dataframe, infer_schema
from insight_builder.qa.intent_parser import parse_intent
from insight_builder.qa.llm_client import complete

_NARRATION_SYSTEM_PROMPT = """You turn an already-computed statistical result \
into one grounded, plain-English sentence for a business user. Use only the \
numbers given to you — never invent or adjust any figure. Be concise."""


def ask(question: str, csv_path: str, audit_dir: str | None = None) -> dict[str, Any]:
    raw_df = pd.read_csv(csv_path)
    schema = infer_schema(raw_df)
    clean_df = coerced_dataframe(raw_df, schema)
    schema_roles = {name: profile.role for name, profile in schema.items()}

    intent = parse_intent(question, schema_roles)

    if intent["type"] == "unsupported":
        return {
            "question": question,
            "answer": f"I can't answer that with this dataset: {intent['reason']}",
            "intent": intent,
        }

    audit_path = Path(audit_dir) if audit_dir else Path(tempfile.mkdtemp(prefix="qa_audit_"))
    audit_path.mkdir(parents=True, exist_ok=True)

    coerced_csv_path = audit_path / "coerced_dataset.csv"
    datetime_cols = [n for n, p in schema.items() if p.role == "datetime"]
    to_write = clean_df.copy()
    for c in datetime_cols:
        to_write[c] = to_write[c].dt.strftime("%Y-%m-%d")
    to_write.to_csv(coerced_csv_path, index=False)

    columns = {k: v for k, v in intent.items() if k != "type"}
    candidate = {"type": intent["type"], "columns": columns}

    script_text = render_script(candidate, str(coerced_csv_path))
    result = run_script(script_text, audit_path / "scripts")

    if "error" in result:
        return {
            "question": question,
            "answer": f"The computation failed: {result['error']}",
            "intent": intent,
            "result": result,
        }

    narration_prompt = (
        f"Question: {question}\n"
        f"Computed result: {result}\n\n"
        "Write the one-sentence grounded answer."
    )
    answer = complete(narration_prompt, system=_NARRATION_SYSTEM_PROMPT).strip()

    return {
        "question": question,
        "answer": answer,
        "intent": intent,
        "result": result,
        "audit_dir": str(audit_path),
    }
