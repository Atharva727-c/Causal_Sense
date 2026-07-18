"""Domain Knowledge Agent: turns a domain string into abstract KPI/hypothesis defs.

The LLM is the domain knowledge base here — nothing in code says "retail" or
"office supplies". It never sees the dataset, only the domain string, and it
never names a real column: it describes the *role* a column would need to
play (e.g. "monetary amount representing the value of one order"). Turning
those abstract slots into real column names is a separate agent
(schema_mapper.py) so the two judgment calls stay independently inspectable.
"""
from __future__ import annotations

import json
from typing import Any

from insight_builder.qa.llm_client import complete

_SYSTEM_PROMPT = """You are a business-domain expert advising a commercial team \
(revenue growth, sales, customer acquisition/retention, pricing, margin, and \
account/portfolio performance) — not clinical, compliance, academic, or \
back-office operations teams. Given a domain name, propose the KPIs and \
hypotheses that a commercial team in that domain would act on directly: \
things that change a pricing decision, a customer/account strategy, a sales \
or marketing investment, or a margin/revenue target. Every domain has other \
audiences (e.g. clinical quality, risk/compliance, IT ops) with their own \
KPIs — deliberately exclude those and stay in the commercial lane unless a \
metric also has a direct, obvious revenue/cost/customer angle.

Return ONLY a JSON array, no prose. Each element must match exactly one of \
these shapes (the "requires" object lists abstract variable slots you need \
mapped to real columns later — describe what each slot means, don't name \
real columns):

1. Ratio/KPI:
{"name": "<short KPI name>", "type": "ratio",
 "requires": {"numerator": "<description of the monetary/count quantity that is summed>",
              "denominator": "<description of the count/quantity it's divided by>",
              "group": "<description of an optional categorical breakdown, or null>"}}

2. Group comparison:
{"name": "<short name>", "type": "group_diff",
 "requires": {"numeric": "<description of the numeric measure>",
              "categorical": "<description of the grouping dimension>"}}

3. Correlation:
{"name": "<short name>", "type": "correlation",
 "requires": {"a": "<description>", "b": "<description>"}}

4. Trend:
{"name": "<short name>", "type": "trend",
 "requires": {"numeric": "<description of the measure>",
              "datetime": "<description of the time dimension>"}}

Propose 6-10 KPIs/hypotheses that are genuinely useful for this domain. \
Do not reference any specific dataset or column name — only describe roles."""


def get_domain_hypotheses(domain: str) -> list[dict[str, Any]]:
    raw = complete(f"Domain: {domain}", system=_SYSTEM_PROMPT).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    valid_types = {"ratio", "group_diff", "correlation", "trend"}
    return [
        item for item in parsed
        if isinstance(item, dict) and item.get("type") in valid_types and "requires" in item
    ]
