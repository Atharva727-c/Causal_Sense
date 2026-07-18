"""Ranks business-fact KPIs (ratio/top_n/cross_top_n/concentration) by how
noteworthy their own shape is -- never by column name or value, since this
has to work on any dataset. Each KPI type has a different payload, so each
gets its own generic "how skewed/concentrated is this" score on a 0-1 scale;
the scores are comparable across types because they all answer the same
question (does one group dominate?), just computed from different fields.
"""
from __future__ import annotations

from typing import Any

# A "dominant" group backed by only a handful of rows produces the same
# 0-1 skew score as one backed by hundreds -- the score alone can't tell a
# robust finding from a fluke of a tiny sample. Below this row count, the
# score is discounted proportionally rather than trusted at face value.
MIN_ROBUST_GROUP_COUNT = 5

# A ratio whose value rounds to 0.00 at the narration's own display
# precision (see narration/narrator.py's ":.2f" formatting) reads as
# uninformative regardless of how much it varies by group -- and a tiny
# overall_ratio in the denominator of the group-spread formula below can
# inflate the score to the 1.0 cap purely by dividing by something near
# zero. Both cases are filtered here rather than left to accidentally win.
_DISPLAY_ROUNDING_FLOOR = 0.005


def _size_weight(count: int | None) -> float:
    if not count:
        return 1.0
    return min(1.0, count / MIN_ROBUST_GROUP_COUNT)


def _concentration_score(kpi: dict[str, Any]) -> float:
    score = float(kpi.get("share_of_top_20pct_groups") or 0.0)
    top_groups = kpi.get("top_groups") or []
    leader_count = top_groups[0].get("count") if top_groups else None
    return score * _size_weight(leader_count)


def _top_n_score(kpi: dict[str, Any]) -> float:
    top = kpi.get("top") or []
    if len(top) < 2:
        return 0.0
    total_visible = sum(row["sum"] for row in top)
    if total_visible <= 0:
        return 0.0
    score = top[0]["sum"] / total_visible
    return score * _size_weight(top[0].get("count"))


def _ratio_score(kpi: dict[str, Any]) -> float:
    overall = kpi.get("overall_ratio")
    if overall is None or round(overall, 2) == 0 or abs(overall) < _DISPLAY_ROUNDING_FLOOR:
        return 0.0
    if kpi.get("test") != "ratio_by_group":
        return 0.0
    ratios = list(kpi.get("group_ratios", {}).values())
    if len(ratios) < 2:
        return 0.0
    return min(1.0, (max(ratios) - min(ratios)) / abs(overall))


def _cross_top_n_score(kpi: dict[str, Any]) -> float:
    best = 0.0
    for group in kpi.get("group_top") or []:
        top = group.get("top") or []
        if len(top) < 2:
            continue
        total = sum(row["value"] for row in top)
        if total > 0:
            score = (top[0]["value"] / total) * _size_weight(top[0].get("count"))
            best = max(best, score)
    return best


_SCORERS = {
    "concentration": _concentration_score,
    "top_n": _top_n_score,
    "ratio": _ratio_score,
    "cross_top_n": _cross_top_n_score,
}


def _grouping_dimension(kpi: dict[str, Any]) -> Any:
    """Whatever categorical column this KPI is sliced/grouped by, if any --
    used only to spread the top-N across different dimensions instead of
    letting one dimension (whichever happens to have the widest spread)
    crowd out every other angle on the data."""
    columns = kpi.get("columns", {})
    return columns.get("group_col") or columns.get("categorical_col")


def _measured_metric(kpi: dict[str, Any]) -> Any:
    """Whatever numeric column this KPI's value is actually computed from, if
    any -- used to spread the top-N across different measured metrics.
    Without this, a single numeric column whose distribution happens to be
    the most skewed (e.g. an ordinal risk rating rather than a true
    magnitude like revenue) can dominate every slot just because every
    grouping dimension scores highest when sliced by that one column."""
    columns = kpi.get("columns", {})
    return columns.get("numeric_col") or columns.get("numerator_col")


def rank_business_kpis(
    kpi_results: list[dict[str, Any]],
    top_n: int = 10,
    max_per_dimension: int = 2,
    max_per_metric: int = 2,
) -> list[dict[str, Any]]:
    """Returns the top_n KPI facts, highest-scoring first, capped at
    max_per_dimension picks per grouping dimension and max_per_metric picks
    per measured numeric column, so the result covers a spread of angles on
    the data rather than one dimension -- or one column's skewed
    distribution -- dominating every slot. Once every dimension/metric has
    hit its cap (or there aren't enough distinct ones to fill top_n),
    remaining slots are backfilled by score regardless of dimension/metric."""
    scored = sorted(
        (
            (_SCORERS.get(kpi.get("type"), lambda _: 0.0)(kpi), position, kpi)
            for position, kpi in enumerate(kpi_results)
        ),
        key=lambda item: (-item[0], item[1]),
    )

    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    dimension_counts: dict[Any, int] = {}
    metric_counts: dict[Any, int] = {}

    for _, _, kpi in scored:
        if len(selected) >= top_n:
            break
        dimension = _grouping_dimension(kpi)
        metric = _measured_metric(kpi)
        if dimension is not None and dimension_counts.get(dimension, 0) >= max_per_dimension:
            continue
        if metric is not None and metric_counts.get(metric, 0) >= max_per_metric:
            continue
        selected.append(kpi)
        selected_ids.add(id(kpi))
        if dimension is not None:
            dimension_counts[dimension] = dimension_counts.get(dimension, 0) + 1
        if metric is not None:
            metric_counts[metric] = metric_counts.get(metric, 0) + 1

    if len(selected) < top_n:
        for _, _, kpi in scored:
            if len(selected) >= top_n:
                break
            if id(kpi) not in selected_ids:
                selected.append(kpi)
                selected_ids.add(id(kpi))

    return selected
