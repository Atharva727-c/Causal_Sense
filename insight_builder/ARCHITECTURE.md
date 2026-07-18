# Insight Builder — Architecture

## The one-line answer to "agentic or graph?"

Insight Builder is a **deterministic state graph with LLM-powered leaf nodes**,
not an agentic tool loop. The LLM never decides *what happens next*; it only
fills in judgment gaps inside fixed stages (domain knowledge, schema mapping,
question intent, narration). The graph decides control flow from data
(artifact present? LLM configured? domain known?), so two runs on the same
inputs execute the same plan.

### Why not a conventional agent loop

| Property | Agent loop (LLM + tools) | State graph (this system) |
|---|---|---|
| Reproducibility | Run-to-run plan drift | Same inputs → same plan |
| Statistical validity | Sequential, unplanned tests break batch multiple-comparison correction | Fixed candidate batch → Benjamini-Hochberg is well-defined |
| Auditability | Reconstruct from chat transcript | Every stage named, timed, traced; every script on disk |
| Cost/latency | LLM call per decision | 0–4 LLM calls per analysis, all parallelizable leaves |
| Failure isolation | One bad tool call derails the loop | Optional nodes fail/skip individually; report always produced |
| Hallucination surface | Model can assert numbers | Model never computes; all numbers from sandboxed scripts |

The place where agentic behavior *is* appropriate — open-ended, user-driven
questions — is exactly where the system already has one: the Tier-B ad-hoc
query path (`query/`), a bounded generate→execute→self-correct loop with a
safety blocklist and sandbox. Bounded agency at the edge, determinism in the
core.

## The graph

`graph/engine.py` is a ~150-line runtime: nodes are `state -> updates`
functions with declared dependencies, optional *conditions* (skip-and-record
when false) and *error isolation* (`optional=True` nodes fail without failing
the run). `orchestrator.build_insight_graph()` assembles:

```
load_dataset ─ infer_schema ─┬─ persist_coerced ──────────────┐
                             ├─ load_market_context* ─┐       │
                             ├─ generic_candidates    ├─ domain_candidates*†
                             │                        └─ dag_candidates*
                             └──── merge_candidates ── triage ── execute(parallel)
                                    ── partition ── validate(gates) ── narrate
                                    ─┬─ enrich_with_market*
                                     ├─ rank_kpis
                                     └─ executive_summary*† ── assemble_report
* conditional on the market-research artifact     † conditional on LLM config
```

Every report carries `graph_trace`: per-node status (ok/skipped/failed) and
timing — the run explains itself.

## Market Researcher integration (`context/`)

The Market Researcher's `output.json` (research report + causal DAG) is a
strictly optional input, resolved in this order: explicit path → the
`INSIGHT_MARKET_RESEARCH_PATH` env var → `output.json` next to the dataset →
absent. Absent or malformed ⇒ those nodes skip and the report notes why.

When present it contributes three things, all *annotation or candidate
generation*, never statistical evidence:

1. **Domain fallback** — its detected domain feeds the domain-knowledge agent
   when the user didn't supply one.
2. **DAG-derived hypotheses** (`context/dag_hypotheses.py`, deterministic) —
   each believed causal path between two dataset variables (directly or via
   unobserved external factors) becomes the matching observable test
   (correlation / group_diff / chi_square / trend) on real columns, labeled
   with the research rationale. The gates still decide truth: a wrong DAG
   edge can waste one test, never fabricate an insight.
3. **Insight enrichment** (`context/enricher.py`) — validated insights and
   KPI facts whose columns appear in a research finding get a
   `market_context` list (finding + source URLs), in reports and in `/chat`
   answers.

## Trust tiers (unchanged, now provenance-tagged)

- `business_fact` — arithmetic KPIs, no hypothesis test implied
- `validated` — cleared significance, effect-size, and BH-correction gates
- `not_significant` — tested, explicitly failed
- `ad_hoc_query` — Tier-B answer to a user question, not a validated finding

Insights additionally carry `source`: `generic` / `domain` / `market_dag`,
so a UI can badge where each hypothesis came from.
