"""Loads the Market Researcher artifact (output.json) into a typed context.

The artifact is strictly optional input produced by a *separate* system, so
this loader is deliberately tolerant and side-effect free: any missing file,
unparseable JSON, or unexpected shape yields None (with a recorded reason),
and the pipeline runs exactly as it would with no artifact at all. Nothing
outside this module parses the artifact's JSON.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MARKET_RESEARCH_PATH_ENV = "INSIGHT_MARKET_RESEARCH_PATH"
DEFAULT_ARTIFACT_NAME = "output.json"


@dataclass
class MarketFinding:
    title: str
    detail: str
    source_urls: list[str] = field(default_factory=list)
    # Dataset columns this finding talks about, resolved against the schema
    # once at load time so enrichment is a cheap set intersection later.
    matched_columns: set[str] = field(default_factory=set)

    def as_context(self) -> dict[str, Any]:
        out: dict[str, Any] = {"title": self.title, "detail": self.detail}
        if self.source_urls:
            out["sources"] = self.source_urls
        return out


@dataclass
class MarketDagEdge:
    source: str
    target: str
    relationship: str
    rationale: str
    confidence: str  # high | medium | low


@dataclass
class MarketContext:
    path: str
    domain: str | None
    executive_summary: str | None
    findings: list[MarketFinding]
    opportunities: list[str]
    risks: list[str]
    recommendations: list[dict[str, Any]]
    dag_nodes: dict[str, dict[str, Any]]  # node id -> {label, type, description}
    dag_edges: list[MarketDagEdge]
    # Column names the artifact's own data_profile says it was built from —
    # used to detect an artifact that describes a *different* dataset.
    profile_columns: list[str] = field(default_factory=list)

    def matches_dataset(self, column_names: list[str]) -> bool:
        """False when the artifact self-describes columns and none of them
        exist in the dataset — the signature of a stale/mismatched artifact
        (whose domain, findings, and DAG would all be about other data)."""
        if not self.profile_columns:
            return True  # artifact doesn't say; give it the benefit of the doubt
        normalize = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        dataset = {normalize(c) for c in column_names}
        return any(normalize(c) in dataset for c in self.profile_columns)

    @property
    def has_dag(self) -> bool:
        return bool(self.dag_nodes and self.dag_edges)

    def dataset_variable_ids(self) -> list[str]:
        return [nid for nid, n in self.dag_nodes.items() if n.get("type") == "dataset_variable"]

    def summary_for_report(self) -> dict[str, Any]:
        return {
            "available": True,
            "path": self.path,
            "domain": self.domain,
            "executive_summary": self.executive_summary,
            "n_key_findings": len(self.findings),
            "opportunities": self.opportunities,
            "risks": self.risks,
            "recommendations": self.recommendations,
            "dag": {
                "n_nodes": len(self.dag_nodes),
                "n_edges": len(self.dag_edges),
            } if self.has_dag else None,
        }


def resolve_artifact_path(dataset_path: str | Path, explicit_path: str | None = None) -> Path | None:
    """Where is the Market Researcher artifact for this dataset, if anywhere?
    Precedence: explicit caller path -> INSIGHT_MARKET_RESEARCH_PATH env var
    -> an output.json sitting next to the dataset. Returns None when no
    candidate exists — the caller then simply runs without market context."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env_path = os.environ.get(MARKET_RESEARCH_PATH_ENV)
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(dataset_path).parent / DEFAULT_ARTIFACT_NAME)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _finding_column_matches(text: str, column_names: list[str]) -> set[str]:
    """Columns mentioned by name in a finding's text (word-boundary,
    case-insensitive; underscores/spaces treated as equivalent)."""
    matched: set[str] = set()
    lowered = text.lower()
    for col in column_names:
        pattern = re.escape(col.lower()).replace(r"\_", r"[_\s]")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", lowered):
            matched.add(col)
    return matched


def load_market_context(path: str | Path, column_names: list[str] | None = None) -> MarketContext | None:
    """Parse the artifact; None on any structural problem. column_names, when
    given, pre-resolves which dataset columns each finding mentions."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    research = raw.get("market_research")
    if not isinstance(research, dict):
        research = {}
    profile = raw.get("data_profile")
    if not isinstance(profile, dict):
        profile = {}

    columns = column_names or []
    findings: list[MarketFinding] = []
    for item in research.get("key_findings") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        detail = str(item.get("detail") or "")
        urls = [
            s.get("url") for s in item.get("sources") or []
            if isinstance(s, dict) and s.get("url")
        ]
        findings.append(MarketFinding(
            title=str(item["title"]),
            detail=detail,
            source_urls=urls,
            matched_columns=_finding_column_matches(f"{item['title']} {detail}", columns),
        ))

    dag = raw.get("dag")
    dag_nodes: dict[str, dict[str, Any]] = {}
    dag_edges: list[MarketDagEdge] = []
    if isinstance(dag, dict):
        for node in dag.get("nodes") or []:
            if isinstance(node, dict) and node.get("id"):
                dag_nodes[str(node["id"])] = {
                    "label": node.get("label") or str(node["id"]),
                    "type": node.get("type") or "external_factor",
                    "description": node.get("description"),
                }
        for edge in dag.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            src, tgt = edge.get("source"), edge.get("target")
            if src in dag_nodes and tgt in dag_nodes:
                dag_edges.append(MarketDagEdge(
                    source=str(src), target=str(tgt),
                    relationship=str(edge.get("relationship") or ""),
                    rationale=str(edge.get("rationale") or ""),
                    confidence=str(edge.get("confidence") or "medium"),
                ))

    recommendations = [
        {
            "recommendation": r.get("recommendation"),
            "rationale": r.get("rationale"),
            "priority": r.get("priority", "medium"),
        }
        for r in research.get("recommendations") or []
        if isinstance(r, dict) and r.get("recommendation")
    ]

    profile_columns = [
        str(c["name"]) for c in profile.get("columns") or []
        if isinstance(c, dict) and c.get("name")
    ]

    domain = research.get("domain") or profile.get("domain")
    return MarketContext(
        path=str(path),
        domain=str(domain) if domain else None,
        executive_summary=research.get("executive_summary"),
        findings=findings,
        opportunities=[str(o) for o in research.get("opportunities") or []],
        risks=[str(r) for r in research.get("risks") or []],
        recommendations=recommendations,
        dag_nodes=dag_nodes,
        dag_edges=dag_edges,
        profile_columns=profile_columns,
    )
