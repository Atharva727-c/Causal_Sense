"""File ingestion: detect type, parse with pandas, extract schema / preview / stats."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def detect_file_type(filename: str) -> str:
    mapping = {
        ".csv": "csv", ".tsv": "csv",
        ".xlsx": "excel", ".xls": "excel",
        ".json": "json",
        ".parquet": "parquet",
        ".sql": "sql",
        ".txt": "text",
    }
    return mapping.get(Path(filename).suffix.lower(), "other")


async def process_file(path: Path, file_type: str) -> dict[str, Any]:
    """
    Returns:
      row_count, column_count,
      schema: [{name, dtype, null_pct, unique_count}],
      preview: [dict row, ...] (first 5),
      stats: {col: {count, mean, std, min, 25%, 50%, 75%, max}}
    """
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not installed — skipping file analysis")
        return _empty()

    try:
        df = _read(pd, path, file_type)
    except Exception as exc:
        logger.warning("Could not parse %s: %s", path, exc)
        return _empty()

    if df is None:
        return _empty()

    schema = [
        {
            "name": col,
            "dtype": str(df[col].dtype),
            "null_pct": round(float(df[col].isna().mean() * 100), 2),
            "unique_count": int(df[col].nunique()),
        }
        for col in df.columns[:100]  # cap at 100 columns
    ]

    numeric = df.select_dtypes(include="number")
    stats: dict[str, Any] = {}
    if not numeric.empty:
        desc = numeric.describe().round(4)
        stats = {col: desc[col].to_dict() for col in desc.columns}

    preview = (
        df.head(5)
        .fillna("")
        .astype(str)
        .to_dict(orient="records")
    )

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "schema": schema,
        "preview": preview,
        "stats": stats,
    }


def build_file_context(
    *,
    filename: str,
    schema: list[dict],
    preview: list[dict],
    stats: dict,
    row_count: int | None = None,
) -> str:
    """Build a compact LLM-ready markdown block from file metadata."""
    lines: list[str] = [f"### Attached file: `{filename}`"]

    if row_count is not None:
        lines.append(f"- **Rows:** {row_count:,}  **Columns:** {len(schema)}")

    if schema:
        lines.append("\n**Schema:**")
        for col in schema[:40]:
            lines.append(
                f"- `{col['name']}` ({col['dtype']}) — "
                f"{col['null_pct']}% null · {col['unique_count']} unique"
            )

    if preview:
        headers = list(preview[0].keys())[:10]
        lines.append("\n**Sample (first 5 rows):**")
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in preview[:5]:
            vals = [str(row.get(h, ""))[:40] for h in headers]
            lines.append("| " + " | ".join(vals) + " |")

    return "\n".join(lines)


def _empty() -> dict[str, Any]:
    return {"row_count": None, "column_count": None, "schema": [], "preview": [], "stats": {}}


def _read(pd: Any, path: Path, file_type: str) -> Any:
    if file_type == "csv":
        return pd.read_csv(path, nrows=50_000)
    if file_type == "excel":
        return pd.read_excel(path, nrows=50_000)
    if file_type == "json":
        return pd.read_json(path)
    if file_type == "parquet":
        return pd.read_parquet(path)
    return None
