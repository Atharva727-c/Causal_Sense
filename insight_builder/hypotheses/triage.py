"""Cheap vectorized screening pass — cuts candidates before expensive template execution."""
from __future__ import annotations

from typing import Any

import pandas as pd

MIN_GROUP_SIZE = 5
CORRELATION_SCREEN_THRESHOLD = 0.10


def screen_candidates(df: pd.DataFrame, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    survivors: list[dict[str, Any]] = []

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    corr_matrix = df[numeric_cols].corr() if len(numeric_cols) >= 2 else None

    for cand in candidates:
        cols = cand["columns"]

        if cand["type"] == "correlation":
            a, b = cols["col_a"], cols["col_b"]
            if corr_matrix is None or a not in corr_matrix or b not in corr_matrix:
                continue
            r = corr_matrix.loc[a, b]
            if pd.isna(r) or abs(r) < CORRELATION_SCREEN_THRESHOLD:
                continue
            survivors.append(cand)

        elif cand["type"] == "group_diff":
            num_col, cat_col = cols["numeric_col"], cols["categorical_col"]
            sizes = df.groupby(cat_col)[num_col].count()
            if (sizes >= MIN_GROUP_SIZE).sum() < 2:
                continue
            survivors.append(cand)

        elif cand["type"] == "chi_square":
            a, b = cols["col_a"], cols["col_b"]
            ct = pd.crosstab(df[a], df[b])
            if ct.shape[0] < 2 or ct.shape[1] < 2 or (ct.values < MIN_GROUP_SIZE).mean() > 0.8:
                continue
            survivors.append(cand)

        elif cand["type"] == "trend":
            num_col, dt_col = cols["numeric_col"], cols["datetime_col"]
            valid = df[[num_col, dt_col]].dropna()
            if len(valid) < 10:
                continue
            survivors.append(cand)

        else:
            survivors.append(cand)

    return survivors
