"""Loads Tier A Jinja2 templates and fills them with column names only — never logic."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _pyjson(value: Any) -> str:
    """Like the `tojson` filter, but emits Python literals (None/True/False)
    instead of JSON ones (null/true/false) — these templates are Python
    source, not JSON documents. Using `tojson` on an optional column (e.g.
    ratio's group_col=None) silently renders `group_col = null`, a NameError
    at runtime that execution/runner.py swallows as a generic script error."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    return json.dumps(value)


_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
)
_env.filters["pyjson"] = _pyjson

MIN_GROUP_SIZE = 5

_TEMPLATE_FOR_TYPE = {
    "group_diff": "group_diff.py.j2",
    "correlation": "correlation.py.j2",
    "trend": "trend.py.j2",
    "chi_square": "chi_square.py.j2",
    "ratio": "ratio.py.j2",
    "top_n": "top_n.py.j2",
    "cross_top_n": "cross_top_n.py.j2",
    "concentration": "concentration.py.j2",
}


def render_script(candidate: dict[str, Any], dataset_path: str) -> str:
    template_name = _TEMPLATE_FOR_TYPE[candidate["type"]]
    template = _env.get_template(template_name)
    params = dict(candidate["columns"])
    params["dataset_path"] = dataset_path
    params["min_group_size"] = MIN_GROUP_SIZE
    return template.render(**params)
