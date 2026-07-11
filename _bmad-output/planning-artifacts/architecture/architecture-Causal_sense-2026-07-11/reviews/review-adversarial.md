---
title: Adversarial Review — Causal Sense Architecture Spine
reviewed: ARCHITECTURE-SPINE.md (2026-07-11) against prd.md (2026-07-08, updated 2026-07-11)
reviewer-mode: adversarial (construct two independent builders, both spec-compliant, who diverge)
date: 2026-07-11
---

# Adversarial Review — Causal Sense Architecture Spine

## Method

For each finding below: a concrete pair of builders, each following every AD to the letter, who nonetheless
produce components that don't compose. Severity is ranked by (a) whether it breaks the live demo path
(UJ-1/UJ-3) and (b) whether it's discoverable only at integration time, not at code-review time.

---

## Finding 1 — SEVERITY: CRITICAL — No mechanism for the async Causal Analysis job to pause for FR-9's human-in-the-loop edge review

**AD(s) implicated:** AD-6, AD-7, capability map row for FR-9.

**The gap:** AD-6 fixes the async contract as exactly two endpoints: `POST /causal-analysis` (returns `job_id`)
and `GET /jobs/{job_id}` (polls `{status, current_step, result?}`). FR-9 requires that below-threshold DAG
edges **escalate to the user**, who accepts/rejects each one, and **rejected edges are excluded from FR-10**
(ATE Estimation) — i.e. ATE must not run until the human decision is in. Neither AD-6 nor AD-7's tool-sequence
table (`EDA → Market Research → DAG Draft → Expert Validation → ATE Estimation → NL Insight`) says what happens
when Expert Validation produces edges that need a human decision mid-sequence. There is no endpoint anywhere
in the spine for submitting an edge accept/reject decision, and no `status` value describing "waiting on user
input."

**Concrete divergence:** Teammate A (owns the Orchestrator/job runner, AD-6) builds the job to run straight
through `Expert Validation → ATE Estimation` non-interactively — auto-validated edges pass, escalated edges
are silently treated as auto-rejected (or auto-accepted) so the job can complete and return a `result`, because
nothing in the contract tells them to pause. Teammate B (owns the Expert Validation UI / edge-review screen,
per FR-9) builds a screen that expects to `PATCH` a decision back to a paused job before ATE ever runs. On
integration: the UI shows an edge-review screen for a job that has already finished computing ATE using
whatever default the orchestrator picked — the human's decision arrives too late to affect FR-10, silently
violating FR-9's stated causal-integrity guarantee, on stage, in front of judges.

**Verdict:** Needs a new/tightened AD, not deferrable — this sits directly on UJ-1's climax path and SM-6
(Responsible & Ethical AI). Recommend: add an AD-6a (or extend AD-6) that (1) adds a `status` enum including an
explicit "awaiting_review" value, (2) adds `PATCH /jobs/{job_id}/edges` (or similar) for submitting per-edge
decisions, and (3) states in the AD-7 sequence table that Expert Validation is a hard barrier — ATE Estimation
does not start until all escalated edges for that job have a decision (accept/reject) recorded.

---

## Finding 2 — SEVERITY: HIGH — PipelineContext's Market Research field and DAG edge shape are named, not schematized

**AD(s) implicated:** AD-4.

**The gap:** AD-4 says PipelineContext threads "Market Research result (incl. optional DAG)" between Tools, and
that a Tool "writes only its own designated field." That pins *field ownership*, not *field shape*. Nowhere in
the spine (or PRD) is there a schema for:
- the plain-text summary (FR-5/FR-6/FR-7): is it a bare `str`, a `{summary: str, sources: [{title, url}]}`
  object, markdown with inline citations, or something else?
- the DAG when produced (FR-8): a list of edge objects, an adjacency structure, a serialized `networkx` graph,
  node/edge arrays with what field names (`source`/`target` vs `cause`/`effect`)?
- the DAG **edge status** values referenced in the task brief and implied by FR-9's prose
  ("auto-validate," "escalate," "accept/reject") — no literal enum (e.g. `auto_validated` / `escalated` /
  `user_accepted` / `user_rejected`) appears anywhere in the PRD or the spine. It exists only as narrative prose.

