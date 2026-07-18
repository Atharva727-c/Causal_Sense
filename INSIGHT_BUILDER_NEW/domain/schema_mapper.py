"""Schema Mapping Agent: maps abstract domain KPI slots onto real columns.

Input is the dataset's actual schema (column name, inferred role, a few
sample values) plus the abstract "requires" slots from the Domain Knowledge
Agent. Output is a concrete column mapping with a confidence score. Nothing
here computes a statistic — it only proposes which real columns play which
role, and low-confidence/missing mappings are dropped rather than guessed
silently, so a bad LLM guess can never produce a bogus hypothesis.
"""
from __future__ import annotations

import json
from typing import Any

from insight_builder.ingestion.schema import ColumnProfile
from insight_builder.qa.language_guard import strip_editorializing
from insight_builder.qa.llm_client import complete

MIN_MAPPING_CONFIDENCE = 0.55

_SYSTEM_PROMPT = """You map abstract KPI variable slots onto real dataset \
columns. For each hypothesis, choose the best real column for every slot in \
its "requires" object, using the column's inferred role and sample values as \
evidence. If a slot is optional (e.g. "group") and no good column exists, use \
null. If a required slot has no reasonable match, set "confidence" to 0 and \
leave that slot null.

Return ONLY a JSON array, no prose, one object per input hypothesis:
{"name": "<same name as input>", "type": "<same type as input>",
 "columns": {"<slot>": "<real column name or null>", ...},
 "confidence": <0.0-1.0 overall confidence in this mapping>}

Only ever use column names exactly as given in the schema."""

_SLOT_TO_KEY = {
    "ratio": {"numerator": "numerator_col", "denominator": "denominator_col", "group": "group_col"},
    "group_diff": {"numeric": "numeric_col", "categorical": "categorical_col"},
    "correlation": {"a": "col_a", "b": "col_b"},
    "trend": {"numeric": "numeric_col", "datetime": "datetime_col"},
}

_EXPECTED_ROLE = {
    "numerator_col": "numeric", "denominator_col": "numeric", "group_col": "categorical",
    "numeric_col": "numeric", "categorical_col": "categorical",
    "col_a": None, "col_b": None,
    "datetime_col": "datetime",
}


def map_domain_hypotheses(
    domain_hypotheses: list[dict[str, Any]], schema: dict[str, ColumnProfile]
) -> list[dict[str, Any]]:
    if not domain_hypotheses:
        return []

    schema_desc = {
        name: {"role": profile.role, "sample_values": profile.sample_values}
        for name, profile in schema.items()
    }
    prompt = (
        f"Schema:\n{json.dumps(schema_desc, indent=2)}\n\n"
        f"Hypotheses to map:\n{json.dumps(domain_hypotheses, indent=2)}"
    )
    raw = complete(prompt, system=_SYSTEM_PROMPT).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        mappings = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(mappings, list):
        return []

    candidates: list[dict[str, Any]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        htype = mapping.get("type")
        slot_map = _SLOT_TO_KEY.get(htype)
        if slot_map is None:
            continue
        if mapping.get("confidence", 0) < MIN_MAPPING_CONFIDENCE:
            continue

        raw_columns = mapping.get("columns", {})
        columns: dict[str, str | None] = {}
        valid = True
        for slot, key in slot_map.items():
            col_name = raw_columns.get(slot)
            if col_name is None:
                columns[key] = None
                continue
            if col_name not in schema:
                valid = False
                break
            expected_role = _EXPECTED_ROLE.get(key)
            if expected_role is not None and schema[col_name].role != expected_role:
                valid = False
                break
            columns[key] = col_name
        if not valid:
            continue

        required_keys = [k for k in slot_map.values() if k != "group_col"]
        if any(columns.get(k) is None for k in required_keys):
            continue

        candidates.append({
            "type": htype,
            "columns": columns,
            "source": "domain_kpi" if htype == "ratio" else "domain",
            "label": strip_editorializing(mapping.get("name") or "") or None,
        })

    return candidates
