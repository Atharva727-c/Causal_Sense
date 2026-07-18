#!/usr/bin/env python3
"""
explore_dataset.py — Adaptive, dataset-agnostic exploratory data analysis.

Implements steps 1–6 of the "Machine Learning Project Checklist"
(Géron, *Hands-On ML*, Appendix A → "Explore the Data"):

    1. Create a copy of the data for exploration (sample it down if large).
    2. Create a Jupyter notebook to keep a record of the exploration.
    3. Study each attribute and its characteristics
       (name · type · % missing · noisiness/outliers · usefulness · distribution).
    4. For supervised learning, identify the target attribute(s).
    5. Visualize the data.
    6. Study the correlations between attributes.

Steps 7–10 (solve manually, promising transforms, extra data, document
learnings) are intentionally left out — they come later.

Design goals
------------
* **Dataset-agnostic.** The script inspects whatever you hand it and adapts:
  tabular (numeric / categorical / boolean / text / id), datetime columns,
  and time-series (a detected/【--time-col】 ordering column unlocks temporal
  plots, resampling, rolling stats, autocorrelation and — if statsmodels is
  present — seasonal decomposition).
* **Graceful degradation.** Only ``pandas`` + ``numpy`` are hard requirements.
  ``matplotlib``/``seaborn`` enable plots; ``scipy`` enables normality tests;
  ``statsmodels`` enables seasonal decomposition; ``pyarrow``/``openpyxl``
  enable parquet/excel reading. Anything missing is skipped with a note,
  never a crash.
* **Reproducible record.** Produces a populated ``.ipynb`` (step 2) that
  re-runs the same engine, plus saved figures, a machine-readable
  ``profile.json`` and a human-readable ``REPORT.md``.

Usage
-----
    python explore_dataset.py path/to/data.csv
    python explore_dataset.py sales.parquet --target revenue --time-col order_date
    python explore_dataset.py big.csv --sample-rows 50000 --execute-notebook

Run ``python explore_dataset.py --help`` for the full option list.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import textwrap
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ── Hard dependencies ───────────────────────────────────────────────────────
import numpy as np
import pandas as pd

# ── Optional dependencies (feature-detected) ────────────────────────────────
def _try_import(name: str):
    try:
        return __import__(name)
    except Exception:  # pragma: no cover - environment dependent
        return None


plt = None
sns = None
scipy_stats = None
_HAS_MPL = _HAS_SNS = _HAS_SCIPY = _HAS_STATSMODELS = _HAS_NBFORMAT = False

try:
    import matplotlib

    matplotlib.use("Agg")  # headless-safe; notebooks override with %matplotlib inline
    import matplotlib.pyplot as plt  # type: ignore

    _HAS_MPL = True
except Exception:
    pass

if _HAS_MPL:
    try:
        import seaborn as sns  # type: ignore

        _HAS_SNS = True
    except Exception:
        pass

try:
    from scipy import stats as scipy_stats  # type: ignore

    _HAS_SCIPY = True
except Exception:
    pass

try:
    import statsmodels.api  # noqa: F401

    _HAS_STATSMODELS = True
except Exception:
    pass

try:
    import nbformat  # noqa: F401

    _HAS_NBFORMAT = True
except Exception:
    pass


warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

log = logging.getLogger("explore")


# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ExploreConfig:
    """All tunables in one place so the behaviour is transparent & testable."""

    # Sampling (step 1)
    sample_rows: int = 100_000          # cap the exploration copy at this many rows
    sample_frac: Optional[float] = None  # explicit fraction (overrides sample_rows)
    seed: int = 42

    # Type inference (step 3)
    categorical_max_cardinality: int = 50      # <= this many uniques → categorical
    categorical_max_ratio: float = 0.05        # or uniques/rows below this
    id_unique_ratio: float = 0.95              # >= this → likely an identifier
    text_min_avg_len: int = 25                 # avg chars above this + high card → text
    datetime_parse_success: float = 0.90       # frac parseable → treat object as datetime

    # Usefulness flags (step 3)
    high_missing_pct: float = 40.0             # flag columns missing more than this
    near_constant_pct: float = 99.0            # single value covers >= this % → near-constant

    # Outliers / noise (step 3)
    iqr_multiplier: float = 1.5
    zscore_threshold: float = 3.0

    # Visualization (step 5)
    max_numeric_plots: int = 30
    max_categorical_plots: int = 20
    top_categories: int = 20
    pairplot_max_cols: int = 6

    # Correlations (step 6)
    high_corr_threshold: float = 0.90          # multicollinearity warning
    max_corr_columns: int = 40                 # cap heatmap size

    # Time series (step 5/6)
    max_lags: int = 40                         # autocorrelation lags


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Load & copy the data (sampled if necessary)
# ══════════════════════════════════════════════════════════════════════════════
_READERS = {
    ".csv": "csv", ".tsv": "csv", ".txt": "csv",
    ".xlsx": "excel", ".xls": "excel", ".xlsm": "excel",
    ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl",
    ".parquet": "parquet", ".pq": "parquet",
    ".feather": "feather", ".ft": "feather",
}


def detect_file_type(path: Path) -> str:
    return _READERS.get(path.suffix.lower(), "unknown")


def _count_csv_rows(path: Path) -> Optional[int]:
    """Cheap line count for CSV/TSV so we can decide whether to sample."""
    try:
        with open(path, "rb") as fh:
            return max(sum(1 for _ in fh) - 1, 0)  # minus header
    except Exception:
        return None


def load_dataset(
    path: Path,
    cfg: ExploreConfig,
    *,
    sep: Optional[str] = None,
    sheet: Optional[str] = None,
    time_col: Optional[str] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Load a dataset of unknown shape/type and return a *working copy*
    (sampled down to ``cfg.sample_rows`` when needed) plus sampling metadata.

    Sampling strategy adapts to the data:
      * time-series (``time_col`` given/detected) → systematic (evenly spaced)
        sample so the temporal envelope is preserved;
      * otherwise → uniform random sample.
    """
    ftype = detect_file_type(path)
    if ftype == "unknown":
        log.warning("Unknown extension '%s' — attempting CSV parse.", path.suffix)
        ftype = "csv"

    total_rows: Optional[int] = None
    if ftype == "csv":
        if sep is None and path.suffix.lower() == ".tsv":
            sep = "\t"
        total_rows = _count_csv_rows(path)

    frac = cfg.sample_frac
    target_n = cfg.sample_rows

    # Decide how many rows to read.
    def _read_full() -> pd.DataFrame:
        if ftype == "csv":
            if sep is None:
                # Let pandas sniff the delimiter (python engine — no low_memory).
                return pd.read_csv(path, sep=None, engine="python")
            return pd.read_csv(path, sep=sep, low_memory=False)
        if ftype == "excel":
            return pd.read_excel(path, sheet_name=sheet or 0)
        if ftype == "json":
            return pd.read_json(path)
        if ftype == "jsonl":
            return pd.read_json(path, lines=True)
        if ftype == "parquet":
            return pd.read_parquet(path)
        if ftype == "feather":
            return pd.read_feather(path)
        raise ValueError(f"Unsupported file type: {ftype}")

    df_full = _read_full()
    original_rows = len(df_full)
    original_cols = df_full.shape[1]

    # Detect the time column early so sampling can respect ordering.
    detected_time = time_col or detect_time_column(df_full, cfg)

    # Decide whether to sample.
    do_sample = False
    if frac is not None:
        do_sample = 0 < frac < 1.0
    elif original_rows > target_n:
        do_sample = True
        frac = target_n / original_rows

    if do_sample:
        if detected_time and detected_time in df_full.columns:
            # Systematic sample preserving temporal order.
            df_sorted = df_full.sort_values(detected_time)
            step = max(int(round(1 / frac)), 1)
            df = df_sorted.iloc[::step].copy()
            method = f"systematic (every {step}th row, time-ordered by '{detected_time}')"
        else:
            df = df_full.sample(frac=frac, random_state=cfg.seed).copy()
            method = f"uniform random (frac={frac:.4f}, seed={cfg.seed})"
    else:
        df = df_full.copy()
        method = "none (full dataset kept)"

    df = df.reset_index(drop=True)

    meta = {
        "path": str(path),
        "file_type": ftype,
        "original_rows": original_rows,
        "original_columns": original_cols,
        "counted_rows_on_disk": total_rows,
        "working_rows": len(df),
        "working_columns": df.shape[1],
        "sampled": do_sample,
        "sample_method": method,
        "detected_time_column": detected_time,
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    return df, meta


def save_working_copy(df: pd.DataFrame, out_dir: Path) -> Path:
    """Persist the exploration copy so the analysis is reproducible."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "exploration_copy.parquet"
    try:
        df.to_parquet(target, index=False)
    except Exception:
        target = out_dir / "exploration_copy.csv"
        df.to_csv(target, index=False)
    return target


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Study each attribute
# ══════════════════════════════════════════════════════════════════════════════
def _try_parse_datetime(s: pd.Series, cfg: ExploreConfig) -> Optional[pd.Series]:
    """Return a parsed datetime series if a strong majority of values parse."""
    if s.dropna().empty:
        return None
    sample = s.dropna()
    if len(sample) > 5000:
        sample = sample.sample(5000, random_state=cfg.seed)
    parsed = pd.to_datetime(sample, errors="coerce", utc=False)
    success = parsed.notna().mean()
    if success >= cfg.datetime_parse_success:
        return pd.to_datetime(s, errors="coerce", utc=False)
    return None


def detect_time_column(df: pd.DataFrame, cfg: ExploreConfig) -> Optional[str]:
    """Best-effort detection of a temporal ordering column."""
    # 1) Existing datetime dtypes win.
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    # 2) Name-based hints, verified by parsing.
    hints = ("date", "time", "timestamp", "datetime", "dt", "period", "month", "day", "year")
    candidates = [c for c in df.columns if any(h in str(c).lower() for h in hints)]
    for col in candidates:
        if df[col].dtype == object and _try_parse_datetime(df[col], cfg) is not None:
            return col
    return None


def infer_semantic_type(s: pd.Series, cfg: ExploreConfig) -> str:
    """
    Map a column to a *semantic* type, richer than the pandas dtype:
      constant · boolean · datetime · numeric_continuous · numeric_discrete
      · categorical · id · text · structured · empty
    """
    n = len(s)
    non_null = s.dropna()
    nunique = non_null.nunique()

    if non_null.empty:
        return "empty"
    if nunique == 1:
        return "constant"

    if pd.api.types.is_bool_dtype(s) or (nunique == 2 and pd.api.types.is_numeric_dtype(s)):
        return "boolean"

    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"

    # Structured (lists / dicts / json-ish objects).
    if s.dtype == object:
        head = non_null.head(50)
        if head.map(lambda v: isinstance(v, (list, dict, tuple))).any():
            return "structured"

    if pd.api.types.is_numeric_dtype(s):
        # Integer-like with modest cardinality → discrete/count.
        is_int = pd.api.types.is_integer_dtype(s) or (non_null == non_null.round()).all()
        ratio = nunique / max(n, 1)
        # Near-unique integer key (e.g. a row id) → identifier, not a real feature.
        if is_int and ratio >= cfg.id_unique_ratio and nunique > cfg.categorical_max_cardinality:
            return "id"
        if is_int and (nunique <= cfg.categorical_max_cardinality or ratio < cfg.categorical_max_ratio):
            return "numeric_discrete"
        return "numeric_continuous"

    # Object / string columns.
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        parsed = _try_parse_datetime(s, cfg)
        if parsed is not None:
            return "datetime"

        ratio = nunique / max(n, 1)
        avg_len = non_null.astype(str).str.len().mean()
        if ratio >= cfg.id_unique_ratio:
            return "id"
        if avg_len and avg_len >= cfg.text_min_avg_len and ratio > 0.5:
            return "text"
        if nunique <= cfg.categorical_max_cardinality or ratio < cfg.categorical_max_ratio:
            return "categorical"
        return "text"

    return "categorical"


def _distribution_guess(s: pd.Series, cfg: ExploreConfig) -> dict[str, Any]:
    """Heuristic guess at the distribution family of a numeric column."""
    x = s.dropna().astype(float)
    out: dict[str, Any] = {"guess": None, "skew": None, "kurtosis": None, "normality_p": None, "notes": []}
    if len(x) < 8 or x.nunique() < 3:
        out["guess"] = "insufficient-data"
        return out

    skew = float(x.skew())
    kurt = float(x.kurt())
    out["skew"], out["kurtosis"] = round(skew, 4), round(kurt, 4)

    # Optional formal normality test.
    if _HAS_SCIPY and len(x) >= 20:
        try:
            sample = x.sample(min(len(x), 5000), random_state=cfg.seed)
            out["normality_p"] = round(float(scipy_stats.normaltest(sample).pvalue), 6)
        except Exception:
            pass

    all_positive = (x > 0).all()
    nearly_symmetric = abs(skew) < 0.5
    heavy_right = skew > 1.0

    if nearly_symmetric and abs(kurt) < 1.0:
        out["guess"] = "approximately Gaussian"
    elif heavy_right and all_positive:
        out["guess"] = "right-skewed (log-normal / exponential candidate — try log transform)"
        out["notes"].append("Positive & right-skewed: log/Box-Cox transform likely helps.")
    elif skew < -1.0:
        out["guess"] = "left-skewed"
    elif abs(skew) < 0.5 and kurt < -1.0:
        out["guess"] = "roughly uniform / platykurtic"
    else:
        out["guess"] = "moderately skewed / non-Gaussian"

    if out.get("normality_p") is not None and out["normality_p"] > 0.05:
        out["guess"] = "approximately Gaussian (normality test not rejected)"
    return out


def _numeric_noise(s: pd.Series, cfg: ExploreConfig) -> dict[str, Any]:
    """Outlier counts (IQR + z-score) and rounding diagnostics."""
    x = s.dropna().astype(float)
    out: dict[str, Any] = {}
    if x.empty:
        return out

    q1, q3 = x.quantile(0.25), x.quantile(0.75)
    iqr = q3 - q1
    lo, hi = q1 - cfg.iqr_multiplier * iqr, q3 + cfg.iqr_multiplier * iqr
    iqr_out = int(((x < lo) | (x > hi)).sum()) if iqr > 0 else 0

    z_out = 0
    if x.std(ddof=0) > 0:
        z = (x - x.mean()) / x.std(ddof=0)
        z_out = int((z.abs() > cfg.zscore_threshold).sum())

    # Rounding: fraction integer-valued + typical decimal places.
    is_int_valued = float((x == x.round()).mean())
    decimals = x.astype(str).str.extract(r"\.(\d+)")[0].dropna().str.len()
    typical_decimals = int(decimals.mode().iloc[0]) if not decimals.empty else 0

    out.update(
        {
            "iqr_outliers": iqr_out,
            "iqr_outlier_pct": round(iqr_out / len(x) * 100, 3),
            "zscore_outliers": z_out,
            "pct_integer_valued": round(is_int_valued * 100, 2),
            "typical_decimal_places": typical_decimals,
            "pct_zero": round(float((x == 0).mean()) * 100, 3),
            "pct_negative": round(float((x < 0).mean()) * 100, 3),
        }
    )
    return out


def profile_column(name: str, s: pd.Series, cfg: ExploreConfig) -> dict[str, Any]:
    """Full single-attribute profile (name/type/missing/noise/distribution/usefulness)."""
    n = len(s)
    non_null = s.dropna()
    n_missing = int(s.isna().sum())
    nunique = int(non_null.nunique())
    sem = infer_semantic_type(s, cfg)

    prof: dict[str, Any] = {
        "name": name,
        "pandas_dtype": str(s.dtype),
        "semantic_type": sem,
        "count": int(non_null.shape[0]),
        "missing": n_missing,
        "missing_pct": round(n_missing / n * 100, 3) if n else 0.0,
        "unique": nunique,
        "unique_pct": round(nunique / n * 100, 3) if n else 0.0,
        "bounded": None,
        "sample_values": [str(v)[:60] for v in non_null.head(5).tolist()],
        "usefulness_flags": [],
        "notes": [],
    }

    # ── Numeric ──────────────────────────────────────────────────────────────
    if sem in ("numeric_continuous", "numeric_discrete") or (
        pd.api.types.is_numeric_dtype(s) and sem == "boolean"
    ):
        x = non_null.astype(float)
        if not x.empty:
            prof["min"] = round(float(x.min()), 6)
            prof["max"] = round(float(x.max()), 6)
            prof["mean"] = round(float(x.mean()), 6)
            prof["median"] = round(float(x.median()), 6)
            prof["std"] = round(float(x.std()), 6)
            prof["bounded"] = "non-negative" if x.min() >= 0 else "unbounded (has negatives)"
            prof.update(_numeric_noise(s, cfg))
            prof["distribution"] = _distribution_guess(s, cfg)

    # ── Datetime ─────────────────────────────────────────────────────────────
    elif sem == "datetime":
        dt = pd.to_datetime(s, errors="coerce")
        dt_nn = dt.dropna()
        if not dt_nn.empty:
            prof["min"] = str(dt_nn.min())
            prof["max"] = str(dt_nn.max())
            prof["range_days"] = round((dt_nn.max() - dt_nn.min()).total_seconds() / 86400, 3)
            prof["monotonic_increasing"] = bool(dt_nn.is_monotonic_increasing)
            inferred = None
            try:
                inferred = pd.infer_freq(dt_nn.sort_values().head(200))
            except Exception:
                pass
            prof["inferred_frequency"] = inferred
            prof["bounded"] = "time-bounded"

    # ── Categorical / boolean / id / text / structured ────────────────────────
    else:
        vc = non_null.value_counts()
        if not vc.empty:
            prof["top_value"] = str(vc.index[0])[:60]
            prof["top_freq"] = int(vc.iloc[0])
            prof["top_pct"] = round(float(vc.iloc[0]) / n * 100, 3) if n else 0.0
            prof["top_values"] = {str(k)[:40]: int(v) for k, v in vc.head(10).items()}
            # Shannon entropy (bits) — dispersion of categories.
            p = vc / vc.sum()
            prof["entropy_bits"] = round(float(-(p * np.log2(p)).sum()), 4)
        if sem in ("text",):
            lens = non_null.astype(str).str.len()
            prof["avg_char_length"] = round(float(lens.mean()), 2)
            prof["max_char_length"] = int(lens.max())

    # ── Usefulness heuristics (step 3, "usefulness for the task") ─────────────
    flags = prof["usefulness_flags"]
    if sem == "constant":
        flags.append("constant → drop (no information)")
    if sem == "empty":
        flags.append("all-missing → drop")
    if prof["missing_pct"] >= cfg.high_missing_pct:
        flags.append(f"high missingness ({prof['missing_pct']}%) → impute carefully or drop")
    if sem == "id":
        flags.append("identifier-like (near-unique) → likely exclude from modelling")
    top_pct = prof.get("top_pct", 0.0)
    if sem in ("categorical", "boolean") and top_pct >= cfg.near_constant_pct:
        flags.append(f"near-constant ({top_pct}% one value) → low signal")
    if sem == "text":
        flags.append("free text → needs NLP/feature extraction before modelling")
    if sem == "structured":
        flags.append("structured (list/dict) → needs flattening/parsing")
    if not flags:
        flags.append("candidate feature")

    return prof


def profile_dataset(df: pd.DataFrame, cfg: ExploreConfig) -> list[dict[str, Any]]:
    return [profile_column(col, df[col], cfg) for col in df.columns]


def profile_to_frame(profiles: list[dict[str, Any]]) -> pd.DataFrame:
    """Compact tabular view of the per-attribute profile for quick scanning."""
    rows = []
    for p in profiles:
        rows.append(
            {
                "attribute": p["name"],
                "dtype": p["pandas_dtype"],
                "semantic": p["semantic_type"],
                "missing_%": p["missing_pct"],
                "unique": p["unique"],
                "min": p.get("min", ""),
                "max": p.get("max", ""),
                "mean": p.get("mean", ""),
                "skew": (p.get("distribution") or {}).get("skew", ""),
                "outliers(IQR)": p.get("iqr_outliers", ""),
                "distribution": (p.get("distribution") or {}).get("guess", ""),
                "flags": "; ".join(p["usefulness_flags"]),
            }
        )
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — Identify the target attribute(s)
# ══════════════════════════════════════════════════════════════════════════════
_TARGET_NAME_HINTS = (
    "target", "label", "class", "y", "outcome", "result", "response",
    "price", "sales", "revenue", "churn", "default", "fraud", "score",
    "rating", "sentiment", "survived", "diagnosis", "value",
)


def suggest_targets(
    df: pd.DataFrame,
    profiles: list[dict[str, Any]],
    cfg: ExploreConfig,
    explicit: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Suggest likely target column(s) and infer the problem type."""
    prof_by_name = {p["name"]: p for p in profiles}

    if explicit:
        chosen = [c for c in explicit if c in df.columns]
    else:
        scored: list[tuple[float, str]] = []
        for col in df.columns:
            name = str(col).lower()
            score = 0.0
            if name in _TARGET_NAME_HINTS:
                score += 5
            if any(name == h or name.endswith("_" + h) or name.startswith(h + "_") for h in _TARGET_NAME_HINTS):
                score += 3
            if any(h in name for h in _TARGET_NAME_HINTS):
                score += 1
            # Last column is a common convention for the label.
            if col == df.columns[-1]:
                score += 0.5
            p = prof_by_name[col]
            if p["semantic_type"] in ("id",) or p["missing_pct"] > 0:
                score -= 2  # targets are usually complete & not ids
            if score > 0:
                scored.append((score, col))
        scored.sort(reverse=True)
        chosen = [c for _, c in scored[:1]]  # single best guess

    result: dict[str, Any] = {"targets": chosen, "explicit": bool(explicit), "details": {}}
    for col in chosen:
        p = prof_by_name[col]
        sem = p["semantic_type"]
        if sem in ("numeric_continuous",):
            ptype = "regression"
        elif sem in ("boolean",) or (sem in ("categorical", "numeric_discrete") and p["unique"] <= 20):
            ptype = "classification" + (" (binary)" if p["unique"] == 2 else " (multiclass)")
        elif sem == "numeric_discrete":
            ptype = "regression or ordinal classification"
        else:
            ptype = "unclear — inspect manually"
        result["details"][col] = {
            "semantic_type": sem,
            "n_classes_or_unique": p["unique"],
            "suggested_problem_type": ptype,
        }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — Visualize (adaptive to the detected types)
# ══════════════════════════════════════════════════════════════════════════════
def _finish_fig(fig, name: str, plots_dir: Optional[Path], show: bool) -> Optional[Path]:
    saved = None
    if plots_dir is not None:
        plots_dir.mkdir(parents=True, exist_ok=True)
        saved = plots_dir / f"{name}.png"
        fig.savefig(saved, dpi=110, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return saved


def visualize(
    df: pd.DataFrame,
    profiles: list[dict[str, Any]],
    cfg: ExploreConfig,
    *,
    target: Optional[str] = None,
    time_col: Optional[str] = None,
    plots_dir: Optional[Path] = None,
    show: bool = False,
) -> list[str]:
    """Render an adaptive set of figures. Returns list of saved file paths."""
    if not _HAS_MPL:
        log.warning("matplotlib not installed — skipping visualizations.")
        return []

    prof_by_name = {p["name"]: p for p in profiles}
    numeric = [p["name"] for p in profiles if p["semantic_type"] in ("numeric_continuous", "numeric_discrete")]
    categorical = [p["name"] for p in profiles if p["semantic_type"] in ("categorical", "boolean")]
    saved: list[str] = []

    def _rec(path: Optional[Path]):
        if path:
            saved.append(str(path))

    # ── Missingness overview ───────────────────────────────────────────────
    miss = pd.Series({p["name"]: p["missing_pct"] for p in profiles}).sort_values(ascending=False)
    miss = miss[miss > 0]
    if not miss.empty:
        fig, ax = plt.subplots(figsize=(9, max(3, 0.3 * len(miss))))
        miss.head(40).sort_values().plot.barh(ax=ax, color="#c0392b")
        ax.set_title("Missing values by attribute (%)")
        ax.set_xlabel("% missing")
        _rec(_finish_fig(fig, "01_missingness", plots_dir, show))

    # ── Numeric histograms ──────────────────────────────────────────────────
    for col in numeric[: cfg.max_numeric_plots]:
        x = df[col].dropna().astype(float)
        if x.nunique() < 2:
            continue
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
        if _HAS_SNS:
            sns.histplot(x, kde=True, ax=axes[0], color="#2980b9")
        else:
            axes[0].hist(x, bins=40, color="#2980b9")
        axes[0].set_title(f"Distribution — {col}")
        _boxplot(axes[1], x, horizontal=True, widths=0.6)
        g = prof_by_name[col].get("distribution", {}).get("guess", "")
        axes[1].set_title(f"Box (outliers) — {g}")
        _rec(_finish_fig(fig, f"num_{_slug(col)}", plots_dir, show))

    # ── Categorical bar charts ────────────────────────────────────────────────
    for col in categorical[: cfg.max_categorical_plots]:
        vc = df[col].astype(str).value_counts().head(cfg.top_categories)
        if vc.empty:
            continue
        fig, ax = plt.subplots(figsize=(9, max(3, 0.3 * len(vc))))
        vc.sort_values().plot.barh(ax=ax, color="#27ae60")
        ax.set_title(f"Top categories — {col}")
        ax.set_xlabel("count")
        _rec(_finish_fig(fig, f"cat_{_slug(col)}", plots_dir, show))

    # ── Target-focused plots ─────────────────────────────────────────────────
    if target and target in df.columns:
        tprof = prof_by_name.get(target, {})
        fig, ax = plt.subplots(figsize=(8, 4))
        if tprof.get("semantic_type") in ("numeric_continuous",):
            df[target].dropna().astype(float).plot.hist(bins=40, ax=ax, color="#8e44ad")
        else:
            df[target].astype(str).value_counts().head(cfg.top_categories).plot.bar(ax=ax, color="#8e44ad")
        ax.set_title(f"Target distribution — {target}")
        _rec(_finish_fig(fig, "target_distribution", plots_dir, show))

        # Numeric features vs target.
        for col in [c for c in numeric if c != target][:12]:
            fig, ax = plt.subplots(figsize=(7, 4))
            if tprof.get("semantic_type") in ("numeric_continuous", "numeric_discrete"):
                ax.scatter(df[col], df[target], s=8, alpha=0.4, color="#16a085")
                ax.set_xlabel(col)
                ax.set_ylabel(target)
                ax.set_title(f"{col} vs {target}")
            else:
                data = [df.loc[df[target].astype(str) == str(g), col].dropna()
                        for g in df[target].astype(str).value_counts().head(8).index]
                _boxplot(ax, data, tick_labels=[str(g)[:12] for g in df[target].astype(str).value_counts().head(8).index])
                ax.set_title(f"{col} by {target}")
                plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
            _rec(_finish_fig(fig, f"target_vs_{_slug(col)}", plots_dir, show))

    # ── Time-series views ─────────────────────────────────────────────────────
    if time_col and time_col in df.columns:
        _rec_all = _time_series_plots(df, numeric, cfg, target, time_col, plots_dir, show)
        saved.extend(_rec_all)

    # ── Pairplot on a small numeric subset ────────────────────────────────────
    if _HAS_SNS and len(numeric) >= 2:
        subset = numeric[: cfg.pairplot_max_cols]
        try:
            hue = target if (target in categorical or prof_by_name.get(target, {}).get("semantic_type") == "boolean") else None
            g = sns.pairplot(df[subset + ([target] if hue else [])].dropna(), hue=hue, corner=True,
                             plot_kws={"s": 12, "alpha": 0.4})
            if plots_dir is not None:
                p = plots_dir / "pairplot.png"
                g.savefig(p, dpi=100)
                saved.append(str(p))
            if not show:
                plt.close("all")
        except Exception as exc:
            log.debug("pairplot skipped: %s", exc)

    return saved


def _time_series_plots(df, numeric, cfg, target, time_col, plots_dir, show) -> list[str]:
    saved: list[str] = []
    ts = df.copy()
    ts[time_col] = pd.to_datetime(ts[time_col], errors="coerce")
    ts = ts.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)

    focus = [target] if (target in numeric) else numeric[:4]
    focus = [c for c in focus if c in numeric][:4]

    for col in focus:
        series = ts[col].dropna().astype(float)
        if series.empty:
            continue
        fig, ax = plt.subplots(figsize=(11, 3.8))
        series.plot(ax=ax, color="#2c3e50", lw=0.8, label=col)
        # Rolling mean for trend.
        win = max(len(series) // 50, 2)
        series.rolling(win, min_periods=1).mean().plot(ax=ax, color="#e67e22", lw=1.6, label=f"rolling mean ({win})")
        ax.set_title(f"Time series — {col}")
        ax.legend()
        p = _finish_fig(fig, f"ts_{_slug(col)}", plots_dir, show)
        if p:
            saved.append(str(p))

        # Autocorrelation.
        acf = _autocorrelation(series.values, cfg.max_lags)
        if acf is not None:
            fig, ax = plt.subplots(figsize=(9, 3.2))
            ax.stem(range(len(acf)), acf)
            ax.set_title(f"Autocorrelation — {col}")
            ax.set_xlabel("lag")
            p = _finish_fig(fig, f"acf_{_slug(col)}", plots_dir, show)
            if p:
                saved.append(str(p))

        # Seasonal decomposition (optional).
        if _HAS_STATSMODELS and len(series) >= 24:
            try:
                from statsmodels.tsa.seasonal import seasonal_decompose

                freq = _guess_seasonal_period(series)
                if freq and len(series) >= 2 * freq:
                    dec = seasonal_decompose(series.asfreq(series.index.inferred_freq or "D").interpolate()
                                             if series.index.inferred_freq else series,
                                             period=freq, model="additive", extrapolate_trend="freq")
                    fig = dec.plot()
                    fig.set_size_inches(11, 7)
                    fig.suptitle(f"Seasonal decomposition — {col} (period={freq})")
                    p = _finish_fig(fig, f"decompose_{_slug(col)}", plots_dir, show)
                    if p:
                        saved.append(str(p))
            except Exception as exc:
                log.debug("decompose skipped for %s: %s", col, exc)
    return saved


def _autocorrelation(x: np.ndarray, max_lags: int) -> Optional[np.ndarray]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 10:
        return None
    x = x - x.mean()
    denom = np.dot(x, x)
    if denom == 0:
        return None
    lags = min(max_lags, n - 1)
    return np.array([np.dot(x[: n - k], x[k:]) / denom for k in range(lags + 1)])


def _guess_seasonal_period(series: pd.Series) -> Optional[int]:
    freq = series.index.inferred_freq
    mapping = {"D": 7, "B": 5, "H": 24, "M": 12, "MS": 12, "W": 52, "Q": 4, "QS": 4}
    if freq:
        for k, v in mapping.items():
            if freq.startswith(k):
                return v
    return None


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(name))[:40]


def _boxplot(ax, data, *, horizontal: bool = False, tick_labels=None, **extra):
    """Matplotlib boxplot across API versions (3.11 renamed vert/labels)."""
    try:  # new API (matplotlib >= 3.9/3.11)
        kw = dict(extra)
        if horizontal:
            kw["orientation"] = "horizontal"
        if tick_labels is not None:
            kw["tick_labels"] = tick_labels
        return ax.boxplot(data, **kw)
    except TypeError:  # old API
        kw = dict(extra)
        if horizontal:
            kw["vert"] = False
        if tick_labels is not None:
            kw["labels"] = tick_labels
        return ax.boxplot(data, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# Step 6 — Study correlations
# ══════════════════════════════════════════════════════════════════════════════
def cramers_v(x: pd.Series, y: pd.Series) -> Optional[float]:
    """Bias-corrected Cramér's V for two categorical variables."""
    try:
        confusion = pd.crosstab(x, y)
        if confusion.size == 0 or confusion.shape[0] < 2 or confusion.shape[1] < 2:
            return None
        chi2 = _chi2(confusion.values)
        n = confusion.values.sum()
        phi2 = chi2 / n
        r, k = confusion.shape
        phi2corr = max(0, phi2 - (k - 1) * (r - 1) / (n - 1))
        rcorr = r - (r - 1) ** 2 / (n - 1)
        kcorr = k - (k - 1) ** 2 / (n - 1)
        denom = min(kcorr - 1, rcorr - 1)
        return float(np.sqrt(phi2corr / denom)) if denom > 0 else None
    except Exception:
        return None


def _chi2(observed: np.ndarray) -> float:
    if _HAS_SCIPY:
        return float(scipy_stats.chi2_contingency(observed)[0])
    total = observed.sum()
    row = observed.sum(axis=1, keepdims=True)
    col = observed.sum(axis=0, keepdims=True)
    expected = row @ col / total
    with np.errstate(divide="ignore", invalid="ignore"):
        chi = np.where(expected > 0, (observed - expected) ** 2 / expected, 0.0)
    return float(chi.sum())


def correlation_ratio(categories: pd.Series, values: pd.Series) -> Optional[float]:
    """Correlation ratio (η) measuring categorical → numeric association."""
    try:
        df = pd.DataFrame({"c": categories, "v": pd.to_numeric(values, errors="coerce")}).dropna()
        if df.empty or df["c"].nunique() < 2:
            return None
        grand = df["v"].mean()
        ss_between = df.groupby("c")["v"].apply(lambda g: len(g) * (g.mean() - grand) ** 2).sum()
        ss_total = ((df["v"] - grand) ** 2).sum()
        return float(np.sqrt(ss_between / ss_total)) if ss_total > 0 else None
    except Exception:
        return None


def correlations(
    df: pd.DataFrame,
    profiles: list[dict[str, Any]],
    cfg: ExploreConfig,
    *,
    target: Optional[str] = None,
) -> dict[str, Any]:
    """Numeric (Pearson+Spearman), categorical (Cramér's V), mixed (η), + target."""
    numeric = [p["name"] for p in profiles if p["semantic_type"] in ("numeric_continuous", "numeric_discrete")]
    categorical = [p["name"] for p in profiles if p["semantic_type"] in ("categorical", "boolean")]

    out: dict[str, Any] = {
        "pearson": None, "spearman": None,
        "high_correlation_pairs": [], "cramers_v": {}, "eta": {},
        "target_correlations": {},
    }

    num_df = df[numeric[: cfg.max_corr_columns]].apply(pd.to_numeric, errors="coerce")
    if num_df.shape[1] >= 2:
        pear = num_df.corr(method="pearson")
        spear = num_df.corr(method="spearman")
        out["pearson"] = pear.round(4)
        out["spearman"] = spear.round(4)
        # Multicollinearity pairs.
        cols = pear.columns
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                r = pear.iloc[i, j]
                if pd.notna(r) and abs(r) >= cfg.high_corr_threshold:
                    out["high_correlation_pairs"].append(
                        {"a": cols[i], "b": cols[j], "pearson": round(float(r), 4)}
                    )

    # Categorical ↔ categorical.
    for i, a in enumerate(categorical):
        for b in categorical[i + 1:]:
            v = cramers_v(df[a], df[b])
            if v is not None and v >= 0.5:
                out["cramers_v"][f"{a} ~ {b}"] = round(v, 4)

    # Target-centric associations.
    if target and target in df.columns:
        tprof = next((p for p in profiles if p["name"] == target), {})
        tsem = tprof.get("semantic_type")
        tc: dict[str, float] = {}
        if tsem in ("numeric_continuous", "numeric_discrete"):
            ty = pd.to_numeric(df[target], errors="coerce")
            for col in numeric:
                if col == target:
                    continue
                r = num_df[col].corr(ty) if col in num_df else pd.to_numeric(df[col], errors="coerce").corr(ty)
                if pd.notna(r):
                    tc[col] = round(float(r), 4)
            for col in categorical:
                e = correlation_ratio(df[col], df[target])
                if e is not None:
                    out["eta"][f"{col} → {target}"] = round(e, 4)
        else:  # categorical target
            for col in numeric:
                e = correlation_ratio(df[target], df[col])
                if e is not None:
                    tc[col] = round(e, 4)  # η: numeric feature explains categorical target
            for col in categorical:
                if col == target:
                    continue
                v = cramers_v(df[col], df[target])
                if v is not None:
                    out["cramers_v"][f"{col} ~ {target}"] = round(v, 4)
        out["target_correlations"] = dict(sorted(tc.items(), key=lambda kv: abs(kv[1]), reverse=True))

    return out


def plot_correlation_heatmap(corr: dict[str, Any], plots_dir: Optional[Path], show: bool) -> Optional[str]:
    if not _HAS_MPL or corr.get("pearson") is None:
        return None
    pear = corr["pearson"]
    fig, ax = plt.subplots(figsize=(min(1 + 0.5 * len(pear), 16), min(1 + 0.5 * len(pear), 14)))
    if _HAS_SNS:
        sns.heatmap(pear, annot=len(pear) <= 15, fmt=".2f", cmap="coolwarm", center=0, ax=ax, square=True)
    else:
        im = ax.imshow(pear.values, cmap="coolwarm", vmin=-1, vmax=1)
        ax.set_xticks(range(len(pear))); ax.set_xticklabels(pear.columns, rotation=90)
        ax.set_yticks(range(len(pear))); ax.set_yticklabels(pear.index)
        fig.colorbar(im)
    ax.set_title("Pearson correlation heatmap")
    p = _finish_fig(fig, "correlation_heatmap", plots_dir, show)
    return str(p) if p else None


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Build a Jupyter notebook that records the exploration
# ══════════════════════════════════════════════════════════════════════════════
def _nb_cell(cell_type: str, source: str) -> dict[str, Any]:
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }
    if cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


def build_notebook(
    dataset_path: Path,
    out_dir: Path,
    cfg: ExploreConfig,
    *,
    target: Optional[str],
    time_col: Optional[str],
) -> Path:
    """
    Emit a self-contained ``.ipynb`` (step 2). It re-imports THIS module and
    re-runs the same engine so the notebook is a faithful, reproducible record.
    """
    script_dir = str(Path(__file__).resolve().parent)
    # Absolute so the notebook works regardless of the kernel's working dir
    # (nbclient runs the kernel from the notebook's own directory).
    dataset_abs = str(Path(dataset_path).resolve())
    tgt = repr(target) if target else "None"
    tcol = repr(time_col) if time_col else "None"

    cells: list[dict[str, Any]] = []
    md = lambda s: cells.append(_nb_cell("markdown", textwrap.dedent(s).strip() + "\n"))
    code = lambda s: cells.append(_nb_cell("code", textwrap.dedent(s).strip() + "\n"))

    md(f"""
    # Data Exploration — `{dataset_path.name}`

    Auto-generated record of ML checklist **steps 1–6** (explore the data).
    Re-run top-to-bottom to reproduce. Generated {datetime.now():%Y-%m-%d %H:%M}.
    """)

    code(f"""
    import sys
    sys.path.insert(0, r"{script_dir}")
    import explore_dataset as ed
    import pandas as pd
    %matplotlib inline

    DATASET_PATH = r"{dataset_abs}"
    TARGET       = {tgt}
    TIME_COL     = {tcol}
    cfg = ed.ExploreConfig()
    """)

    md("## Step 1 — Load & copy the data (sampled if large)")
    code("""
    df, meta = ed.load_dataset(ed.Path(DATASET_PATH), cfg, time_col=TIME_COL)
    TIME_COL = TIME_COL or meta["detected_time_column"]
    meta
    """)
    code("df.head()")

    md("## Step 3 — Study each attribute\n"
       "Name · type · % missing · noise/outliers · usefulness · distribution.")
    code("""
    profiles = ed.profile_dataset(df, cfg)
    summary = ed.profile_to_frame(profiles)
    summary
    """)
    code("""
    # Full detail for any single attribute:
    import json
    print(json.dumps(profiles[0], indent=2, default=str))
    """)

    md("## Step 4 — Identify the target attribute(s)")
    code("""
    targets = ed.suggest_targets(df, profiles, cfg,
                                 explicit=[TARGET] if TARGET else None)
    TARGET = (targets["targets"] or [None])[0]
    targets
    """)

    md("## Step 5 — Visualize the data\n"
       "Adapts to detected types (numeric, categorical, target, time series).")
    code("""
    _ = ed.visualize(df, profiles, cfg, target=TARGET, time_col=TIME_COL,
                     plots_dir=None, show=True)
    """)

    md("## Step 6 — Study the correlations")
    code("""
    corr = ed.correlations(df, profiles, cfg, target=TARGET)
    corr["pearson"]
    """)
    code("""
    _ = ed.plot_correlation_heatmap(corr, plots_dir=None, show=True)
    """)
    code("""
    print("Multicollinear pairs (|r| >= %.2f):" % cfg.high_corr_threshold)
    for pr in corr["high_correlation_pairs"]:
        print(" ", pr)
    print("\\nTop associations with target:")
    for k, v in list(corr["target_correlations"].items())[:15]:
        print(f"  {k}: {v}")
    """)

    md("""
    ---
    *Steps 7–10 (solve manually · promising transforms · extra data ·
    document learnings) are intentionally left for later.*
    """)

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    nb_path = out_dir / "data_exploration.ipynb"
    out_dir.mkdir(parents=True, exist_ok=True)
    nb_path.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
    return nb_path


def execute_notebook(nb_path: Path) -> bool:
    """Execute the notebook in place so outputs are embedded (best-effort)."""
    if not _HAS_NBFORMAT:
        log.warning("nbformat not installed — cannot execute notebook.")
        return False
    try:
        # On Windows the default Proactor loop breaks pyzmq/jupyter_client;
        # the selector loop is required for the kernel to talk to nbclient.
        if sys.platform == "win32":
            try:
                import asyncio

                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass

        import nbformat
        from nbclient import NotebookClient

        nb = nbformat.read(nb_path, as_version=4)
        client = NotebookClient(nb, timeout=600, kernel_name="python3",
                                resources={"metadata": {"path": str(nb_path.parent)}})
        client.execute()
        nbformat.write(nb, nb_path)
        return True
    except Exception as exc:
        log.warning("Notebook execution failed: %s", exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════════════════
def _df_to_md(df: pd.DataFrame) -> str:
    """Markdown table via tabulate if present, else a fenced fixed-width table."""
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _jsonable(obj):
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def write_report(
    out_dir: Path,
    meta: dict,
    profiles: list[dict],
    targets: dict,
    corr: dict,
    figures: list[str],
    cfg: ExploreConfig,
) -> tuple[Path, Path]:
    # Machine-readable profile.
    json_path = out_dir / "profile.json"
    json_path.write_text(
        json.dumps(
            {"meta": meta, "config": asdict(cfg), "profiles": profiles,
             "targets": targets,
             "correlations": {k: (v.to_dict() if isinstance(v, pd.DataFrame) else v)
                              for k, v in corr.items()}},
            indent=2, default=_jsonable,
        ),
        encoding="utf-8",
    )

    # Human-readable markdown.
    md = out_dir / "REPORT.md"
    lines = [
        f"# Data Exploration Report — `{Path(meta['path']).name}`",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M}_\n",
        "## 1. Data & sampling",
        f"- Original: **{meta['original_rows']:,} rows × {meta['original_columns']} cols**",
        f"- Working copy: **{meta['working_rows']:,} rows** — sampling: {meta['sample_method']}",
        f"- Detected time column: `{meta['detected_time_column']}`\n",
        "## 3. Attribute profile",
        "",
        _df_to_md(profile_to_frame(profiles)),
        "",
        "## 4. Target suggestion",
        f"- Target(s): **{targets['targets'] or 'none detected'}** "
        f"({'explicit' if targets['explicit'] else 'heuristic guess — confirm!'})",
    ]
    for col, d in targets.get("details", {}).items():
        lines.append(f"  - `{col}` → {d['suggested_problem_type']} ({d['n_classes_or_unique']} unique)")

    lines += ["", "## 6. Correlations"]
    if corr.get("high_correlation_pairs"):
        lines.append(f"- **Multicollinear pairs (|r| ≥ {cfg.high_corr_threshold}):**")
        for pr in corr["high_correlation_pairs"]:
            lines.append(f"  - `{pr['a']}` ↔ `{pr['b']}`: r = {pr['pearson']}")
    if corr.get("target_correlations"):
        lines.append("- **Top associations with target:**")
        for k, v in list(corr["target_correlations"].items())[:15]:
            lines.append(f"  - `{k}`: {v}")

    if figures:
        lines += ["", "## 5. Figures", ""]
        lines += [f"- `{Path(f).relative_to(out_dir) if out_dir in Path(f).parents else f}`" for f in figures]

    lines += ["", "---", "_Steps 7–10 intentionally deferred._"]
    md.write_text("\n".join(str(x) for x in lines), encoding="utf-8")
    return json_path, md


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════════
def explore(
    dataset_path: str | Path,
    *,
    target: Optional[str] = None,
    time_col: Optional[str] = None,
    output_dir: Optional[str | Path] = None,
    cfg: Optional[ExploreConfig] = None,
    sep: Optional[str] = None,
    sheet: Optional[str] = None,
    make_notebook: bool = True,
    execute_nb: bool = False,
    make_plots: bool = True,
) -> dict[str, Any]:
    """Run steps 1–6 end-to-end and write all artifacts. Returns a result dict."""
    cfg = cfg or ExploreConfig()
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(path)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir) if output_dir else Path("eda_output") / f"{path.stem}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = out_dir / "plots" if make_plots else None

    log.info("Step 1 - loading %s", path)
    df, meta = load_dataset(path, cfg, sep=sep, sheet=sheet, time_col=time_col)
    time_col = time_col or meta["detected_time_column"]
    copy_path = save_working_copy(df, out_dir)
    meta["working_copy"] = str(copy_path)

    log.info("Step 3 - profiling %d attributes", df.shape[1])
    profiles = profile_dataset(df, cfg)

    log.info("Step 4 - identifying target")
    targets = suggest_targets(df, profiles, cfg, explicit=[target] if target else None)
    chosen_target = (targets["targets"] or [None])[0]

    figures: list[str] = []
    if make_plots:
        log.info("Step 5 - visualizing")
        figures = visualize(df, profiles, cfg, target=chosen_target,
                            time_col=time_col, plots_dir=plots_dir, show=False)

    log.info("Step 6 - correlations")
    corr = correlations(df, profiles, cfg, target=chosen_target)
    if make_plots:
        hm = plot_correlation_heatmap(corr, plots_dir, show=False)
        if hm:
            figures.append(hm)

    json_path, md_path = write_report(out_dir, meta, profiles, targets, corr, figures, cfg)

    nb_path = None
    if make_notebook:
        log.info("Step 2 - writing notebook")
        nb_path = build_notebook(path, out_dir, cfg, target=chosen_target, time_col=time_col)
        if execute_nb:
            execute_notebook(nb_path)

    return {
        "output_dir": str(out_dir),
        "meta": meta,
        "profiles": profiles,
        "targets": targets,
        "correlations": corr,
        "figures": figures,
        "report_json": str(json_path),
        "report_md": str(md_path),
        "notebook": str(nb_path) if nb_path else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Adaptive EDA (checklist steps 1–6) for any dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("dataset", help="Path to the dataset (csv/tsv/xlsx/json/jsonl/parquet/feather).")
    p.add_argument("--target", help="Target column(s), comma-separated. Auto-suggested if omitted.")
    p.add_argument("--time-col", help="Datetime/ordering column to unlock time-series analysis.")
    p.add_argument("--output-dir", help="Where to write artifacts. Default: eda_output/<name>_<timestamp>.")
    p.add_argument("--sample-rows", type=int, default=100_000, help="Cap the exploration copy at N rows.")
    p.add_argument("--sample-frac", type=float, help="Explicit sampling fraction (overrides --sample-rows).")
    p.add_argument("--sep", help="CSV separator override (auto for .tsv).")
    p.add_argument("--sheet", help="Excel sheet name/index.")
    p.add_argument("--seed", type=int, default=42, help="Random seed for sampling.")
    p.add_argument("--no-notebook", action="store_true", help="Skip generating the Jupyter notebook.")
    p.add_argument("--execute-notebook", action="store_true", help="Execute the notebook after building it.")
    p.add_argument("--no-plots", action="store_true", help="Skip rendering figures.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    cfg = ExploreConfig(
        sample_rows=args.sample_rows,
        sample_frac=args.sample_frac,
        seed=args.seed,
    )
    target = args.target.split(",")[0].strip() if args.target else None

    result = explore(
        args.dataset,
        target=target,
        time_col=args.time_col,
        output_dir=args.output_dir,
        cfg=cfg,
        sep=args.sep,
        sheet=args.sheet,
        make_notebook=not args.no_notebook,
        execute_nb=args.execute_notebook,
        make_plots=not args.no_plots,
    )

    line = "=" * 70
    print("\n" + line)
    print(f"[OK] Exploration complete -> {result['output_dir']}")
    print(f"  - Report (md):    {result['report_md']}")
    print(f"  - Profile (json): {result['report_json']}")
    if result["notebook"]:
        print(f"  - Notebook:       {result['notebook']}")
    print(f"  - Figures:        {len(result['figures'])} saved")
    if result["targets"]["targets"]:
        print(f"  - Target guess:   {result['targets']['targets']} "
              f"({'confirmed' if result['targets']['explicit'] else 'heuristic - verify'})")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
