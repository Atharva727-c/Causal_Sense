"""Turns a natural-language question into a structured, executable intent.

The LLM only ever sees column names and roles (never raw data rows) and only
ever proposes *what* to compute. It does not compute anything itself — the
returned intent is executed by the same sandboxed Tier A templates used
elsewhere in the pipeline.
"""
from __future__ import annotations

import json
from typing import Any

from insight_builder.qa.llm_client import complete

_SYSTEM_PROMPT = """You translate a business question into a JSON computation \
intent over a dataset. You never see the actual data values, only column \
names and their inferred roles (numeric/categorical/datetime/identifier/free_text).

Return ONLY a JSON object, no prose, matching exactly one of these shapes:

1. Ratio/KPI question (e.g. "average order value", "profit rate", "X per Y"):
{"type": "ratio", "numerator_col": "<numeric column>", "denominator_col": "<numeric column>", "group_col": "<categorical column or null>"}

2. Group comparison question (e.g. "average X by Y", "does X differ by Y"):
{"type": "group_diff", "numeric_col": "<numeric column>", "categorical_col": "<categorical column>"}

3. Correlation question (e.g. "does X relate to Y"):
{"type": "correlation", "col_a": "<numeric column>", "col_b": "<numeric column>"}

4. Trend question (e.g. "how has X changed over time"):
{"type": "trend", "numeric_col": "<numeric column>", "datetime_col": "<datetime column>"}

5. Association question (e.g. "is X related to Y" for two categories):
{"type": "chi_square", "col_a": "<categorical column>", "col_b": "<categorical column>"}

If the question cannot be answered with the available columns, return:
{"type": "unsupported", "reason": "<short explanation>"}

Only ever use column names from the provided schema, exactly as given."""


def parse_intent(question: str, schema: dict[str, str]) -> dict[str, Any]:
    """schema maps column name -> role (numeric/categorical/datetime/identifier/free_text)."""
    prompt = (
        f"Schema (column: role):\n{json.dumps(schema, indent=2)}\n\n"
        f"Question: {question}"
    )
    raw = complete(prompt, system=_SYSTEM_PROMPT).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        intent = json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "unsupported", "reason": f"Could not parse LLM response: {raw[:200]}"}

    if not isinstance(intent, dict) or "type" not in intent:
        return {"type": "unsupported", "reason": "LLM returned an unexpected shape"}

    valid_cols = set(schema.keys())
    referenced_cols = [v for k, v in intent.items() if k.endswith("_col") and v]
    unknown = [c for c in referenced_cols if c not in valid_cols]
    if unknown:
        return {"type": "unsupported", "reason": f"LLM referenced unknown columns: {unknown}"}

    return intent
