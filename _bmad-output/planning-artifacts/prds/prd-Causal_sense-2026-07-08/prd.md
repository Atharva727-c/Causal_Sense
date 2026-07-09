---
title: Causal Sense
created: 2026-07-08
updated: 2026-07-09
status: final
---

# PRD: Causal Sense
*Working title — confirm.*

## 0. Document Purpose

This PRD aligns the Causal Sense team (Atharva, Sahil, Aaishwarya, Rupesh) on what to build before the 2026-07-13 hackathon submission, and is the evaluation-facing description of the product. It builds on `_bmad-output/forge/causal-sense/forged-idea.md` without duplicating it — that document remains the source for *why* alternatives were rejected. FRs are globally numbered and stable; `[ASSUMPTION]` tags are indexed in §9. **All numeric thresholds in this PRD (confidence scores, latency targets) are v1 placeholders the team will tune after testing — this isn't repeated per-FR below.**

**Ownership:** Rupesh — EDA, Talk to Your Data, React UI. Aaishwarya — ATE Estimation (FR-10). Atharva, Sahil, Aaishwarya jointly — the rest of the core inference pipeline (DAG draft, Expert Validation, What-if Simulator, NL Insight).

## 1. Vision

Causal Sense is an AI-native causal inference engine that answers one question well: *what actually caused this?* A user provides a dataset — time series or cross-sectional — and the product walks from raw data to a validated causal explanation: not "X correlates with Y" but "X caused Y, by this much, controlling for these confounders," in plain language, with the ability to simulate "what if X had been different?" A user can also just talk to their data directly, without running the full causal pipeline.

It matters because most data tools stop at correlation and dashboards. Causal Sense puts a rigorous pipeline (DAG construction, confounder control, ATE estimation) behind a UI simple enough for a non-expert, with an LLM drafting hypotheses, contextualizing them against real-world events, and translating statistical output into plain language — while a human stays in the loop on ambiguous claims.

**Domain- and shape-agnostic.** Not tuned to one dataset, industry, or even a data *shape* — a time column is not required. Time-series datasets get temporal EDA and time-bounded Market Research; cross-sectional datasets (comparing outcomes across groups at one point in time) get a generic exploratory path instead. The core pipeline (DAG draft, Expert Validation, ATE, What-if Sim, NL Insight) never needed time in the first place. The gold-prices dataset is a rehearsed demo example, not a design anchor.

For this hackathon, the product must run live, on stage, end-to-end without failure, on a team-provided demo dataset.

## 2. Target User

### 2.1 Jobs To Be Done

- As a data analyst or business stakeholder, I want to know *why* a metric moved, not just *that* it moved.
- As a non-expert in causal inference, I want the tool to draft and validate a causal hypothesis for me.
- As a decision-maker, I want to simulate "what if X changes" before acting.
- As anyone with a dataset, I want to just ask it questions in plain language without running a full analysis.
- `[ASSUMPTION]` As a hackathon judge, I evaluate the tool live as it runs on a team-provided dataset — the demo must communicate value without requiring me to drive it myself.

### 2.2 Key User Journeys

- **UJ-1. The team demos the full causal pipeline live on a curated dataset.**
  - **Persona + context:** A team presenter driving the tool in front of judges, on a pre-selected, rehearsed dataset (gold prices 2020-2023). Judges observe; they do not drive.
  - **Path:** Presenter uploads the CSV, selects "Causal Analysis." The app runs EDA, drafts a causal DAG (enriched by Market Research), surfaces 1-3 ambiguous edges in plain language for confirm/reject, then states the causal answer in plain language.
  - **Climax:** Judges see a specific claim — "X caused a change of {effect size} in Y, controlling for {confounders}" — backed by a visible DAG and a validation step a human participated in.
  - **Resolution:** Presenter moves to a what-if simulation (UJ-2) or asks the data a follow-up question (UJ-4).
  - **Edge case:** The upload/validation path (FR-1, FR-2) must still fail gracefully on a malformed CSV — a specific, actionable message, never a crash on stage.

- **UJ-2. A user runs a what-if simulation after a causal analysis.** Same session as UJ-1; user adjusts treatment variable X and gets a simulated P(Y|do(X)) from the validated causal graph — visibly different from a naive projection. Requires a prior Causal Analysis in-session (FR-12 Out of Scope).

