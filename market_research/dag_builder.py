"""Builds a hypothesized causal factor graph (DAG) over the dataset's key
variables plus external market factors surfaced by research. Not every
dataset supports this -- if there's insufficient structured signal, or the
LLM's proposal collapses after cycle removal, this returns (None, reason)
so the caller can skip rendering a DAG entirely."""

from __future__ import annotations

import networkx as nx

from .llm_client import chat_json
from .models import CausalDag, DagEdge, DagNode, DataProfile, MarketResearchReport

_MIN_CANDIDATE_VARIABLES = 2
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_DAG_NODE_TYPES = {"dataset_variable", "external_factor"}
_DAG_CONFIDENCE_LEVELS = {"high", "medium", "low"}

_DAG_SYSTEM_PROMPT = (
    "You are a causal analysis expert. Given a dataset's variables and market research "
    "findings, propose a hypothesized causal DAG: which variables/factors plausibly cause "
    "changes in which other variables/factors. Only propose direct, defensible causal claims "
    "(not mere correlation). If the data + research don't support at least two genuine causal "
    "relationships, say so honestly instead of inventing weak ones."
)


def _candidate_columns(profile: DataProfile):
    return [c for c in profile.columns if c.role in ("numeric", "categorical", "date")]


def _build_prompt(profile: DataProfile, report: MarketResearchReport, candidates) -> str:
    column_lines = "\n".join(f"- {c.name} ({c.role}): stats={c.stats}" for c in candidates)
    finding_lines = "\n".join(f"- {f.title}: {f.detail}" for f in report.key_findings)
    opportunity_lines = "\n".join(f"- {o}" for o in report.opportunities)
    risk_lines = "\n".join(f"- {r}" for r in report.risks)

    return (
        f"Dataset domain: {profile.domain}\n"
        f"Dataset variables available as causal graph nodes:\n{column_lines}\n\n"
        f"Market research executive summary: {report.executive_summary}\n\n"
        f"Key findings:\n{finding_lines or '(none)'}\n\n"
        f"Opportunities:\n{opportunity_lines or '(none)'}\n\n"
        f"Risks:\n{risk_lines or '(none)'}\n\n"
        "Return JSON exactly in this shape:\n"
        "{\n"
        '  "feasible": true or false,\n'
        '  "reason": "why feasible, or why not enough causal signal exists",\n'
        '  "nodes": [{"id": "short_slug", "label": "Human readable", '
        '"type": "dataset_variable|external_factor", "description": "..."}],\n'
        '  "edges": [{"source": "id", "target": "id", "relationship": "short causal claim, '
        'e.g. increases/decreases/delays", "rationale": "...", "confidence": "high|medium|low"}]\n'
        "}\n"
        "Rules:\n"
        "- Use dataset_variable nodes only for the variables listed above (id = a slug derived "
        "from the column name).\n"
        "- Use external_factor nodes for market forces identified in the research (e.g. "
        "seasonality, competitor pricing, input costs).\n"
        "- Max 12 nodes and 15 edges.\n"
        "- Do not include both A->B and B->A.\n"
        "- Set feasible=false if you cannot justify at least 2 real causal edges."
    )


def _parse_llm_dag(result: dict) -> tuple[list[DagNode], list[DagEdge]]:
    raw_nodes = result.get("nodes", []) or []
    nodes = []
    seen_ids = set()
    for n in raw_nodes:
        node_id = n.get("id")
        node_type = n.get("type")
        if not node_id or node_id in seen_ids or node_type not in _DAG_NODE_TYPES:
            continue
        seen_ids.add(node_id)
        nodes.append(
            DagNode(id=node_id, label=n.get("label", node_id), type=node_type, description=n.get("description"))
        )

    node_ids = {n.id for n in nodes}
    edges = []
    for e in result.get("edges", []) or []:
        source, target = e.get("source"), e.get("target")
        if not source or not target or source == target:
            continue
        if source not in node_ids or target not in node_ids:
            continue
        confidence = e.get("confidence") if e.get("confidence") in _DAG_CONFIDENCE_LEVELS else "medium"
        edges.append(
            DagEdge(
                source=source,
                target=target,
                relationship=e.get("relationship", "influences"),
                rationale=e.get("rationale", ""),
                confidence=confidence,
            )
        )
    return nodes, edges


def _make_acyclic(nodes: list[DagNode], edges: list[DagEdge]) -> tuple[list[DagNode], list[DagEdge]]:
    graph = nx.DiGraph()
    graph.add_nodes_from(n.id for n in nodes)
    for e in edges:
        graph.add_edge(e.source, e.target)

    remaining = list(edges)
    while not nx.is_directed_acyclic_graph(graph):
        try:
            cycle = nx.find_cycle(graph)
        except nx.NetworkXNoCycle:
            break
        cycle_pairs = {(u, v) for u, v, *_ in cycle}
        candidates = [e for e in remaining if (e.source, e.target) in cycle_pairs]
        if not candidates:
            break
        weakest = min(candidates, key=lambda e: _CONFIDENCE_RANK.get(e.confidence, 1))
        remaining.remove(weakest)
        graph.remove_edge(weakest.source, weakest.target)

    used_ids = {e.source for e in remaining} | {e.target for e in remaining}
    kept_nodes = [n for n in nodes if n.id in used_ids]
    return kept_nodes, remaining


def build_causal_dag(profile: DataProfile, report: MarketResearchReport) -> tuple[CausalDag | None, str | None]:
    candidates = _candidate_columns(profile)
    if len(candidates) < _MIN_CANDIDATE_VARIABLES:
        return None, "Dataset doesn't have enough structured (numeric/categorical/date) variables to hypothesize causal relationships."

    prompt = _build_prompt(profile, report, candidates)
    result = chat_json(_DAG_SYSTEM_PROMPT, prompt)

    if not result.get("feasible", False):
        return None, result.get("reason", "The model determined there wasn't enough causal signal in this dataset.")

    nodes, edges = _parse_llm_dag(result)
    nodes, edges = _make_acyclic(nodes, edges)

    if len(nodes) < 2 or not edges:
        return None, "The proposed causal graph didn't hold up after removing cyclic/invalid edges."

    return CausalDag(nodes=nodes, edges=edges), None
