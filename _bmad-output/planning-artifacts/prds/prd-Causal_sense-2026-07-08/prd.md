---
title: Causal Sense
created: 2026-07-08
updated: 2026-07-11
status: final
---

# PRD: Causal Sense
*Working title — confirm.*

## 0. Document Purpose

This PRD aligns the Causal Sense team (Atharva, Sahil, Aaishwarya, Rupesh) on what to build before the 2026-07-13 hackathon submission, and is the evaluation-facing description of the product. It builds on `_bmad-output/forge/causal-sense/forged-idea.md` without duplicating it — that document remains the source for *why* alternatives were rejected. FRs are globally numbered and stable; `[ASSUMPTION]` tags are indexed in §9. **All numeric thresholds in this PRD (confidence scores, latency targets) are v1 placeholders the team will tune after testing — this isn't repeated per-FR below.**

**Ownership:** Sahil — React UI (all four modes). Rupesh — EDA, Talk to Your Data. Aaishwarya — ATE Estimation (FR-10). Atharva, Aaishwarya, Rupesh jointly — the rest of the core inference pipeline (DAG draft, Expert Validation, NL Insight).

## 1. Vision

Causal Sense is an AI-native causal inference engine that answers one question well: *what actually caused this?* A user provides a dataset — time series or cross-sectional — and the product walks from raw data to a validated causal explanation: not "X correlates with Y" but "X caused Y, by this much, controlling for these confounders," in plain language. A user can also just talk to their data directly, without running the full causal pipeline.

It matters because most data tools stop at correlation and dashboards. Causal Sense puts a rigorous pipeline (DAG construction, confounder control, ATE estimation) behind a UI simple enough for a non-expert, with an LLM drafting hypotheses, contextualizing them against real-world events, and translating statistical output into plain language — while a human stays in the loop on ambiguous claims.

**Domain- and shape-agnostic.** Not tuned to one dataset, industry, or even a data *shape* — a time column is not required. Time-series datasets get temporal EDA and time-bounded Market Research; cross-sectional datasets (comparing outcomes across groups at one point in time) get a generic exploratory path and column-context Market Research instead. The core pipeline (DAG draft, Expert Validation, ATE, NL Insight) never needed time in the first place. The gold-prices dataset is a rehearsed demo example, not a design anchor.

For this hackathon, the product must run live, on stage, end-to-end without failure, on a team-provided demo dataset.

## 2. Target User

### 2.1 Jobs To Be Done

- As a data analyst or business stakeholder, I want to know *why* a metric moved, not just *that* it moved.
- As a non-expert in causal inference, I want the tool to draft and validate a causal hypothesis for me.
- As anyone with a dataset, I want to just ask it questions in plain language without running a full analysis.
- `[ASSUMPTION]` As a hackathon judge, I evaluate the tool live as it runs on a team-provided dataset — the demo must communicate value without requiring me to drive it myself.

### 2.2 Key User Journeys

- **UJ-1. The team demos the full causal pipeline live on a curated dataset.**
  - **Persona + context:** A team presenter driving the tool in front of judges, on a pre-selected, rehearsed dataset (gold prices 2020-2023). Judges observe; they do not drive.
  - **Path:** Presenter uploads the CSV, selects "Causal Insight." The app runs EDA, drafts a causal DAG (enriched by Market Research), surfaces 1-3 ambiguous edges in plain language for confirm/reject, then states the causal answer in plain language.
  - **Climax:** Judges see a specific claim — "X caused a change of {effect size} in Y, controlling for {confounders}" — backed by a visible DAG and a validation step a human participated in.
  - **Resolution:** Presenter asks the data a follow-up question (UJ-3).
  - **Edge case:** The upload/validation path (FR-1, FR-2) must still fail gracefully on a malformed CSV — a specific, actionable message, never a crash on stage.

- **UJ-2. A user runs EDA-only and gets nudged toward causal analysis.** User selects EDA explicitly, uploads data, sees pattern/anomaly output; if something notable is detected, a specific nudge suggests running Causal Insight.

- **UJ-3. A user talks to their data directly.** User selects "NL Insight Builder" (Talk to Your Data), uploads a dataset, and is first shown automatically generated insights, then asks free-text questions ("what's the average of X," "what happened in March") without running the causal pipeline. If a time column exists, the automatic insights include temporal patterns.