- **UJ-3. A user runs EDA-only and gets nudged toward causal analysis.** User selects EDA explicitly, uploads data, sees pattern/anomaly output; if something notable is detected, a specific nudge suggests running Causal Analysis.

- **UJ-4. A user talks to their data directly.** User selects "Talk to Your Data," uploads a dataset, and asks free-text questions ("what's the average of X," "what happened in March") without running the causal pipeline. If a time column exists, the tool also proactively surfaces temporal insights unprompted.

## 3. Glossary

- **DAG (Causal Graph)** — A directed acyclic graph of hypothesized causal relationships, drafted by the Drafting LLM and refined via Expert Validation.
- **ATE (Average Treatment Effect)** — The estimated causal effect of a treatment variable on an outcome, computed via DoWhy/EconML after confounder control.
- **Confounder** — A variable influencing both a hypothesized cause and its effect; must be controlled for to isolate the true causal effect.
- **Expert Validation** — The step where a separate **Validator LLM** cross-checks each DAG edge and scores its confidence; high-confidence edges auto-validate, low-confidence edges escalate to the user in plain language.
- **Drafting LLM / Validator LLM** — Two distinct LLMs (separate DIAL keys): Drafting proposes the DAG; Validator independently scores each edge, so validation isn't a model checking its own work.
- **What-if Simulation** — P(Y|do(X)): the outcome Y under a hypothetical intervention on X, from the validated causal graph (not a plain regression).
- **Mode** — One of five explicit, user-selected entry points: EDA, Market Research, Causal Analysis, What-if Sim, Talk to Your Data. Never inferred by an LLM router.
- **Solution Orchestrator** — Composes the shared tool set (EDA, Market Research, DAG Draft, Expert Validation, ATE Estimation, What-if Sim, NL Insight) per selected Mode.
- **Time-series dataset** — Has a detected time/date column; routes to temporal EDA and time-bounded Market Research.
- **Cross-sectional dataset** — No time/date column; routes to generic distribution/correlation EDA and skips time-bounded Market Research. Fully supported, not degraded.
- **NL Insight / Talk to Your Data** — The plain-language layer: explains a causal result when embedded in the pipeline, or answers free-text questions directly about the dataset when run standalone.
- **Session** — One live run from upload to a delivered answer; v1 has no cross-session persistence. `[ASSUMPTION]`

## 4. Features

### 4.1 Data Ingestion & EDA

**Description:** The entry point for every Mode. Owner: Rupesh.

#### FR-1: Data Upload and Validation
User can upload data as **CSV** (v1 demo path, fully supported) or other tabular formats such as **Excel** (accepted without a file-type error; best-effort parsing, full analysis support not guaranteed in v1). Database connectivity is **Future Scope**, not built in v1 (see §6.2).

**Consequences (testable):**
- Uploading a non-CSV tabular file never produces a file-*type* error — the system attempts best-effort parsing. Validation errors are reserved for genuinely malformed/unparseable content, never the format itself.
- System rejects malformed input with a specific, actionable error, not a generic failure.
- **No minimum or maximum file/dataset size is enforced at upload.** Very large uploads may run slower; the UI shows progress rather than hanging silently (see Reliability NFR). Statistical sufficiency for a *reliable causal estimate* is a separate, downstream concern (FR-10), not an upload gate.

**Out of Scope:** Multi-file joins across a single session (one data source at a time); database connectivity (Future Scope).

#### FR-2: Automatic Schema & Time-Column Inference
System infers column types and a time/date column, if one exists, with no user configuration required. **This inference is a hard prerequisite for both EDA (FR-3/FR-4) and Talk to Your Data (FR-13/FR-14)** — both consume it directly.

**Consequences (testable):**
- ≥95% detection accuracy on unambiguous date formats `[ASSUMPTION target]`.
- If a time-like column is ambiguous, the system asks the user to designate it; if genuinely absent, it proceeds cross-sectionally without prompting.

#### FR-3: Temporal Pattern & Anomaly Detection (EDA — time-series path)
When a time column is present, system detects trends, seasonality, and anomalies (spikes, breaks, outliers), domain-agnostically (statistical properties, not hard-coded rules — validated against ≥1 non-demo dataset before submission `[ASSUMPTION]`).

**Feature-specific NFRs:** Must degrade gracefully (partial output + explanation) on unexpected shapes, never crash.

