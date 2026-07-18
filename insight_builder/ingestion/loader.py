"""Dataset loading and the one shared "coerce & persist" step.

Supports the two upload formats the product promises (CSV and Excel) in one
place, and owns the write-out of the coerced dataset that every sandboxed
script reads — previously copy-pasted in four modules.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from insight_builder.ingestion.schema import ColumnProfile

EXCEL_SUFFIXES = {".xlsx", ".xls", ".xlsm"}
SUPPORTED_SUFFIXES = EXCEL_SUFFIXES | {".csv"}


def is_supported_dataset(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_SUFFIXES


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Read a CSV or Excel dataset into a DataFrame. Excel reads the first
    sheet — multi-sheet selection is a UI concern, not an inference one."""
    suffix = Path(path).suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        return pd.read_excel(path)
    return pd.read_csv(path)


def dataset_columns(path: str | Path) -> list[str]:
    """Just the column names, without loading the data rows."""
    suffix = Path(path).suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        return list(pd.read_excel(path, nrows=0).columns)
    return list(pd.read_csv(path, nrows=0).columns)


def write_coerced_csv(clean_df: pd.DataFrame, schema: dict[str, ColumnProfile], audit_path: Path) -> Path:
    """Persist the role-coerced dataframe as the canonical CSV every sandboxed
    script runs against. Datetimes are serialized as ISO dates so a re-read
    parses them identically regardless of the original file's format."""
    audit_path.mkdir(parents=True, exist_ok=True)
    coerced_csv_path = audit_path / "coerced_dataset.csv"
    to_write = clean_df.copy()
    for name, profile in schema.items():
        if profile.role == "datetime":
            to_write[name] = to_write[name].dt.strftime("%Y-%m-%d")
    to_write.to_csv(coerced_csv_path, index=False)
    return coerced_csv_path
