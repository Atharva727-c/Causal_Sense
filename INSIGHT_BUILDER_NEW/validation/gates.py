"""The three gates: raw significance -> meaningful effect size -> survives batch correction.

Nothing here is an LLM call — this is pure statistics.
"""
from __future__ import annotations

from typing import Any

ALPHA = 0.05

MIN_EFFECT_SIZE = {
    "cohens_d": 0.2,
    "eta_squared": 0.06,
    "abs_r": 0.10,
    "abs_rho": 0.10,
    "cramers_v": 0.10,
}


def gate_1_significant(result: dict[str, Any]) -> bool:
    p = result.get("p_value")
    return p is not None and p < ALPHA


def gate_2_meaningful(result: dict[str, Any]) -> bool:
    effect_name = result.get("effect_name")
    effect_size = result.get("effect_size")
    if effect_name is None or effect_size is None:
        return False
    threshold = MIN_EFFECT_SIZE.get(effect_name, 0.1)
    return effect_size >= threshold


def benjamini_hochberg(p_values: list[float], alpha: float = ALPHA) -> list[bool]:
    """Returns a per-candidate pass/fail mask after BH correction across the whole batch."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(range(m), key=lambda i: p_values[i])
    passed = [False] * m
    largest_rank_passed = -1
    for rank, idx in enumerate(indexed, start=1):
        threshold = (rank / m) * alpha
        if p_values[idx] <= threshold:
            largest_rank_passed = rank
    for rank, idx in enumerate(indexed, start=1):
        passed[idx] = rank <= largest_rank_passed
    return passed


def apply_gates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Runs all three gates in order; returns only validated insights, each carrying its rank_score."""
    stage1 = [r for r in results if "error" not in r and gate_1_significant(r)]
    stage2 = [r for r in stage1 if gate_2_meaningful(r)]

    if not stage2:
        return []

    p_values = [r["p_value"] for r in stage2]
    bh_mask = benjamini_hochberg(p_values)

    validated = []
    for r, passed in zip(stage2, bh_mask):
        if not passed:
            continue
        r["rank_score"] = (1 - r["p_value"]) * r["effect_size"]
        validated.append(r)

    validated.sort(key=lambda r: r["rank_score"], reverse=True)
    return validated
