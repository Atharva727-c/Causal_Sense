"""Detects functional-dependency hierarchies among categorical/free-text columns
(e.g. Address -> City -> State) so dimension analysis isn't repeated at every
granularity of what is really one underlying hierarchy. Purely statistical -
never keyed on column names, so it applies to any schema.
"""
from __future__ import annotations

import pandas as pd

NESTING_PURITY_THRESHOLD = 0.98


def _is_nested_in(df: pd.DataFrame, fine_col: str, coarse_col: str, purity: float = NESTING_PURITY_THRESHOLD) -> bool:
    """True if fine_col's value determines coarse_col's value for at least
    `purity` of rows - i.e. every value of fine_col belongs to (almost) exactly
    one value of coarse_col, the signature of a finer level nested in a coarser
    one (every address belongs to one city, not several)."""
    sizes = df.groupby(fine_col)[coarse_col].nunique(dropna=True)
    if sizes.empty:
        return False
    return (sizes <= 1).mean() >= purity


def hierarchy_roots(df: pd.DataFrame, columns: list[str]) -> list[str]:
    """Collapse columns that are functionally nested inside a coarser column in
    the same list down to the single coarsest representative of each chain
    (Address -> City -> State collapses to State)."""
    cols = list(dict.fromkeys(columns))
    if len(cols) <= 1:
        return cols

    cardinality = {c: df[c].nunique(dropna=True) for c in cols}
    parent = {c: c for c in cols}

    def find(c: str) -> str:
        while parent[c] != c:
            c = parent[c]
        return c

    # Process from highest to lowest cardinality so a column is always tested
    # against coarser (or equal-cardinality, for ties) candidates first.
    ordered = sorted(cols, key=lambda c: (-cardinality[c], cols.index(c)))
    for fine in ordered:
        for coarse in cols:
            if coarse == fine or cardinality[coarse] > cardinality[fine]:
                continue
            if find(fine) == find(coarse):
                continue
            if _is_nested_in(df, fine, coarse):
                parent[find(fine)] = find(coarse)

    return [c for c in cols if find(c) == c]
