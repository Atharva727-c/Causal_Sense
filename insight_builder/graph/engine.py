"""A minimal explicit state-graph runtime for the insight pipeline.

Why this exists instead of a hand-written function pipeline or an agentic
tool loop:

- Every stage is a named node over one shared, inspectable state dict, so
  the workflow *is* the documentation: `graph.describe()` returns the real
  execution plan, and every run returns a per-node trace (status, timing,
  failure detail) that can be shown in a UI or attached to an audit dir.
- Conditional nodes make optional capabilities (LLM domain knowledge,
  market-research enrichment) first-class: a node whose condition is false
  is *skipped and recorded as skipped*, not silently absent.
- `optional=True` nodes are error-isolated: an LLM outage or a malformed
  artifact fails that node only; the pipeline still produces a report from
  whatever the deterministic nodes computed.

Deliberately NOT here: LLM-driven control flow, cycles, or dynamic node
creation. Control flow stays deterministic and data-driven so two runs on
the same inputs execute the same plan — the property the statistical gates
(multiple-comparison correction over a *fixed* candidate batch) rely on.

Nodes are functions `state -> dict of state updates` (or None). `after`
lists express dependencies; execution order is a stable topological sort.
Conditions read state, never node statuses, so a skipped upstream producer
simply leaves its keys absent and downstream consumers see empty defaults.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

NodeFn = Callable[[dict[str, Any]], dict[str, Any] | None]
Condition = Callable[[dict[str, Any]], bool]


class GraphDefinitionError(ValueError):
    pass


class NodeExecutionError(RuntimeError):
    def __init__(self, node: str, cause: Exception):
        super().__init__(f"node '{node}' failed: {cause}")
        self.node = node
        self.cause = cause


@dataclass
class Node:
    name: str
    fn: NodeFn
    after: tuple[str, ...] = ()
    condition: Condition | None = None
    condition_label: str | None = None
    optional: bool = False


@dataclass
class NodeTrace:
    node: str
    status: str  # "ok" | "skipped" | "failed"
    duration_ms: int = 0
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"node": self.node, "status": self.status, "duration_ms": self.duration_ms}
        if self.detail:
            out["detail"] = self.detail
        return out


@dataclass
class StateGraph:
    name: str = "graph"
    _nodes: dict[str, Node] = field(default_factory=dict)

    def add_node(
        self,
        name: str,
        fn: NodeFn,
        *,
        after: tuple[str, ...] | list[str] = (),
        condition: Condition | None = None,
        condition_label: str | None = None,
        optional: bool = False,
    ) -> "StateGraph":
        if name in self._nodes:
            raise GraphDefinitionError(f"duplicate node name: {name}")
        for dep in after:
            if dep not in self._nodes:
                raise GraphDefinitionError(f"node '{name}' depends on unknown node '{dep}'")
        self._nodes[name] = Node(
            name=name, fn=fn, after=tuple(after),
            condition=condition, condition_label=condition_label, optional=optional,
        )
        return self

    def _topo_order(self) -> list[Node]:
        # add_node already requires dependencies to be declared first, so
        # insertion order is a valid topological order — kept as a distinct
        # method so the invariant is stated (and checked) in one place.
        seen: set[str] = set()
        for node in self._nodes.values():
            if any(dep not in seen for dep in node.after):
                raise GraphDefinitionError(f"node '{node.name}' ordered before a dependency")
            seen.add(node.name)
        return list(self._nodes.values())

    def describe(self) -> list[dict[str, Any]]:
        """The execution plan as data — usable in docs, tests, or a UI."""
        return [
            {
                "node": n.name,
                "after": list(n.after),
                "conditional": n.condition_label if n.condition else None,
                "optional": n.optional,
            }
            for n in self._topo_order()
        ]

    def run(self, state: dict[str, Any]) -> tuple[dict[str, Any], list[NodeTrace]]:
        traces: list[NodeTrace] = []
        for node in self._topo_order():
            if node.condition is not None and not node.condition(state):
                traces.append(NodeTrace(node.name, "skipped", detail=node.condition_label))
                continue

            started = time.perf_counter()
            try:
                updates = node.fn(state)
            except Exception as exc:
                duration = int((time.perf_counter() - started) * 1000)
                if not node.optional:
                    raise NodeExecutionError(node.name, exc) from exc
                detail = f"{type(exc).__name__}: {exc}"
                traces.append(NodeTrace(node.name, "failed", duration, detail))
                # Full traceback stays out of the report but is recoverable:
                state.setdefault("_node_errors", {})[node.name] = traceback.format_exc()
                continue

            duration = int((time.perf_counter() - started) * 1000)
            if updates:
                state.update(updates)
            traces.append(NodeTrace(node.name, "ok", duration))
        return state, traces
