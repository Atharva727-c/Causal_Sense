"""Turns a validated insight object into one grounded sentence.

Phase 1: deterministic string templates (no LLM call yet) so the statistical
engine can be proven correct in isolation. In later phases this function's
body is replaced by a Narrator Agent call — the input/output contract
(insight dict in, one sentence out) stays identical, so nothing upstream
needs to change when that swap happens.
"""
from __future__ import annotations

from typing import Any


def _outlier_note(insight: dict[str, Any]) -> str:
    """Rows below the 2.5th / above the 97.5th percentile are dropped before
    any computation in the templates — this states how many, so a mean/sum/
    correlation reads as computed-on-trimmed-data rather than silently."""
    removed = insight.get("outliers_removed")
    if not removed:
        return ""
    flagged = {col: n for col, n in removed.items() if n > 0}
    if not flagged:
        return ""
    parts = ", ".join(f"{n} in {col}" for col, n in flagged.items())
    return f" ({parts} outlier rows removed via 2.5/97.5 percentile trim.)"


def narrate(insight: dict[str, Any]) -> str:
    return _narrate_body(insight) + _outlier_note(insight)


def _narrate_body(insight: dict[str, Any]) -> str:
    test = insight["test"]
    cols = insight["columns"]
    label = insight.get("label")
    prefix = f"{label}: " if label else ""

    if test == "ratio":
        return f"{prefix}{cols['numerator_col']} per {cols['denominator_col']} is {insight['overall_ratio']:.2f} (n={insight['n']})."

    if test == "ratio_by_group":
        ratios = insight["group_ratios"]
        top_group = max(ratios, key=ratios.get)
        bottom_group = min(ratios, key=ratios.get)
        return (
            f"{prefix}{cols['numerator_col']} per {cols['denominator_col']} is {insight['overall_ratio']:.2f} overall, "
            f"by {cols['group_col']} it ranges from {ratios[bottom_group]:.2f} ('{bottom_group}') "
            f"to {ratios[top_group]:.2f} ('{top_group}')."
        )

    if test == "top_n":
        top = insight["top"][:5]
        top_str = ", ".join(f"'{t['group']}' ({t['sum']:.2f})" for t in top)
        return (
            f"Top {cols['categorical_col']} groups by total {cols['numeric_col']}: {top_str} "
            f"(P75={insight['overall_p75']:.2f}, P90={insight['overall_p90']:.2f}, n={insight['n']})."
        )

    if test == "concentration":
        top_groups = ", ".join(
            f"'{g['group']}' ({g['share']:.0%})" for g in insight["top_groups"][:3]
        )
        return (
            f"{cols['categorical_col']} concentration on {cols['numeric_col']}: "
            f"top {insight['top_20pct_group_count']} of {insight['n_groups']} groups (20%) drive "
            f"{insight['share_of_top_20pct_groups']:.0%} of total; "
            f"{insight['groups_for_80pct']} groups ({insight['pct_of_groups_for_80pct']:.0%} of all groups) "
            f"account for 80%. Leaders: {top_groups} (n={insight['n']})."
        )

    if test == "cross_top_n":
        cols = insight["columns"]
        parts = []
        for g in insight["group_top"][:5]:
            top = g["top"][:1]
            if not top:
                continue
            best = top[0]
            parts.append(f"'{g['group']}' -> '{best['breakdown']}' ({best['value']:.2f})")
        return (
            f"{prefix}Within {cols['group_col']}, top {cols['breakdown_col']} by total "
            f"{cols['numeric_col']}: {'; '.join(parts)} (n={insight['n']})."
        )

    p = insight["p_value"]

    if test in ("anova", "welch_t"):
        means = insight["group_means"]
        top_group = max(means, key=means.get)
        bottom_group = min(means, key=means.get)
        p75 = insight.get("group_p75", {})
        p90 = insight.get("group_p90", {})
        percentile_note = (
            f" (P75={p75[top_group]:.2f}, P90={p90[top_group]:.2f} for '{top_group}')"
            if top_group in p75 and top_group in p90 else ""
        )
        return (
            f"{cols['numeric_col']} varies significantly by {cols['categorical_col']} "
            f"(p={p:.3f}), with '{top_group}' averaging {means[top_group]:.2f} "
            f"vs '{bottom_group}' at {means[bottom_group]:.2f}{percentile_note}."
        )

    if test == "pearson":
        direction = "positively" if insight["statistic"] > 0 else "negatively"
        return (
            f"{cols['col_a']} is {direction} correlated with {cols['col_b']} "
            f"(r={insight['statistic']:.2f}, p={p:.3f})."
        )

    if test == "spearman_trend":
        half_note = ""
        if insight.get("first_half_mean") is not None and insight.get("second_half_mean") is not None:
            half_note = (
                f" (early-period mean={insight['first_half_mean']:.2f}, "
                f"recent-period mean={insight['second_half_mean']:.2f})"
            )
        return (
            f"{cols['numeric_col']} shows a significant {insight['direction']} trend "
            f"over {cols['datetime_col']} (rho={insight['statistic']:.2f}, p={p:.3f}){half_note} "
            f"[P75={insight['p75']:.2f}, P90={insight['p90']:.2f}]."
        )

    if test == "chi_square":
        return (
            f"{cols['col_a']} and {cols['col_b']} are significantly associated "
            f"(Cramer's V={insight['effect_size']:.2f}, p={p:.3f})."
        )

    return f"Validated finding on {cols} (p={p:.3f})."


def narrate_no_trend(result: dict[str, Any]) -> str:
    """For a trend candidate that was tested but didn't clear the significance/effect
    gates — states the flat/no-trend finding explicitly instead of silent omission."""
    cols = result["columns"]
    return (
        f"No significant trend detected for {cols['numeric_col']} over {cols['datetime_col']} "
        f"(rho={result['statistic']:.2f}, p={result['p_value']:.3f}) — values appear flat/noisy across the period."
    ) + _outlier_note(result)
