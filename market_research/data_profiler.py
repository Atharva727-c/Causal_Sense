"""Loads a user-uploaded dataset and builds a structured profile of it:
column roles, basic stats, an inferred/generated description, business domain,
and whether the data has a date-bounded timeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import IO, Union

import pandas as pd

from .llm_client import chat_json
from .models import ColumnProfile, DataProfile, TimelineInfo

FileInput = Union[str, Path, IO[bytes]]

_CURRENCY_RE = re.compile(r"^-?\$[\d,]+\.?\d*$")
_PERCENT_RE = re.compile(r"^-?\d+\.?\d*%$")


def load_dataframe(file: FileInput, filename: str | None = None) -> pd.DataFrame:
    if isinstance(file, (str, Path)):
        suffix = Path(file).suffix.lower()
    else:
        if not filename:
            raise ValueError("filename is required when passing a file-like object")
        suffix = Path(filename).suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(file)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(file)
    raise ValueError(f"Unsupported file type: {suffix}")


def _clean_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    cleaned = series.astype(str).str.replace(r"[\$,%]", "", regex=True).str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def _infer_role_and_stats(name: str, series: pd.Series) -> tuple[str, dict]:
    non_null = series.dropna()
    if non_null.empty:
        return "text", {}

    lname = name.lower()
    sample = non_null.astype(str).head(50)

    if "date" in lname:
        parsed_dates = pd.to_datetime(non_null, dayfirst=True, errors="coerce")
        if parsed_dates.notna().mean() > 0.7:
            valid = parsed_dates.dropna()
            return "date", {"min": str(valid.min().date()), "max": str(valid.max().date())}

    is_currency = sample.str.match(_CURRENCY_RE).mean() > 0.8
    is_percent = sample.str.match(_PERCENT_RE).mean() > 0.8

    if is_currency or is_percent or pd.api.types.is_numeric_dtype(series):
        numeric = _clean_numeric(series).dropna()
        if not numeric.empty:
            return "numeric", {
                "min": round(float(numeric.min()), 2),
                "max": round(float(numeric.max()), 2),
                "mean": round(float(numeric.mean()), 2),
            }

    unique_count = series.nunique(dropna=True)
    unique_ratio = unique_count / max(len(non_null), 1)

    if unique_ratio > 0.9 and any(k in lname for k in ("id", "no", "number", "code")):
        return "identifier", {"unique_count": int(unique_count)}

    if unique_ratio < 0.5:
        top_values = series.value_counts(dropna=True).head(5)
        return "categorical", {"top_values": {str(k): int(v) for k, v in top_values.items()}}

    return "text", {"unique_count": int(unique_count)}


def profile_columns(df: pd.DataFrame) -> list[ColumnProfile]:
    profiles = []
    for name in df.columns:
        series = df[name]
        role, stats = _infer_role_and_stats(name, series)
        missing_pct = round(float(series.isna().mean() * 100), 2)
        sample_values = [str(v) for v in series.dropna().astype(str).unique()[:5]]
        profiles.append(
            ColumnProfile(
                name=name,
                dtype=str(series.dtype),
                role=role,
                missing_pct=missing_pct,
                sample_values=sample_values,
                stats=stats,
            )
        )
    return profiles


_TIMELINE_PRIORITY_KEYWORDS = ["order date", "transaction date", "purchase date", "sale date", "date"]


def detect_timeline(df: pd.DataFrame, columns: list[ColumnProfile]) -> TimelineInfo:
    date_columns = [c for c in columns if c.role == "date"]
    if not date_columns:
        return TimelineInfo(has_timeline=False)

    chosen = None
    for keyword in _TIMELINE_PRIORITY_KEYWORDS:
        for column in date_columns:
            if keyword in column.name.lower():
                chosen = column
                break
        if chosen:
            break
    chosen = chosen or date_columns[0]

    parsed = pd.to_datetime(df[chosen.name], dayfirst=True, errors="coerce").dropna()
    if parsed.empty:
        return TimelineInfo(has_timeline=False)

    return TimelineInfo(
        has_timeline=True,
        date_column=chosen.name,
        start_date=str(parsed.min().date()),
        end_date=str(parsed.max().date()),
    )


_DOMAIN_SYSTEM_PROMPT = (
    "You are a data analyst who specializes in quickly understanding unfamiliar datasets. "
    "Given a dataset's column schema and sample values, and optionally a user-provided "
    "description, identify the business domain/industry and, only if no description was "
    "provided, write one yourself."
)


def infer_domain_and_description(
    columns: list[ColumnProfile], user_description: str | None, row_count: int
) -> tuple[str, str, bool]:
    column_summary = "\n".join(
        f"- {c.name} ({c.role}, dtype={c.dtype}): sample values = {c.sample_values[:3]}" for c in columns
    )
    needs_description = not user_description
    prompt = (
        f"Dataset has {row_count} rows and {len(columns)} columns.\n\n"
        f"Columns:\n{column_summary}\n\n"
        f"User-provided description: {user_description or '(none provided)'}\n\n"
        "Return JSON with keys:\n"
        '- "domain": a short (3-8 word) label for the business domain/industry this data represents\n'
        '- "description": '
        + (
            "a 2-4 sentence description of what this dataset contains and represents"
            if needs_description
            else "just echo back the user-provided description verbatim"
        )
    )
    result = chat_json(_DOMAIN_SYSTEM_PROMPT, prompt)
    domain = result.get("domain", "unknown domain")
    description = user_description or result.get("description", "")
    return domain, description, needs_description


def build_data_profile(
    file: FileInput, description: str | None = None, filename: str | None = None
) -> DataProfile:
    df = load_dataframe(file, filename=filename)
    columns = profile_columns(df)
    timeline = detect_timeline(df, columns)
    domain, final_description, was_generated = infer_domain_and_description(columns, description, len(df))

    return DataProfile(
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        description=final_description,
        description_was_generated=was_generated,
        domain=domain,
        timeline=timeline,
    )
