# CausalSense — Documentation

This folder contains the full technical documentation for the CausalSense platform:
its architecture, every component, and how each feature works end to end.

For **installation and running the project**, see the [root README](../README.md).

## Contents

| # | Document | Covers |
|---|---|---|
| 01 | [Architecture Overview](01-architecture-overview.md) | The whole system, components, data flow, and the four features |
| 02 | [Frontend](02-frontend.md) | React 19 chat UI, components, hooks, result renderers |
| 03 | [FastAPI Backend](03-fastapi-backend.md) | The primary API — routers, services, agent framework, DB |
| 04 | [EDA Pipeline](04-eda-pipeline.md) | Notebook-driven exploratory analysis with a ReAct follow-up agent |
| 05 | [Insight Builder](05-insight-builder.md) | Deterministic statistical-insight state graph |
| 06 | [Market Research](06-market-research.md) | LLM + web-search domain research and causal DAG builder |
| 07 | [Data & Storage](07-data-and-storage.md) | SQLite schema, file storage, EDA workspace, the `output.json` contract |
| 08 | [API Reference](08-api-reference.md) | Every HTTP endpoint across all services |

## The one-paragraph summary

CausalSense turns a raw tabular dataset into validated, causal, business-ready insight.
A React chat UI (port 5173) talks to a FastAPI backend (port 8001) that orchestrates four
features: **EDA** (an autonomous notebook-exploration agent), **Market Research** (LLM +
Tavily web search producing a domain report and a causal DAG), **Insight Builder** (a
deterministic state graph that generates, statistically validates, and narrates insights),
and **Causal Analysis** (a chain that runs all three and fuses them into one causal report).
Every number shown to the user comes from code that actually executed on the data — the LLM
interprets and narrates, but never computes.

## Design principles that recur across the codebase

- **No hallucinated numbers.** Statistics are always produced by sandboxed scripts or
  notebook cells; the LLM only interprets, maps, and narrates.
- **Graceful degradation.** Every LLM-dependent path has a mock/offline fallback (mock chat,
  hashed embeddings, deterministic narration), so the app is fully demoable with no API keys.
- **Determinism where it matters.** Insight Builder is a state graph, not an agent loop, so
  the same inputs produce the same analysis plan — which is what makes batch multiple-comparison
  correction statistically valid.
- **Bounded agency at the edges.** Open-ended, user-driven questions use bounded
  generate→execute→self-correct loops with a safety blocklist and a sandbox.
- **Auditability.** Every generated script is written to disk; Insight Builder reports carry a
  per-node execution trace.