## 3. Glossary

- **DAG (Causal Graph)** — A directed acyclic graph of hypothesized causal relationships, drafted by the Drafting LLM and refined via Expert Validation. Not guaranteed to be producible for every dataset; when produced it is rendered in the UI and forwarded to the NL Insight Builder.
- **ATE (Average Treatment Effect)** — The estimated causal effect of a treatment variable on an outcome, computed via DoWhy/EconML after confounder control.
- **Confounder** — A variable influencing both a hypothesized cause and its effect; must be controlled for to isolate the true causal effect.
- **Expert Validation** — The step where a separate **Validator LLM** cross-checks each DAG edge and scores its confidence; high-confidence edges auto-validate, low-confidence edges escalate to the user in plain language.
- **Drafting LLM / Validator LLM** — Two distinct LLMs (separate DIAL keys): Drafting proposes the DAG; Validator independently scores each edge, so validation isn't a model checking its own work.
- **Mode** — One of four explicit, user-selected entry points: EDA, Market Research (now includes DAG Draft, Expert Validation, and ATE Estimation — not search alone), NL Insight Builder, Causal Insight (the full pipeline). Never inferred by an LLM router.
- **Mode Runner** — An internal, non-user-facing module that composes the shared tool set (EDA, Market Research, DAG Draft, Expert Validation, ATE Estimation, NL Insight) per selected Mode, so overlapping steps between Market Research and Causal Insight aren't wired twice. Not a concept exposed anywhere in the UI or to the user — earlier drafts of this PRD called it the "Solution Orchestrator."
- **Time-series dataset** — Has a detected time/date column; routes to temporal EDA and time-bounded Market Research.
- **Cross-sectional dataset** — No time/date column; routes to generic distribution/correlation EDA and column-context Market Research (no time bound). Fully supported, not degraded.
- **NL Insight / Talk to Your Data** — The plain-language layer, with two parts: it explains a causal result when embedded in the pipeline (FR-11), and standalone it both generates insights automatically (FR-13) and answers free-text questions directly about the dataset (FR-12).
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
System infers column types and a time/date column, if one exists, with no user configuration required. **This inference is a hard prerequisite for both EDA (FR-3/FR-4) and Talk to Your Data (FR-12/FR-13)** — both consume it directly.

**Consequences (testable):**
- ≥95% detection accuracy on unambiguous date formats `[ASSUMPTION target]`.
- If a time-like column is ambiguous, the system asks the user to designate it; if genuinely absent, it proceeds cross-sectionally without prompting.

#### FR-3: Temporal Pattern & Anomaly Detection (EDA — time-series path)
When a time column is present, system detects trends, seasonality, and anomalies (spikes, breaks, outliers), domain-agnostically (statistical properties, not hard-coded rules — validated against ≥1 non-demo dataset before submission `[ASSUMPTION]`).

**Feature-specific NFRs:** Must degrade gracefully (partial output + explanation) on unexpected shapes, never crash.

#### FR-4: Cross-Sectional Exploratory Analysis (EDA — non-time-series path)
When no time column is present, system runs distributions, a correlation/association scan, and a missingness summary, surfacing candidate treatment/outcome variables instead of anomalies.

**Consequences (testable):** The proactive nudge (FR-15) adapts wording here — e.g. "a strong association was found between X and Y" — since there's no spike or date to reference.

### 4.2 Market Research (Upstream Causal Context, Standalone Insight, and Causal Modeling)

**Description:** Uses the **Tavily web search API** to find real-world events and context that are plausible upstream causal candidates. Runs as its own standalone mode — where it now continues on into the shared causal-modeling steps (DAG Draft, Expert Validation, ATE Estimation; see FR-8–FR-10) rather than stopping at the summary — and also as upstream enrichment feeding DAG drafting within Causal Insight *before* the graph is built — not post-hoc. **Always produces a plain-language, plain-text market-research summary**, delivered both to the user in the UI and to the NL Insight Builder (4.4) as grounding context. Owner: core team.