#### FR-4: Cross-Sectional Exploratory Analysis (EDA — non-time-series path)
When no time column is present, system runs distributions, a correlation/association scan, and a missingness summary, surfacing candidate treatment/outcome variables instead of anomalies.

**Consequences (testable):** The proactive nudge (FR-16) adapts wording here — e.g. "a strong association was found between X and Y" — since there's no spike or date to reference.

### 4.2 Market Research (Upstream Causal Context)

**Description:** Uses the **Tavily web search API** to find real-world events that are plausible upstream causal candidates, feeding DAG drafting *before* the graph is built — not post-hoc. An entry point that funnels toward Causal Analysis; also runnable standalone. Owner: core team.

#### FR-5: Standalone Event/Context Search
Given a topic and date range, queries Tavily and returns events with source attribution, or a clear "no relevant events found" — never fabricated.

#### FR-6: Upstream Enrichment for Causal Analysis
On a time-series dataset, automatically runs Market Research against the dataset's time range and feeds results into DAG Drafting (FR-8) as candidate upstream causes. If nothing relevant, DAG Drafting proceeds dataset-internally, noted in the NL Insight output.

#### FR-7: Market Research Fallback for Cross-Sectional Datasets
No time column means no timeframe to bound the search. System skips enrichment and states this explicitly in the NL Insight output rather than omitting it silently. `[ASSUMPTION — default is skip-with-note, not a topic-only query without a date filter]`

### 4.3 Causal Analysis (Flagship Pipeline)

**Description:** EDA → Market Research → LLM DAG Draft → Expert Validation → ATE Estimation → What-if Simulator → NL Insight. Primary demo path, realizes UJ-1. Owner: core team (per-FR ownership below).

#### FR-8: LLM-Drafted Causal DAG
**Drafting LLM** drafts a DAG from detected patterns (FR-3 or FR-4) plus Market Research context (FR-6, or its absence per FR-7). Rendered visually before any validation step; each edge passed to the Validator LLM for scoring.

#### FR-9: Hybrid Expert Validation (Cross-Model)
A separate **Validator LLM** (distinct model/DIAL key) independently scores each edge. High-confidence edges auto-validate (default threshold **0.8**); below-threshold edges escalate to the user in plain language, jargon-free. User can accept/reject each escalated edge; rejected edges are excluded from FR-10.

#### FR-10: ATE Estimation with Confounder Control
**Owner: Aaishwarya.** Estimates the average treatment effect of validated edges via DoWhy/EconML, controlling for confounders in the validated DAG.

**Consequences (testable):**
- Output includes effect size, a confidence/uncertainty indicator, and the confounders controlled for.
- A dataset needs enough rows and ≥2 analyzable variables for a *reliable* estimate `[ASSUMPTION — exact bar TBD after testing]` — no time column required; below that bar, the system reports the estimate as unreliable rather than hiding the limitation. This is separate from FR-1's no-upload-limit: small datasets are always accepted, but may get a low-confidence result instead of a rejection.

#### FR-11: Plain-Language Insight (Pipeline-Embedded)
Translates the ATE result and validated DAG into one readable, jargon-free paragraph naming the cause, effect, effect size, and confounders — and any edges the user rejected. Shares its underlying capability with Talk to Your Data (4.5); a user can keep asking follow-up questions after this point.

### 4.4 What-if Simulator

**Description:** Post-causation intervention simulator. Requires a prior Causal Analysis in-session. Realizes UJ-2. Owner: core team.

#### FR-12: Graph-Based Intervention Simulation
User specifies a hypothetical value for a validated treatment variable X and gets a simulated P(Y|do(X)) from the causal graph — visibly distinct in the UI from a naive linear projection. Disabled/redirected if no validated Causal Analysis exists in-session.

**Out of Scope:** Multi-variable simultaneous interventions (single-variable only in v1). `[ASSUMPTION]`

### 4.5 NL Insight Builder — "Talk to Your Data"

**Description:** A standalone mode where a user converses in natural language with their uploaded dataset, without running the full Causal Analysis pipeline. Requires Automatic Schema & Time-Column Inference (FR-2). Shares its NL-generation capability with FR-11 — one triggered by a causal result, one by direct user questions. Realizes UJ-4. Owner: Rupesh.

#### FR-13: Standalone Conversational Data Q&A
User asks free-text questions about the uploaded dataset (e.g. "what's the average of X," "what happened around March") and gets plain-language answers.