**Concrete divergence:** Rupesh's NL Insight tool (`tools/nl_insight.py`, consuming forwarded MR context per
FR-12/FR-13) is built expecting `PipelineContext.market_research` to be a string. The core team's Market
Research tool (`tools/market_research.py`) instead writes `{summary, sources, dag}` as a nested object because
that's what feeds FR-5's UI "source attribution" requirement. Rupesh's tool either crashes trying to
string-format a dict, or silently drops source attribution because it never expected the field to carry it.
Separately, whoever implements DAG Draft picks `status: "auto_validated"` while whoever implements Expert
Validation's UI checks for `status == "validated"` — the escalation banner never renders because the string
never matches.

**Verdict:** Needs a tightened AD. AD-4 should either (a) inline a minimal field-level schema (even just a
short Pydantic-style stub) for `market_research_result` and `dag` in the spine itself, or (b) explicitly
delegate this to a named companion schema doc that all Tool owners are required to consult before writing to
PipelineContext, with the edge-status enum values pinned as literal strings. Given the 2026-07-13 deadline,
the cheapest fix is a 10-line Pydantic model added directly under AD-4, not a new companion document.

---

## Finding 3 — SEVERITY: HIGH — Cross-mode PipelineContext handoff (FR-13/FR-5) has no defined lifecycle: per-run or per-session?

**AD(s) implicated:** AD-4, AD-5, AD-7.

**The gap:** AD-5 says session state — "uploaded data, PipelineContext" — lives in-memory "keyed by
`session_id`," implying one PipelineContext persists across the whole session, reusable across mode switches.
But AD-7's mode → Tool-sequence table treats each mode as a fixed, closed sequence run by the Orchestrator, with
no notation for "read prior PipelineContext content produced by a different mode earlier in this session."
Talk to Your Data's row reads `Schema Inference (FR-2) → NL Insight` — it does not re-run Market Research and
has no explicit "merge with any existing session PipelineContext" step. Yet FR-13 explicitly requires: "plus
any market-research context forwarded from FR-5/FR-6" in automatic insights, and FR-12's grounding also implies
awareness of anything already known about the dataset. The task brief's exact question — does AD-7 silently
drop this handoff — is confirmed: the table as written gives no signal either way.

**Concrete divergence:** Teammate A (Orchestrator) implements each mode call as instantiating a **fresh**
PipelineContext scoped to that single Orchestrator invocation (defensible reading of AD-7's "fixed... sequence"
language, and simpler to implement/test in isolation). Teammate B (Rupesh, NL Insight/Talk to Your Data) builds
FR-13's "plus market-research context forwarded from FR-5/FR-6" on the assumption that the *session's*
PipelineContext (per AD-5) is automatically available and pre-populated whenever Market Research ran earlier in
the same session. On stage: presenter runs Market Research standalone, then switches to Talk to Your Data in
the same session — the automatic insights never surface the market-research context because the Orchestrator
handed NL Insight a blank PipelineContext for the new mode invocation. FR-13's explicit consequence ("plus any
market-research context forwarded from FR-5/FR-6") silently fails, discoverable only at integration/demo
rehearsal, not in either teammate's unit tests.

**Verdict:** Needs a tightened AD. Recommend adding an explicit line to AD-7 (or a new AD-7a): "Each Orchestrator
invocation reads the session's existing PipelineContext from the session store (AD-5) if one exists for that
`session_id`, and merges newly-produced fields into it rather than starting blank; Tools never overwrite a
field already populated by an earlier mode in the same session unless that mode is explicitly being re-run."

---

## Finding 4 — SEVERITY: MEDIUM-HIGH — Async job and synchronous Talk to Your Data can race on the same session's PipelineContext

**AD(s) implicated:** AD-5, AD-6.

**The gap:** AD-5 fixes session state as a single in-memory, single-process store keyed by `session_id`. AD-6
makes Causal Analysis async (a background job mutates PipelineContext over 60-90s) while Talk to Your Data is
synchronous. Nothing in AD-5 or AD-6 says what happens if a user (or the demo presenter, mid-rehearsal, or a
judge poking at the UI) fires a Talk to Your Data request against the same `session_id` while a Causal Analysis
job is still running. There's no mutex/versioning/read-write discipline specified for the shared
per-session PipelineContext.

