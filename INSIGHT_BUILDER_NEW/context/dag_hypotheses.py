"""Turns the Market Researcher's causal DAG into concrete test candidates.

The DAG encodes *believed* causal structure (from external research); this
module translates each believed influence between two dataset variables —
direct, or routed through external-factor nodes we can't observe — into the
matching observable test shape (correlation / group_diff / trend /
chi_square) on the real columns. The pipeline's statistical gates then judge
whether the data actually supports it, so a wrong DAG edge can only ever
waste one test, never fabricate an insight.

Everything here is deterministic: no LLM call, no network. DAG node ids are
matched to schema columns by normalized name.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from insight_builder.context.market import MarketContext
from insight_builder.ingestion.schema import ColumnProfile

MAX_PATH_EDGES = 3
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}

# Same bounds hypotheses/generator.py uses for a usable grouping dimension.
MIN_CATEGORY_CARDINALITY = 2
MAX_CATEGORY_CARDINALITY = 20


def _normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _match_columns(context: MarketContext, schema: dict[str, ColumnProfile]) -> dict[str, str]:
    """DAG node id -> real schema column, by normalized-name equality."""
    by_norm = {_normalize(col): col for col in schema}
    matches: dict[str, str] = {}
    for node_id in context.dataset_variable_ids():
        col = by_norm.get(_normalize(node_id))
        if col is not None:
            matches[node_id] = col
    return matches


def _paths_between_variables(context: MarketContext, variable_ids: set[str]) -> list[list[Any]]:
    """All simple edge-paths from one dataset variable to another, at most
    MAX_PATH_EDGES long, where intermediate hops are external factors only
    (a path through another *observed* variable is that variable's own story)."""
    adjacency: dict[str, list[Any]] = {}
    for edge in context.dag_edges:
        adjacency.setdefault(edge.source, []).append(edge)

    paths: list[list[Any]] = []
    for start in variable_ids:
        queue: deque[list[Any]] = deque([[e] for e in adjacency.get(start, [])])
        while queue:
            path = queue.popleft()
            tail = path[-1].target
            if tail in variable_ids:
                paths.append(path)
                continue
            if len(path) >= MAX_PATH_EDGES:
                continue
            visited = {start} | {e.target for e in path}
            for nxt in adjacency.get(tail, []):
                if nxt.target not in visited:
                    queue.append(path + [nxt])
    return paths


def _candidate_for_pair(
    cause_col: str, effect_col: str, schema: dict[str, ColumnProfile]
) -> tuple[str, dict[str, Any]] | None:
    cause_role = schema[cause_col].role
    effect_role = schema[effect_col].role

    def _groupable(col: str) -> bool:
        return MIN_CATEGORY_CARDINALITY <= schema[col].cardinality <= MAX_CATEGORY_CARDINALITY

    if cause_role == "numeric" and effect_role == "numeric":
        return "correlation", {"col_a": cause_col, "col_b": effect_col}
    if cause_role == "categorical" and effect_role == "numeric" and _groupable(cause_col):
        return "group_diff", {"numeric_col": effect_col, "categorical_col": cause_col}
    if cause_role == "numeric" and effect_role == "categorical" and _groupable(effect_col):
        return "group_diff", {"numeric_col": cause_col, "categorical_col": effect_col}
    if cause_role == "categorical" and effect_role == "categorical" and _groupable(cause_col) and _groupable(effect_col):
        return "chi_square", {"col_a": cause_col, "col_b": effect_col}
    if cause_role == "datetime" and effect_role == "numeric":
        return "trend", {"numeric_col": effect_col, "datetime_col": cause_col}
    return None


def derive_dag_candidates(
    context: MarketContext, schema: dict[str, ColumnProfile]
) -> list[dict[str, Any]]:
    """One candidate per (cause column, effect column) pair connected in the
    DAG, keeping the highest-confidence path when several connect the pair."""
    if not context.has_dag:
        return []

    node_to_col = _match_columns(context, schema)
    if len(node_to_col) < 2:
        return []

    best_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for path in _paths_between_variables(context, set(node_to_col)):
        cause_col = node_to_col[path[0].source]
        effect_col = node_to_col[path[-1].target]
        if cause_col == effect_col:
            continue

        shaped = _candidate_for_pair(cause_col, effect_col, schema)
        if shaped is None:
            continue
        ctype, columns = shaped

        confidence = min(
            (_CONFIDENCE_RANK.get(e.confidence, 2) for e in path),
            default=2,
        )
        via = [context.dag_nodes[e.target]["label"] for e in path[:-1]]
        via_note = f" via {', '.join(via)}" if via else ""
        candidate = {
            "type": ctype,
            "columns": columns,
            "source": "market_dag",
            "label": f"Market research link: {cause_col} → {effect_col}{via_note}",
            "market_rationale": path[0].rationale or path[-1].rationale or None,
            "market_confidence": {3: "high", 2: "medium", 1: "low"}[confidence],
            "_confidence_rank": confidence,
        }

        key = (cause_col, effect_col)
        existing = best_by_pair.get(key)
        if existing is None or existing["_confidence_rank"] < confidence:
            best_by_pair[key] = candidate

    candidates = []
    for candidate in best_by_pair.values():
        candidate.pop("_confidence_rank", None)
        candidates.append(candidate)
    return candidates