#### FR-5: Standalone Market Research
As its own mode, runs market research against the uploaded dataset and returns a plain-text, plain-language summary with source attribution — or a clear "no relevant events found," never fabricated. Scope adapts to the data:
- **Timeline present:** time-bounded context research over the dataset's date range (events and context within that window).
- **No timeline:** column-context research derived from the dataset's columns and domain (no time bound).

The mode then continues into the same shared causal-modeling steps used by Causal Insight — DAG Draft (FR-8), Expert Validation (FR-9), and ATE Estimation (FR-10) — so a user who only wants "what caused what, backed by real-world context" doesn't have to separately run the full Causal Insight pipeline (which additionally runs EDA up front and NL Insight at the end).

**Consequences (testable):**
- The plain-text summary is delivered both to the user (UI) and forwarded to the NL Insight Builder (FR-12/FR-13) as context.
- A causal DAG is **not** guaranteed for every dataset. When one is generated, it is displayed in the UI and also forwarded to the NL Insight Builder; when it can't be, the summary is delivered without one, stated plainly rather than faked.
- Expert Validation's escalation behavior (FR-9) applies identically here: ATE Estimation does not run against an edge still awaiting the user's accept/reject decision.

#### FR-6: Upstream Enrichment for Causal Insight
Within Causal Insight, Market Research runs automatically and feeds results into DAG Drafting (FR-8) as candidate upstream causes. On a time-series dataset it bounds the search to the dataset's time range; on a cross-sectional dataset it runs column-context research (FR-7). If nothing relevant is found, DAG Drafting proceeds dataset-internally, noted in the NL Insight output.

#### FR-7: Cross-Sectional Market Research (Column-Context)
No time column means no timeframe to bound the search, so the system runs **column-context research** based on the dataset's columns and domain rather than skipping. The plain-text result still flows to the user and to the NL Insight Builder. `[ASSUMPTION — default is column-context research, superseding the earlier skip-with-note behavior]`

### 4.3 Causal Insight (Flagship Pipeline)

**Description:** EDA → Market Research → LLM DAG Draft → Expert Validation → ATE Estimation → NL Insight — the full pipeline mode. FR-8–FR-10 are the same shared steps also reachable directly from the standalone Market Research mode (4.2); Causal Insight is what you get by additionally running EDA first and NL Insight last, in one mode. Primary demo path, realizes UJ-1. Owner: core team (per-FR ownership below).

#### FR-8: LLM-Drafted Causal DAG
**Drafting LLM** drafts a DAG from detected patterns (FR-3 or FR-4) plus Market Research context (FR-6, or column-context per FR-7). Rendered visually before any validation step; each edge passed to the Validator LLM for scoring. A valid DAG is not guaranteed for every dataset; when one is produced it is displayed and forwarded downstream, otherwise the limitation is stated plainly in the NL Insight output.

#### FR-9: Hybrid Expert Validation (Cross-Model)
A separate **Validator LLM** (distinct model/DIAL key) independently scores each edge. High-confidence edges auto-validate (default threshold **0.8**); below-threshold edges escalate to the user in plain language, jargon-free. User can accept/reject each escalated edge; rejected edges are excluded from FR-10.

#### FR-10: ATE Estimation with Confounder Control
**Owner: Aaishwarya.** Estimates the average treatment effect of validated edges via DoWhy/EconML, controlling for confounders in the validated DAG.

**Consequences (testable):**
- Output includes effect size, a confidence/uncertainty indicator, and the confounders controlled for.
- A dataset needs enough rows and ≥2 analyzable variables for a *reliable* estimate `[ASSUMPTION — exact bar TBD after testing]` — no time column required; below that bar, the system reports the estimate as unreliable rather than hiding the limitation. This is separate from FR-1's no-upload-limit: small datasets are always accepted, but may get a low-confidence result instead of a rejection.

#### FR-11: Plain-Language Insight (Pipeline-Embedded)
Translates the ATE result and validated DAG into one readable, jargon-free paragraph naming the cause, effect, effect size, and confounders — and any edges the user rejected. Shares its underlying capability with NL Insight Builder (4.4); a user can keep asking follow-up questions after this point.

### 4.4 NL Insight Builder — "Talk to Your Data"

