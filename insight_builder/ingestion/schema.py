"""Schema/role inference: classify columns without any knowledge of column names.

Roles: numeric, categorical, datetime, identifier, free_text
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

import pandas as pd

warnings.filterwarnings("ignore", message="Could not infer format")

_CURRENCY_RE = re.compile(r"^\s*[\$€£]?\s*-?[\d,]+\.?\d*\s*$")
_PERCENT_RE = re.compile(r"^\s*-?\d+\.?\d*\s*%\s*$")
# A real date has three components (day/month/year); an ID like "4293-1" has only two.
_DATE_SHAPE_RE = re.compile(r"^\s*\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\s*$")

IDENTIFIER_UNIQUE_RATIO = 0.9
CATEGORICAL_MAX_CARDINALITY = 50
CATEGORICAL_MAX_RATIO = 0.05


@dataclass
class ColumnProfile:
    name: str
    role: str
    dtype: str
    cardinality: int
    sample_values: list = field(default_factory=list)
    is_percent: bool = False


def _clean_numeric_series(s: pd.Series) -> tuple[pd.Series, bool] | None:
    """Try to coerce a text column that looks numeric/currency/percent into floats.
    Returns (coerced_series, is_percent) or None if it doesn't look numeric."""
    sample = s.dropna().astype(str).head(50)
    if sample.empty:
        return None
    looks_currency = sample.str.match(_CURRENCY_RE).mean() > 0.9
    looks_percent = sample.str.match(_PERCENT_RE).mean() > 0.9
    if not (looks_currency or looks_percent):
        return None
    cleaned = (
        s.astype(str)
        .str.replace(r"[\$€£,%]", "", regex=True)
        .str.strip()
    )
    coerced = pd.to_numeric(cleaned, errors="coerce")
    if coerced.notna().mean() < 0.9:
        return None
    return coerced, looks_percent


def infer_schema(df: pd.DataFrame) -> dict[str, ColumnProfile]:
    """Infer a role for every column in df, independent of column names."""
    n_rows = len(df)
    profiles: dict[str, ColumnProfile] = {}

    for col in df.columns:
        s = df[col]
        cardinality = s.nunique(dropna=True)
        unique_ratio = cardinality / n_rows if n_rows else 0

        is_percent = False

        # 1. already-numeric dtype
        if pd.api.types.is_numeric_dtype(s):
            role = "numeric"
            dtype = "float"

        # 2. already-datetime dtype
        elif pd.api.types.is_datetime64_any_dtype(s):
            role = "datetime"
            dtype = "datetime"

        else:
            # 3. text that is secretly numeric (currency/percent) or a real date
            numeric_result = _clean_numeric_series(s)
            if numeric_result is not None:
                role = "numeric"
                dtype = "float"
                is_percent = numeric_result[1]
            else:
                sample = s.dropna().astype(str).head(50)
                looks_date_shaped = not sample.empty and sample.str.match(_DATE_SHAPE_RE).mean() > 0.9
                if looks_date_shaped:
                    parsed_default = pd.to_datetime(s, errors="coerce")
                    parsed_dayfirst = pd.to_datetime(s, errors="coerce", dayfirst=True)
                    parsed_dates = (
                        parsed_default
                        if parsed_default.notna().mean() >= parsed_dayfirst.notna().mean()
                        else parsed_dayfirst
                    )
                else:
                    parsed_dates = pd.Series([pd.NaT] * len(s), index=s.index)

                if parsed_dates.notna().mean() > 0.9:
                    role = "datetime"
                    dtype = "datetime"
                elif unique_ratio > IDENTIFIER_UNIQUE_RATIO:
                    role = "identifier"
                    dtype = "string"
                elif cardinality <= CATEGORICAL_MAX_CARDINALITY or unique_ratio <= CATEGORICAL_MAX_RATIO:
                    role = "categorical"
                    dtype = "string"
                else:
                    role = "free_text"
                    dtype = "string"

        profiles[col] = ColumnProfile(
            name=col,
            role=role,
            dtype=dtype,
            cardinality=int(cardinality),
            sample_values=s.dropna().astype(str).head(3).tolist(),
            is_percent=is_percent,
        )

    return profiles


def coerced_dataframe(df: pd.DataFrame, schema: dict[str, ColumnProfile]) -> pd.DataFrame:
    """Return a copy of df with numeric/datetime-role columns actually converted."""
    out = df.copy()
    for name, profile in schema.items():
        if profile.role == "numeric" and not pd.api.types.is_numeric_dtype(out[name]):
            cleaned = out[name].astype(str).str.replace(r"[\$€£,%]", "", regex=True).str.strip()
            out[name] = pd.to_numeric(cleaned, errors="coerce")
        elif profile.role == "datetime" and not pd.api.types.is_datetime64_any_dtype(out[name]):
            parsed_default = pd.to_datetime(out[name], errors="coerce")
            parsed_dayfirst = pd.to_datetime(out[name], errors="coerce", dayfirst=True)
            out[name] = (
                parsed_default
                if parsed_default.notna().mean() >= parsed_dayfirst.notna().mean()
                else parsed_dayfirst
            )
    return out