**Consequences (testable):**
- Answers are grounded in the dataset's real schema and computed values, not hallucinated from column names alone.
- If a question can't be answered from the data, the system says so rather than guessing.

#### FR-14: Proactive Temporal Insight Surfacing
When a time column is detected (FR-2), this mode proactively surfaces temporal-pattern insights (reusing FR-3's detection) alongside answering direct questions — at least one insight shown before the user asks anything. On a cross-sectional dataset, it falls back to reactive Q&A only, with no fabricated "temporal" insights.

### 4.6 Mode Selection & Orchestration

**Description:** Explicit mode buttons for all five modes; no LLM-based intent recognition — deliberately rejected, since misrouting a math-backed tool is worse than misrouting a chatbot (a wrong mode changes what gets computed, not just what gets said). Owner: Rupesh (UI) + core team (orchestrator).

#### FR-15: Explicit Mode Selection UI
User selects one of five modes via explicit buttons before any analysis begins; no natural-language "what do you want to do" entry point routes to a mode anywhere in v1.

#### FR-16: Proactive AI Nudge Post-EDA
After EDA (FR-3/FR-4) completes, if something notable was detected and Causal Analysis hasn't run yet, a specific, dismissible nudge suggests it — naming the actual anomaly or association, never a generic prompt.

#### FR-17: Shared Tool Orchestration
Solution Orchestrator composes EDA, Market Research, DAG Draft, Expert Validation, ATE Estimation, What-if Sim, and NL Insight as shared tools across modes — chosen over four separate per-teammate agents, which were rejected for creating redundant tools and preventing sharing. What-if Sim's availability is gated structurally on a Causal Analysis result existing in-session, not just via UI copy.

## 5. Non-Goals (Explicit)

- Not a general-purpose BI/dashboarding tool — every mode performs or leads toward causal inference.
- Not an LLM-based intent router for mode selection (explicitly rejected).
- Not supporting multi-file joins or database connectivity in v1 (database connectivity is Future Scope, §6.2) — CSV is the demo path; other tabular formats are accepted but not guaranteed full support.
- Not providing regulatory/compliance-grade audit trails for causal claims.
- Not persisting user data/sessions beyond the current browser session `[ASSUMPTION]` — no accounts, no saved history.
- Not attempting full automated causal validation with zero human oversight (explicitly rejected — collective-hallucination risk).
- Not framing the product as a generic data-science assistant (explicitly rejected — weak on Innovation, SM-4); the causal-inference identity is the specific novelty every feature must trace back to.

## 6. MVP Scope

### 6.1 In Scope
- CSV upload as the demo path (fully supported); other tabular formats (Excel) accepted without a file-type error; no size ceiling (FR-1, FR-2).
- EDA on both paths: temporal (FR-3) or cross-sectional (FR-4).
- Market Research standalone, upstream-enrichment, and cross-sectional fallback (FR-5–FR-7).
- Full Causal Analysis pipeline, both dataset shapes (FR-8–FR-11).
- What-if Simulator gated on prior Causal Analysis (FR-12).
- Talk to Your Data: standalone Q&A + proactive temporal insights (FR-13, FR-14).
- Explicit 5-mode selection UI with proactive nudge (FR-15, FR-16).
- Curated demo dataset (gold prices 2020-2023), rehearsed as the primary live-demo path.
- React frontend covering all five modes.

### 6.2 Out of Scope for MVP
- Multi-variable what-if interventions — v2; single-variable demonstrates the mechanism.
- User accounts / cross-session persistence.
- File formats beyond CSV/Excel (JSON, Parquet).
- Judge/audience-supplied datasets — the team supplies demo data; arbitrary-file robustness beyond graceful, non-erroring acceptance (FR-1) isn't an MVP investment.
- Tunable confidence-threshold UI for Expert Validation — team sets it (0.8 default) at build time. `[NOTE FOR PM]` Could be a strong Responsible-AI talking point if judges probe it and time permits.

**Future Scope (v2+):** Database connectivity (query/pull from an external DB — engine and auth TBD); full, guaranteed analysis support for Excel and other tabular formats beyond best-effort parsing; live/streaming DB sync.

## 7. Success Metrics

*Structured against the six weighted hackathon judging criteria.*

**Primary**
- **SM-1 (AI Tool Use, 25%)**: Every pipeline step — EDA, Tavily Market Research, Drafting LLM, Validator LLM, NL Insight/Talk to Your Data — visibly and traceably uses AI, demoable via a "how AI was used" walkthrough. Validates FR-8, FR-9, FR-11, FR-13.
- **SM-2 (Functionality & Demo, 15%)**: A live end-to-end run (upload → causal answer → what-if sim) completes without crash or silent failure, reliably across repeated runs. Validates FR-1–FR-12.
- **SM-3 (Impact & Relevance, 20%)**: Demo narrative ties the causal answer to a real decision a business/analyst would make differently.

**Secondary**
- **SM-4 (Innovation & Creativity, 20%)**: Market-research-as-upstream-enrichment and cross-model Expert Validation are explicitly called out as the novel mechanisms, not left implicit.
- **SM-5 (Collaboration & Documentation, 10%)**: This PRD, the forged-idea doc, and a short "how we used AI" writeup are complete and legible to an outsider by submission.
- **SM-6 (Responsible & Ethical AI, 10%)**: Demo shows the cross-model Expert Validation step and states the DAG-hallucination limitation out loud, per SM-C1.

**Counter-metrics (do not optimize)**
- **SM-C1**: Don't optimize for auto-validating more edges to look more automated — over-trusting the Validator LLM raises hallucinated-causation risk, judged directly under Responsible & Ethical AI. Counterbalances SM-1, SM-4.
- **SM-C2**: Don't optimize for more formats/modes at the expense of live-demo reliability (SM-2) — broader-but-flakier scores worse than narrower-but-bulletproof.

## 8. Open Questions

1. Model pairing for Drafting vs. Validator LLM — two different DIAL-hosted models, or same base model at different configs? How does the Validator LLM turn a review into a numeric confidence score?
2. Tavily query strategy — how are search terms derived from an arbitrary dataset's columns/domain so it generalizes past the demo dataset?
3. **Demo-day contingency (undecided):** pre-recorded backup, a pre-computed cached result, or rehearsal + graceful degradation alone? Protects SM-2 and the Reliability NFR; needs a decision before dress rehearsal.
4. Does Talk to Your Data (FR-13) need multi-turn conversation memory, or is single-turn Q&A sufficient for the demo?

## 9. Assumptions Index

- §2.1 — Judges evaluate the tool as it runs on team-provided data; they don't drive it.
- §3 — "Session" has no cross-session persistence; browser-session-scoped only.
- FR-1 — Non-CSV tabular formats (Excel) are best-effort parsed, full support not guaranteed in v1; database connectivity deferred entirely to Future Scope.
- FR-2 — 95% time-column detection target not yet measured.
- FR-3 — Domain-agnostic detection to be validated against ≥1 non-demo dataset before submission.
- FR-9 — Auto-validation threshold defaults to 0.8, retunable after testing.
- FR-10 — Exact minimum-data bar for a reliable ATE estimate TBD after testing; no time column required.
- FR-7 — Cross-sectional Market Research fallback defaults to skip-with-note, not a topic-only query.
- FR-12 — Single-variable what-if only in v1.
- §5 — No accounts / no cross-session persistence.

## Constraints, Guardrails & NFRs

**Responsible AI**
- Expert Validation (FR-9) is mandatory — never present an auto-validated-only claim as final without disclosing unreviewed edges.
- The cross-model design is itself a Responsible-AI feature: the validating model must not be the model that drafted the DAG.
- Market Research (FR-5–FR-7) states "no relevant events found" rather than fabricating, and states explicitly when it was skipped (cross-sectional data).

**Privacy / Security**
- DIAL API keys (Drafting + Validator) and the Tavily key are backend-only secrets — never in client-side code, commits, logs, or on the React frontend.
- Uploaded data is not persisted beyond the session, nor sent anywhere beyond the LLM proxies and Tavily required for analysis. `[ASSUMPTION]`

**NFRs**
- **Reliability (demo-critical):** The live demo path must not crash or hang; every failure degrades to a specific, actionable error, never a blank screen or stack trace on stage.
- **Latency:** Each pipeline step targets a live-demo-tolerable window; the full Causal Analysis pipeline targets 60-90 seconds end-to-end `[ASSUMPTION]`, or the UI shows clear intermediate progress.
- **Explainability:** Every AI-generated claim is traceable to the pipeline step that produced it.

## Handoff

Next: `bmad-ux` (screens per mode), then `bmad-architecture` (scaled to a quick spine given the timeline), then `bmad-create-epics-and-stories`.