**Description:** A standalone mode with **two parts: (a) automatic insight generation** (FR-13) and **(b) talk to your data** (FR-12). The user converses in natural language with their uploaded dataset without running the full Causal Insight pipeline, and is also shown insights proactively before asking anything. Requires Automatic Schema & Time-Column Inference (FR-2), and — when available — consumes the plain-text market-research summary and DAG forwarded from Market Research (FR-5/FR-6). Shares its NL-generation capability with FR-11 — one triggered by a causal result, one by direct user questions. Realizes UJ-3. Owner: Rupesh.

#### FR-12: Talk to Your Data — Conversational Q&A
User asks free-text questions about the uploaded dataset (e.g. "what's the average of X," "what happened around March") and gets plain-language answers.

**Consequences (testable):**
- Answers are grounded in the dataset's real schema and computed values, not hallucinated from column names alone.
- If a question can't be answered from the data, the system says so rather than guessing.

#### FR-13: Automatic Insight Generation
Without being asked, this mode surfaces insights about the dataset — temporal-pattern insights (reusing FR-3's detection) when a time column is present, distribution/association insights (reusing FR-4) otherwise — plus any market-research context forwarded from FR-5/FR-6. At least one insight is shown before the user asks anything. On a cross-sectional dataset it does not fabricate "temporal" insights.

### 4.5 Mode Selection & Shared Tool Composition

**Description:** Explicit mode buttons for all four modes; no LLM-based intent recognition — deliberately rejected, since misrouting a math-backed tool is worse than misrouting a chatbot (a wrong mode changes what gets computed, not just what gets said). Owner: Sahil (UI) + core team (internal mode composition — see Mode Runner, §3).

#### FR-14: Explicit Mode Selection UI
User selects one of four modes — EDA, Market Research, NL Insight Builder, Causal Insight — via explicit buttons before any analysis begins; no natural-language "what do you want to do" entry point routes to a mode anywhere in v1.

#### FR-15: Proactive AI Nudge Post-EDA
After EDA (FR-3/FR-4) completes, if something notable was detected and Causal Insight hasn't run yet, a specific, dismissible nudge suggests it — naming the actual anomaly or association, never a generic prompt.

#### FR-16: Shared Tool Composition
An internal, non-user-facing module (Mode Runner, §3) composes EDA, Market Research, DAG Draft, Expert Validation, ATE Estimation, and NL Insight as shared tools across modes — chosen over four separate per-teammate agents, which were rejected for creating redundant tools and preventing sharing.

## 5. Non-Goals (Explicit)

- Not a general-purpose BI/dashboarding tool — every mode performs or leads toward causal inference.
- Not an LLM-based intent router for mode selection (explicitly rejected).
- Not supporting multi-file joins or database connectivity in v1 (database connectivity is Future Scope, §6.2) — CSV is the demo path; other tabular formats are accepted but not guaranteed full support.
- Not shipping a What-if / intervention simulator in v1 (removed from scope; deferred to v2 Future Scope).
- Not providing regulatory/compliance-grade audit trails for causal claims.
- Not persisting user data/sessions beyond the current browser session `[ASSUMPTION]` — no accounts, no saved history.
- Not attempting full automated causal validation with zero human oversight (explicitly rejected — collective-hallucination risk).
- Not framing the product as a generic data-science assistant (explicitly rejected — weak on Innovation, SM-4); the causal-inference identity is the specific novelty every feature must trace back to.

## 6. MVP Scope

### 6.1 In Scope
- CSV upload as the demo path (fully supported); other tabular formats (Excel) accepted without a file-type error; no size ceiling (FR-1, FR-2).
- EDA on both paths: temporal (FR-3) or cross-sectional (FR-4).
- Market Research standalone (now also running DAG Draft, Expert Validation, and ATE Estimation, not search alone) and upstream-enrichment, always emitting a plain-text summary to the user and NL Insight Builder; time-bounded when a timeline exists, column-context otherwise (FR-5–FR-7).
- Full Causal Insight pipeline, both dataset shapes (FR-8–FR-11).
- NL Insight Builder (Talk to Your Data): automatic insight generation + conversational Q&A (FR-12, FR-13).
- Explicit 4-mode selection UI with proactive nudge (FR-14, FR-15).
- Curated demo dataset (gold prices 2020-2023), rehearsed as the primary live-demo path.
- React frontend covering all four modes.

### 6.2 Out of Scope for MVP
- User accounts / cross-session persistence.
- File formats beyond CSV/Excel (JSON, Parquet).
- Judge/audience-supplied datasets — the team supplies demo data; arbitrary-file robustness beyond graceful, non-erroring acceptance (FR-1) isn't an MVP investment.
- Tunable confidence-threshold UI for Expert Validation — team sets it (0.8 default) at build time. `[NOTE FOR PM]` Could be a strong Responsible-AI talking point if judges probe it and time permits.

**Future Scope (v2+):** What-if / intervention simulator — P(Y|do(X)) from the validated causal graph, gated on a prior Causal Insight run (removed from v1 scope). Database connectivity (query/pull from an external DB — engine and auth TBD). Full, guaranteed analysis support for Excel and other tabular formats beyond best-effort parsing; live/streaming DB sync.

## 7. Success Metrics

*Structured against the six weighted hackathon judging criteria.*

**Primary**
- **SM-1 (AI Tool Use, 25%)**: Every pipeline step — EDA, Tavily Market Research, Drafting LLM, Validator LLM, NL Insight/Talk to Your Data — visibly and traceably uses AI, demoable via a "how AI was used" walkthrough. Validates FR-8, FR-9, FR-11, FR-12.
- **SM-2 (Functionality & Demo, 15%)**: A live end-to-end run (upload → causal answer) completes without crash or silent failure, reliably across repeated runs. Validates FR-1–FR-11.
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
2. Tavily query strategy — how are search terms derived from an arbitrary dataset's columns/domain so it generalizes past the demo dataset (both the time-bounded and column-context paths)?
3. **Demo-day contingency (undecided):** pre-recorded backup, a pre-computed cached result, or rehearsal + graceful degradation alone? Protects SM-2 and the Reliability NFR; needs a decision before dress rehearsal.
4. Does NL Insight Builder (FR-12) need multi-turn conversation memory, or is single-turn Q&A sufficient for the demo?

## 9. Assumptions Index

- §2.1 — Judges evaluate the tool as it runs on team-provided data; they don't drive it.
- §3 — "Session" has no cross-session persistence; browser-session-scoped only.
- FR-1 — Non-CSV tabular formats (Excel) are best-effort parsed, full support not guaranteed in v1; database connectivity deferred entirely to Future Scope.
- FR-2 — 95% time-column detection target not yet measured.
- FR-3 — Domain-agnostic detection to be validated against ≥1 non-demo dataset before submission.
- FR-7 — Cross-sectional Market Research now runs column-context research (supersedes the earlier skip-with-note default).
- FR-9 — Auto-validation threshold defaults to 0.8, retunable after testing.
- FR-10 — Exact minimum-data bar for a reliable ATE estimate TBD after testing; no time column required.
- §5 — No accounts / no cross-session persistence.

## Constraints, Guardrails & NFRs

**Responsible AI**
- Expert Validation (FR-9) is mandatory — never present an auto-validated-only claim as final without disclosing unreviewed edges.
- The cross-model design is itself a Responsible-AI feature: the validating model must not be the model that drafted the DAG.
- Market Research (FR-5–FR-7) states "no relevant events found" rather than fabricating.

**Privacy / Security**
- DIAL API keys (Drafting + Validator) and the Tavily key are backend-only secrets — never in client-side code, commits, logs, or on the React frontend.
- Uploaded data is not persisted beyond the session, nor sent anywhere beyond the LLM proxies and Tavily required for analysis. `[ASSUMPTION]`

**NFRs**
- **Reliability (demo-critical):** The live demo path must not crash or hang; every failure degrades to a specific, actionable error, never a blank screen or stack trace on stage.
- **Latency:** Each pipeline step targets a live-demo-tolerable window; the full Causal Insight pipeline targets 60-90 seconds end-to-end `[ASSUMPTION]`, or the UI shows clear intermediate progress.
- **Explainability:** Every AI-generated claim is traceable to the pipeline step that produced it.

## Handoff

Next: `bmad-ux` (screens per mode), then `bmad-architecture` (scaled to a quick spine given the timeline), then `bmad-create-epics-and-stories`.
