# 06 — Market Research

**Path:** `market_research/` · **Stack:** OpenAI-compatible LLM (EPAM DIAL), Tavily web search,
NetworkX · **Output:** `AnalysisResult` (serialized to `output.json`)

Market Research is a three-stage pipeline: it profiles an uploaded dataset, runs LLM-planned web
research, and hypothesizes a causal DAG. The result serializes to the `output.json` that Insight
Builder can ingest to enrich its analysis with domain context and DAG-derived hypotheses.

## External services

- **Tavily** (`search_client.py`) — web search. Posts to `https://api.tavily.com/search` using
  `TAVILY_API_KEY`. `search` returns `{title, url, content}` dicts; `search_many` runs several
  queries, dedupes by URL, and skips failing queries.
- **DIAL / Azure-OpenAI** (`llm_client.py`) — all LLM calls. Default endpoint
  `https://ai-proxy.lab.epam.com`, model `gpt-5.5-2026-04-24-reasoning`, via `DIAL_*` env vars —
  the same credential family as Insight Builder. `chat_json` requests a JSON object (falling back
  to a non-`response_format` call for models that don't support it), strips code fences, and
  sanitizes smart quotes.

## Entry point

`agent.py` — `MarketResearchAgent.analyze(file, description, filename)` runs the three stages in
sequence and returns an `AnalysisResult(data_profile, market_research, dag,
dag_unavailable_reason)`. Convenience wrapper: `analyze_file(...)`. The package itself does not
write `output.json` — a REST caller serializes the returned Pydantic model, whose shape maps 1:1
onto the `data_profile` / `market_research` / `dag` keys Insight Builder reads back.

## Stage 1 — Data profiling (`data_profiler.py`)

`build_data_profile`:
1. `load_dataframe` (CSV/Excel).
2. `profile_columns` → `_infer_role_and_stats` classifies each column
   (date/numeric/currency/percent/identifier/categorical/text) with min/max/mean or top-value
   stats.
3. `detect_timeline` picks a priority date column and derives the dataset's start/end.
4. `infer_domain_and_description` — one LLM call to label the business domain and (if the user
   gave none) write a dataset description.

Returns a `DataProfile`.

## Stage 2 — Market research (`research_agent.py`)

`run_market_research(profile)`:
1. Picks a **mode** — `time_bounded` if the profile has a timeline, else `column_context`.
2. `plan_research_queries` — the LLM emits 4–6 targeted queries (time-bounded queries pinned to
   the dataset's year range; column-context queries avoid years).
3. `run_searches` → `search_many` (Tavily).
4. `synthesize_report` — the LLM turns the numbered sources into a structured
   `MarketResearchReport`: `executive_summary`, 3–6 `key_findings` with resolved `SourceRef`s,
   `opportunities`, `risks`, and `recommendations` with priority.

## Stage 3 — Causal DAG (`dag_builder.py`)

`build_causal_dag(profile, report)`:
- Requires ≥2 structured columns, else returns `(None, reason)` — so a DAG is genuinely optional.
- Prompts the LLM for a feasibility flag + nodes (`dataset_variable` / `external_factor`) +
  confidence-weighted edges (≤12 nodes, ≤15 edges, no bidirectional pairs).
- `_parse_llm_dag` validates node types/ids and edge endpoints.
- `_make_acyclic` uses **NetworkX** to break cycles by dropping the lowest-confidence edge until
  the graph is acyclic, then prunes orphan nodes.
- Returns `(None, reason)` if the graph collapses (<2 nodes or no edges).

## Output schema (`models.py`)

Pydantic models for the whole output:

- **Stage 1:** `ColumnProfile`, `TimelineInfo`, `DataProfile`.
- **Stage 2:** `SourceRef`, `KeyFinding`, `Recommendation`, `MarketResearchReport`.
- **Stage 3:** `DagNode`, `DagEdge`, `CausalDag`.
- **Top level:** `AnalysisResult` — the serialized form is the `output.json` Insight Builder
  ingests.

## The implicit contract with Insight Builder

The two packages share an implicit contract through `output.json`:

| Market Research field | Consumed by Insight Builder |
|---|---|
| `data_profile.domain` | Domain fallback for the Domain Knowledge Agent |
| `data_profile.columns` | `matches_dataset` check (discard a mismatched artifact) |
| `market_research.*` findings | `context/enricher.py` — annotation on validated insights |
| `dag.nodes` (`dataset_variable` / `external_factor`), `dag.edges` (`confidence`) | `context/dag_hypotheses.py` — DAG-derived test candidates |

Insight Builder's `context/market.py` is the only module that parses this artifact, and it is
tolerant: any missing, invalid, or wrong-shaped artifact yields `None`, and the affected graph
nodes simply skip.

## How it's invoked in the product

- Directly via the FastAPI backend: `POST /api/market-research/analyze` (see
  [08 — API Reference](08-api-reference.md)) — runs `analyze_file` in a threadpool and returns the
  `AnalysisResult` as JSON, rendered by the frontend's `MarketResearchResult` + `DagView`.
- As **stage 2 of the Causal Analysis chain** (`backend_fastapi/app/routers/causal.py`), where its
  output is written to a workspace artifact and passed into Insight Builder as
  `market_research_path`.
