# 05 — Insight Builder

**Path:** `insight_builder/` · **Stack:** FastAPI (mounted at `/api/insight`), NetworkX, SciPy,
Jinja2, DIAL LLM · **Companion doc:** `insight_builder/ARCHITECTURE.md`

Insight Builder is a **deterministic state graph with LLM-powered leaf nodes** — not an agent
loop. The graph decides control flow from data (artifact present? LLM configured? domain known?),
so two runs on the same inputs execute the same plan. The single LLM touchpoint is
`qa/llm_client.py`; every LLM node is conditional and error-isolated. The LLM never computes a
number — all statistics come from sandboxed subprocess scripts.

## Why a state graph, not an agent loop

| Property | Agent loop | State graph (this system) |
|---|---|---|
| Reproducibility | Run-to-run plan drift | Same inputs → same plan |
| Statistical validity | Unplanned sequential tests break multiple-comparison correction | Fixed candidate batch → Benjamini-Hochberg is well-defined |
| Auditability | Reconstruct from transcript | Every stage named, timed, traced; every script on disk |
| Cost/latency | LLM call per decision | 0–4 LLM calls per analysis, parallelizable leaves |
| Failure isolation | One bad tool call derails the loop | Optional nodes fail/skip individually; report always produced |
| Hallucination surface | Model can assert numbers | Model never computes; all numbers from sandboxed scripts |

Bounded agency *does* appear where it's appropriate — the open-ended Tier-B ad-hoc query path
(`query/`), a bounded generate→execute→self-correct loop with a safety blocklist and sandbox.

## The graph

`graph/engine.py` is a minimal explicit state-graph runtime. Nodes are `state -> dict` functions
with declared dependencies (`after`), an optional `condition` (skip-and-record when false), and
an `optional` flag (failure is recorded but does not fail the run). `run(state)` executes nodes
in insertion/topological order and returns `(state, traces)` where each `NodeTrace` is
`ok | skipped | failed` with a duration. Conditions read state only, never node statuses — a
skipped producer simply leaves its keys absent. No cycles, no dynamic nodes, no LLM control flow —
deliberately, because that is what makes batch-level FDR correction deterministic.

`orchestrator.build_insight_graph()` assembles the pipeline:

```
load_dataset ─ infer_schema ─┬─ persist_coerced ──────────────┐
                             ├─ load_market_context* ─┐        │
                             ├─ generic_candidates     ├─ domain_candidates*†
                             │                         └─ dag_candidates*
                             └──── merge_candidates ── triage ── execute (parallel)
                                    ── partition ── validate (gates) ── narrate
                                    ─┬─ enrich_with_market*
                                     ├─ rank_kpis
                                     ├─ top_insights
                                     └─ executive_summary*† ── assemble_report

  * conditional on the Market Research artifact     † conditional on LLM config
```

Every report carries `graph_trace`: per-node status and timing — the run explains itself.

## Pipeline stages

### Ingestion (`ingestion/`)
- **`loader.py`** — dataset I/O (CSV + Excel, first sheet only). `write_coerced_csv` persists the
  role-coerced dataframe as the canonical CSV **every sandboxed script reads** (datetimes as ISO).
- **`schema.py`** — **name-agnostic role inference**. Each column becomes `numeric | datetime |
  identifier | categorical | free_text` via dtype checks, currency/percent regex coercion,
  date-shape detection, and cardinality thresholds. This is the crux of the design: hypotheses
  are enumerated from column *roles*, never column *names*.

### Candidate generation
- **`hypotheses/generator.py`** — generic candidates from role *pairs*: `group_diff`
  (numeric×categorical), `correlation` (numeric pairs), `trend` (numeric×datetime), `chi_square`
  (categorical pairs), `ratio` (amount-over-count pairs), `top_n` + `concentration`
  (group×numeric), `cross_top_n` (numeric cols bundled per dimension pair).
- **`hypotheses/hierarchy.py`** — functional-dependency detection (e.g. Address→City→State) via
  union-find, so one underlying hierarchy isn't analyzed at every granularity.
- **`domain/knowledge_agent.py`** — the Domain Knowledge Agent: asks the LLM (which never sees
  data or column names) for 6–10 abstract KPI/hypothesis definitions confined to a commercial
  lane.
- **`domain/schema_mapper.py`** — the Schema Mapping Agent: binds each abstract "requires" slot
  to a real column with a confidence score, dropping low-confidence or role-mismatched mappings.
- **`context/dag_hypotheses.py`** — converts the Market Research DAG into concrete test
  candidates by matching node ids to columns and shaping each believed cause→effect path into a
  correlation/group_diff/chi_square/trend test. Deterministic, no LLM. A wrong DAG edge can waste
  one test but can never fabricate an insight.

`merge_candidates` unions the three sources and dedupes, preferring labeled variants.

### Triage → Execute
- **`hypotheses/triage.py`** — a cheap, vectorized pre-screen before expensive execution
  (correlation must clear |r| ≥ 0.10, group_diff needs ≥2 groups of ≥5, etc.). KPI/fact types
  pass through.