**Concrete divergence:** Teammate A (async job runner) writes each Tool's output field into the session's
PipelineContext as soon as that Tool completes (so `GET /jobs/{job_id}` can report `current_step` progress by
reading it back). Teammate B (Talk to Your Data's synchronous handler) reads the *same* PipelineContext object
to answer a question mid-flight. If A is between "EDA done, Market Research in progress" and B's synchronous
call reads a half-written MR field (or hits a Python dict mutated concurrently by another thread/async task),
the result is either a partial-data answer with no error signal, or a race condition that is close to
un-reproducible outside the exact timing hit live on stage — the worst possible failure mode for a
Reliability-NFR-critical demo.

**Verdict:** Acceptable to push to Deferred **only if** paired with an explicit interim guardrail in the spine
now: e.g. "a session with a Causal Analysis job in-flight (`status != done|error`) rejects/queues concurrent
Talk to Your Data or a second Causal Analysis request against the same `session_id` with a specific
`error_code`" — this is a two-line addition to AD-5 or AD-6, cheap enough it shouldn't wait. If the team decides
single-user-per-session-at-a-time is a safe assumption for a live demo (only one presenter, one session, one
action at a time), that assumption should be written down explicitly rather than left implicit, since it's the
kind of thing a nervous demo presenter double-clicking a button could violate.

---

## Finding 5 — SEVERITY: MEDIUM — `GET /jobs/{job_id}` status/current_step string values are unenumerated

**AD(s) implicated:** AD-6.

**The gap:** AD-6 specifies the response shape `{status, current_step, result?}` but never enumerates the
legal values of `status` (e.g. `queued`/`running`/`done`/`error` — or `completed`/`failed`, etc.) or what
strings `current_step` takes (Tool class names? snake_case Tool file names? human-readable labels like
"Drafting DAG..."?). The Consistency Conventions table pins Tool *class* naming (`<Noun>Tool`) but not the
wire-format strings emitted for job polling.

**Concrete divergence:** Sahil (frontend, polling for progress/completion per FR-14/NFR-Latency) codes the UI
to treat `status === "completed"` as terminal-success. The Orchestrator/job-runner implementer emits `"done"`
instead. The progress UI polls forever, never shows the causal answer, and the presenter is staring at a
spinner on stage — a Reliability-NFR violation caused purely by an unpinned string enum, not a logic bug.

**Verdict:** Needs a small tightening, not a new AD — add an explicit enum for `status`
(e.g. `queued | running | awaiting_review | done | error`, folding in Finding 1's needed value) and either an
enum or a documented naming convention for `current_step` (recommend: the six Tool names as defined in the
namespace table, e.g. `eda`, `market_research`, `dag_draft`, `expert_validation`, `ate_estimation`,
`nl_insight`). Cheap fix, should go in before two people start coding against AD-6 independently.

---

## Finding 6 — SEVERITY: LOW-MEDIUM — PipelineContext mutation discipline (in-place vs. copy-and-merge) unspecified

**AD(s) implicated:** AD-4, AD-5.

**The gap:** AD-4 says a Tool "writes only its own designated field," which describes *which* field, not *how*
the write becomes durable. Is PipelineContext handed to each Tool by reference (mutated in place, with the
Orchestrator relying on that same object already sitting in the session store) or is it passed as an immutable
value that each Tool returns a modified copy of, which the Orchestrator must then explicitly persist back to the
session store per AD-5?

**Concrete divergence:** Teammate A writes `tools/eda.py` assuming Pydantic-model-style immutability (returns a
new PipelineContext via `.model_copy(update=...)`), while the Orchestrator implementer assumes Tools mutate the
object in place and never re-persists the return value to the session store. Result: EDA's output is computed
correctly, returned in the Tool's AD-3 envelope `data` field, but silently never lands back in the session's
canonical PipelineContext — so the *next* Tool in the sequence (or a later mode in the same session, compounding
Finding 3) reads a stale/empty context.

**Verdict:** Acceptable to push to Deferred/implementation convention *if* stated explicitly as a one-line rule
now (e.g. "Tools return an updated PipelineContext value; the Orchestrator alone is responsible for persisting
it to the session store after each Tool call") — this is cheap to pin and removes an entire class of "my Tool
worked in isolation but the pipeline lost my output" bugs during integration.

---

## Finding 7 — SEVERITY: LOW — AD-3 (Tool envelope) and AD-8 (API error contract) have no defined translation rule

**AD(s) implicated:** AD-3, AD-8.

**The gap:** A Tool can return `status: "degraded"` or `"error"` inside its own envelope (AD-3). AD-8 governs
"every non-2xx API response." Nothing states the mapping: does a Tool-level `"error"` always become a non-2xx
API response (and if so, how does `{status, data, message}` map onto `{error_code, message, actionable_hint}` —
where does `error_code` come from if the Tool only gave a `message`)? Does `"degraded"` return HTTP 200 with a
degraded payload, or 207-style partial success?

**Concrete divergence:** Two people implementing two different API routes (e.g. the EDA route and the Market
Research route) each invent their own ad hoc mapping from Tool envelope to HTTP response — one treats
`"degraded"` as 200, another as a non-2xx with a generic `error_code: "DEGRADED"` the frontend was never told to
expect, producing an inconsistent error/warning UI across modes.

**Verdict:** Acceptable to push to Deferred/tighten-later — lower stakes than Findings 1-5 since it's a
UX-polish inconsistency rather than a demo-breaking one, but flag it for a one-paragraph addition to AD-8
("Tool `degraded` maps to HTTP 200 with the degraded envelope passed through as-is in the response body; Tool
`error` maps to a non-2xx AD-8 envelope, with `error_code` derived from a fixed per-Tool error taxonomy") before
frontend and backend owners diverge.

---

## Finding 8 — SEVERITY: LOW — FR-15 (Proactive Nudge) capability map governance looks miskeyed

**AD(s) implicated:** Capability → Architecture Map.

**The gap:** The map lists FR-15 (Proactive AI Nudge Post-EDA) as governed by AD-4 only, and lives in
`frontend/src/modes/*`. But FR-15's trigger condition ("if something notable was detected and Causal Analysis
hasn't run yet") requires the frontend to know *whether Causal Analysis has already run in this session* — a
piece of state that, per AD-5, lives in the backend's session-scoped PipelineContext, not in frontend-only
state. There's no API surface listed anywhere (map or AD-7) for the frontend to query "has Causal Analysis run
for this session_id yet," and AD-9 keeps the frontend as "a pure REST/JSON client" with no direct data access.

**Concrete divergence:** Sahil's frontend tracks "has Causal Analysis run" as local React state (reset on page
refresh); a nudge that should suppress itself after Causal Analysis already ran reappears after a refresh
because the frontend has no backend-sourced signal to check against, contradicting FR-15's stated condition.

**Verdict:** Acceptable to push to Deferred — minor UX-correctness edge case, not a wire-contract fight between
two backend builders, but worth a one-line note that the EDA/session response should carry a
`causal_analysis_run: bool` (or equivalent) flag the frontend can key off, rather than reconstructing it
client-side.

---

## Summary Table

| # | Finding | Severity | Needs new/tightened AD, or Deferred? |
| --- | --- | --- | --- |
| 1 | No pause/resume mechanism for FR-9 human review inside the async job | Critical | New/tightened AD-6 — do now |
| 2 | PipelineContext MR/DAG field shapes + edge-status enum unpinned | High | Tighten AD-4 — do now |
| 3 | Cross-mode PipelineContext handoff (FR-13/FR-5) lifecycle undefined in AD-7 | High | Tighten AD-7 — do now |
| 4 | Async job vs. sync Talk-to-Your-Data race on shared session PipelineContext | Medium-High | Deferred, with an interim one-line guardrail added now |
| 5 | Job `status`/`current_step` string values unenumerated | Medium | Tighten AD-6 — cheap, do now |
| 6 | PipelineContext mutation discipline (in-place vs. copy) unspecified | Low-Medium | Deferred/convention — one line now |
| 7 | Tool envelope (AD-3) -> API error contract (AD-8) translation unspecified | Low | Deferred/tighten later |
| 8 | FR-15 nudge suppression state has no backend-sourced signal | Low | Deferred |
