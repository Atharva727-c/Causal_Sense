"""Generic hypothesis generation: loops over role pairs, never column names."""
from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from insight_builder.hypotheses.hierarchy import hierarchy_roots
from insight_builder.ingestion.schema import ColumnProfile

MIN_CATEGORY_CARDINALITY = 2
MAX_CATEGORY_CARDINALITY = 20
MAX_RATIO_GROUP_CARDINALITY = 20
COUNT_LIKE_INTEGER_RATIO = 0.99
MAX_TOPN_CARDINALITY = 500


def _is_count_like(series: pd.Series) -> bool:
    """A ratio denominator only makes sense against a genuine count/quantity
    column: non-negative whole numbers. A column that can be zero or negative
    (e.g. an ordinal rating like -3..+3, or a signed score) produces sign-flipped
    or exploding "per X" ratios, so it's excluded here regardless of how
    integer-like its values are -- counts of real things never go negative."""
    values = series.dropna()
    if values.empty:
        return False
    if values.min() < 0:
        return False
    return (values == values.round()).mean() >= COUNT_LIKE_INTEGER_RATIO


def generate_candidates(schema: dict[str, ColumnProfile], df: pd.DataFrame) -> list[dict[str, Any]]:
    """Enumerate candidate hypotheses purely from inferred roles."""
    numeric_cols = [n for n, p in schema.items() if p.role == "numeric"]
    categorical_cols = [
        n for n, p in schema.items()
        if p.role == "categorical" and MIN_CATEGORY_CARDINALITY <= p.cardinality <= MAX_CATEGORY_CARDINALITY
    ]
    datetime_cols = [n for n, p in schema.items() if p.role == "datetime"]

    # Top/bottom-N: which groups dominate a numeric total? Works for any categorical
    # or free-text column (e.g. product names) regardless of cardinality, since we
    # only ever surface the top/bottom 10 groups, not every group.
    topn_group_cols = [
        n for n, p in schema.items()
        if p.role in ("categorical", "free_text") and MIN_CATEGORY_CARDINALITY <= p.cardinality <= MAX_TOPN_CARDINALITY
    ]

    # Columns that are functionally nested inside another dimension column
    # (e.g. Address -> City -> State, every address belongs to one city) are
    # collapsed down to the single coarsest representative, so every level of
    # what is really one hierarchy doesn't generate its own redundant analysis.
    roots = set(hierarchy_roots(df, list(dict.fromkeys(categorical_cols + topn_group_cols))))
    categorical_cols = [c for c in categorical_cols if c in roots]
    topn_group_cols = [c for c in topn_group_cols if c in roots]

    candidates: list[dict[str, Any]] = []

    for num_col in numeric_cols:
        for cat_col in categorical_cols:
            candidates.append({
                "type": "group_diff",
                "columns": {"numeric_col": num_col, "categorical_col": cat_col},
                "source": "generic",
            })

    for num_a, num_b in combinations(numeric_cols, 2):
        candidates.append({
            "type": "correlation",
            "columns": {"col_a": num_a, "col_b": num_b},
            "source": "generic",
        })

    for num_col in numeric_cols:
        for dt_col in datetime_cols:
            candidates.append({
                "type": "trend",
                "columns": {"numeric_col": num_col, "datetime_col": dt_col},
                "source": "generic",
            })

    for cat_a, cat_b in combinations(categorical_cols, 2):
        candidates.append({
            "type": "chi_square",
            "columns": {"col_a": cat_a, "col_b": cat_b},
            "source": "generic",
        })

    # Ratio grouping uses the same hierarchy-collapsed categorical columns as
    # group_diff/chi_square (identical cardinality bounds - MAX_RATIO_GROUP_CARDINALITY
    # equals MAX_CATEGORY_CARDINALITY).
    ratio_group_cols = categorical_cols
    # Percent/rate columns (e.g. a discount %) are never a sensible ratio numerator
    # or denominator against raw amounts - only real quantities (amounts, counts).
    ratio_eligible_numeric_cols = [n for n in numeric_cols if not schema[n].is_percent]
    count_like_cols = {c for c in ratio_eligible_numeric_cols if _is_count_like(df[c])}
    # A ratio KPI (e.g. "amount per unit") only makes sense as amount-over-count:
    # skip pairs where neither/both sides are count-like, and never divide by a
    # non-count numeric column (that produces meaningless ratios like Quantity/Discount).
    for num_a, num_b in combinations(ratio_eligible_numeric_cols, 2):
        a_is_count, b_is_count = num_a in count_like_cols, num_b in count_like_cols
        if a_is_count == b_is_count:
            continue
        numerator_col, denominator_col = (num_b, num_a) if a_is_count else (num_a, num_b)

        candidates.append({
            "type": "ratio",
            "columns": {"numerator_col": numerator_col, "denominator_col": denominator_col, "group_col": None},
            "source": "generic_kpi",
        })
        for group_col in ratio_group_cols:
            candidates.append({
                "type": "ratio",
                "columns": {"numerator_col": numerator_col, "denominator_col": denominator_col, "group_col": group_col},
                "source": "generic_kpi",
            })

    for group_col in topn_group_cols:
        for num_col in numeric_cols:
            candidates.append({
                "type": "top_n",
                "columns": {"categorical_col": group_col, "numeric_col": num_col},
                "source": "generic_kpi",
            })
            candidates.append({
                "type": "concentration",
                "columns": {"categorical_col": group_col, "numeric_col": num_col},
                "source": "generic_kpi",
            })

    # Cross-dimensional drill-down: within each value of a coarse categorical
    # dimension, which value of a second categorical/free-text dimension
    # dominates a numeric total? (e.g. "top product per city"). Every numeric
    # column is evaluated in one script run per dimension pair to avoid an
    # explosion of subprocess-per-numeric-column candidates.
    if numeric_cols:
        for group_col in categorical_cols:
            for breakdown_col in topn_group_cols:
                if breakdown_col == group_col:
                    continue
                candidates.append({
                    "type": "cross_top_n",
                    "columns": {
                        "group_col": group_col,
                        "breakdown_col": breakdown_col,
                        "numeric_cols": tuple(numeric_cols),
                    },
                    "source": "generic_kpi",
                })

    return candidates