- **`execution/renderer.py`** — renders the Jinja2 template for each candidate type, filling only
  column names.
- **`execution/runner.py`** — runs each script as a `sys.executable` **subprocess** (120s
  timeout), persists the script to disk (auditable), and captures the last stdout line as JSON.
  `execute` fans these out on a `ThreadPoolExecutor` (8 workers).

### Validate → Narrate
- **`validation/gates.py`** — three pure-statistics gates:
  1. **Significance** — p < 0.05.
  2. **Effect size** — meets a per-metric threshold (Cohen's d 0.2, eta² 0.06, |r|/|rho|/
     Cramér's V 0.10).
  3. **Benjamini-Hochberg** — batch FDR correction across the whole candidate set.

  Validated insights are sorted by `rank_score = (1 - p) * effect_size`. Nothing is dropped
  silently — results bucket into validated / not_significant / failed_tests.
- **`narration/narrator.py`** — deterministic string templates per test type, plus an
  outlier-trim note; explicitly narrates null and failed results too.
- **`context/enricher.py`** — annotation-only: attaches up to 2 matching market findings to an
  insight; never mutates statistics.
- **`context/summary.py`** — one optional LLM pass over already-computed narratives to write an
  executive summary (never sees raw numbers to invent from).
- **`kpi_ranking.py`** — ranks business-fact KPIs by a type-specific concentration/skew score,
  discounts tiny-sample leaders, and spreads coverage across dimensions/metrics.

## Statistical-test templates (`templates/*.py.j2`)

Jinja2-rendered standalone Python scripts, each printing one JSON result line; all trim to the
2.5/97.5 percentile before computing.

| Template | Test | Gated? |
|---|---|---|
| `group_diff.py.j2` | **ANOVA** (>2 groups) or **Welch's t-test**; effect = eta² / Cohen's d | ✅ |
| `correlation.py.j2` | **Pearson**; effect = \|r\| | ✅ |
| `trend.py.j2` | **Spearman** over time ordinal; rho + direction | ✅ |
| `chi_square.py.j2` | **Chi-square independence**; effect = Cramér's V | ✅ |
| `ratio.py.j2` | **Ratio KPI** (business fact, no p-value) | — |
| `top_n.py.j2` | **Top/bottom-N by metric** (business fact) | — |
| `cross_top_n.py.j2` | **Cross-dimensional drill-down** (business fact) | — |
| `concentration.py.j2` | **Pareto / concentration** (business fact) | — |

The four hypothesis-test templates carry `p_value`/`effect_size`/`effect_name` and pass through
the gates; the four fact templates carry no p-value and skip gating.

## Trust tiers

Every result is tagged with a `confidence_tier`:

- **`business_fact`** — arithmetic KPIs, no hypothesis test implied.
- **`validated`** — cleared significance + effect-size + BH-correction gates.
- **`not_significant`** — tested, explicitly failed.
- **`ad_hoc_query`** — a Tier-B answer to a user question, not a validated finding.

Insights additionally carry `source`: `generic` / `domain` / `market_dag`, so a UI can badge
where each hypothesis came from.

## Ad-hoc questions (Tier A → Tier B)

The `/chat` endpoint answers open-ended questions:

- **`qa/answer.py`** — Tier A→B router. `parse_intent` (`qa/intent_parser.py`, LLM sees names +
  roles only) maps the question to one of five fixed shapes (ratio/group_diff/correlation/trend/
  chi_square). Supported → render the same **vetted template** and run it. Unsupported or on
  error → fall back to Tier B. Sets the appropriate `confidence_tier`.
- **`qa/language_guard.py`** — strips editorializing/causal free-text ("surprisingly", "proves",
  "drives", …) while keeping the numbers.
- **Tier B** (`query/`) — the Query Agent (`query/query_agent.py`) has the LLM write descriptive
  pandas over `df` (schema only, no rows); a regex blocklist screens for unsafe code
  (imports/open/exec/eval/os/subprocess/…), regenerating once on violation, then runs it in the
  sandbox. `query/ask.py` adds one regenerate-and-retry that feeds the runtime error back.

## Public API (`insight_builder/api/`)

Mounted at `/api/insight`. In-memory sessions (no TTL reaper — sessions leak until deleted), one
scratch dir per process. See [08 — API Reference](08-api-reference.md) for the endpoint table.
Key flow: `POST /datasets` (upload) → optional `POST /datasets/{id}/market-research` (attach
`output.json`) → `POST /datasets/{id}/analyze` (run the graph) → paginated `GET
/datasets/{id}/insights` and `GET /datasets/{id}/kpis`, plus `POST /datasets/{id}/chat` for
ad-hoc questions.

## The LLM touchpoint (`qa/llm_client.py`)

The only place the package calls an LLM. `llm_available()` checks `DIAL_API_KEY` /
`DIAL_API_VERSION` / `DIAL_ENDPOINT` / `DIAL_MODEL`. `complete(prompt, system)` calls chat
completions with up to 3 retries (exponential backoff) on transient errors. When the LLM is
unavailable, every LLM node simply skips and the deterministic core still produces a report.
