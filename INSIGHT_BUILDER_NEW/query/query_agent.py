"""Query Agent: turns a free-text question into a pandas snippet, given only
the dataset's inferred schema (column names, roles, sample values) — never
the raw rows. The LLM writes descriptive pandas logic only (no hypothesis
tests, no file/network/process access); a blocklist screens the code before
it's ever written to disk or executed.
"""
from __future__ import annotations

import json
import re

from insight_builder.ingestion.schema import ColumnProfile
from insight_builder.qa.llm_client import complete

_SYSTEM_PROMPT = """You write pandas code to answer a question about a \
dataset. A DataFrame named `df` is already loaded in scope — do not read any \
file yourself and do not import anything (pandas as pd and numpy as np are \
already available). Use only the columns listed in the schema, exactly as \
named.

Write ONLY the body of code that computes the answer: no imports, no \
function/class definitions, no print statements. Assign your final answer to \
a variable named `result`, a JSON-serializable dict with:
- "answer": the direct answer (a number, string, or short list/dict)
- "explanation": one sentence, plain and factual, stating only what was \
computed (e.g. "Grouped by X and averaged Y."). Do NOT use subjective, \
hedging, or causal language -- no words like "surprisingly", "clearly", \
"significantly", "dramatically", "best"/"worst", or phrases implying one \
column causes/drives/leads to another. State the computation, not an \
interpretation of it.

Only perform descriptive computation: filters, group-bys, aggregates, \
ratios, sorts, top-N, value counts. Do NOT run statistical hypothesis tests \
(no t-test, ANOVA, correlation p-values, chi-square) — if the question implies \
one, just answer with the descriptive numbers instead (e.g. group means/counts).

Return ONLY the raw code, no prose, no markdown code fences."""

_FORBIDDEN_PATTERNS = [
    r"\bimport\b", r"\bopen\s*\(", r"\bexec\s*\(", r"\beval\s*\(",
    r"__\w+__", r"\bos\.", r"\bsys\.", r"\bsubprocess\b", r"\bsocket\b",
    r"\brequests\b", r"\bshutil\b", r"\binput\s*\(", r"\bcompile\s*\(",
    r"\bgetattr\s*\(", r"\bglobals\s*\(", r"\blocals\s*\(",
]
_FORBIDDEN_RE = re.compile("|".join(_FORBIDDEN_PATTERNS))

MAX_GENERATION_ATTEMPTS = 2


def _find_forbidden(code: str) -> str | None:
    match = _FORBIDDEN_RE.search(code)
    return match.group(0) if match else None


def is_safe_code(code: str) -> bool:
    """Blocklist screen — defense-in-depth on top of the subprocess sandbox
    that every generated script (this or the hypothesis templates) already
    runs in via execution/runner.py."""
    return _find_forbidden(code) is None


def _strip_code_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("python"):
            raw = raw[len("python"):]
        elif raw.startswith("json"):
            raw = raw[len("json"):]
        raw = raw.strip()
    return raw


def generate_query_code(
    question: str, schema: dict[str, ColumnProfile], feedback: str | None = None
) -> str | None:
    """feedback, when given, describes what was wrong with a prior attempt
    (a caught safety violation, or a runtime error the caller hit executing
    the previously-generated code) so the model can self-correct instead of
    the caller just falling back to a worse answer."""
    schema_desc = {
        name: {"role": profile.role, "sample_values": profile.sample_values}
        for name, profile in schema.items()
    }
    base_prompt = f"Schema:\n{json.dumps(schema_desc, indent=2)}\n\nQuestion: {question}"
    prompt = base_prompt
    if feedback:
        prompt += (
            f"\n\nYour previous attempt was rejected for this reason: {feedback} "
            "Rewrite the code to fix this, following all the same rules."
        )

    for _ in range(MAX_GENERATION_ATTEMPTS):
        raw = _strip_code_fences(complete(prompt, system=_SYSTEM_PROMPT).strip())
        if not raw:
            return None
        violation = _find_forbidden(raw)
        if violation is None:
            return raw
        # Regenerate once, telling the model exactly what it did wrong,
        # rather than silently giving up after the first unsafe attempt.
        prompt = (
            f"{base_prompt}\n\n"
            f"Your previous code used the forbidden pattern `{violation}` "
            "(no imports, no file/network/process access is allowed). "
            "Rewrite the code without it, following all the same rules."
        )
    return None


def render_query_script(code_body: str, dataset_path: str) -> str:
    return (
        "import json\n"
        "import pandas as pd\n"
        "import numpy as np\n"
        f"df = pd.read_csv({dataset_path!r})\n\n"
        f"{code_body}\n\n"
        "print(json.dumps(result, default=str))\n"
    )
