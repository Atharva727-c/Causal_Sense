# Reconciliation: forged-idea.md → prd.md

**Input:** `_bmad-output/forge/causal-sense/forged-idea.md`
**Derived artifact:** `_bmad-output/planning-artifacts/prds/prd-Causal_sense-2026-07-08/prd.md`

## Method
Walked every section of forged-idea.md (Identity, Architecture, Locked Pipeline, Standalone Modes,
Key Decisions, Rejected Options, Surviving Weak Points, Handoff) and checked whether the content,
its rationale, and its tone survive in prd.md — distinguishing genuine gaps from intentional
evolutions the user made during PRD drafting (team ownership → joint core-team ownership; Market
Research → Tavily; Expert Validation → cross-model instead of "LLM council"; product now explicitly
domain-agnostic rather than gold-price-anchored). Per instructions, those evolutions are NOT flagged.

## Content confirmed present (no gap)
- Architecture diagram flow (upload → mode → orchestrator → answer + nudge) — §1 Vision, §3 Glossary
  (Solution Orchestrator), FR-11/FR-12/FR-13.
- No-LLM-intent-recognizer decision — FR-11, §5 Non-Goals, UJ-3.
- Market research upstream (not post-hoc) — §4.2 description explicitly says "not as post-hoc
  justification (explicitly rejected in the forged idea)".
- Hybrid validation with human-in-loop, auto-validate high-confidence / escalate ambiguous — FR-7
  (now cross-model, an intentional evolution, not a gap).
- What-if sim uses causal graph, not regression — FR-10.
- Causal inference as sole identity — §1 Vision opening line.
- Shared-tools/no-per-teammate-silos architecture — FR-13 Shared Tool Orchestration.
- Rejected: "full LLM council with no human" (collective hallucination risk) — §5 Non-Goals, restated
  with rationale.
- Surviving weak point "LLM hallucinate DAG edges" → Expert Validation mandatory — Constraints and
  Guardrails section, restated with rationale.
- Surviving weak point "AI tool use is highest-weighted criterion" → SM-1, explicitly restated.
- Surviving weak point "anchor demo to one dataset" → gold prices demo dataset carried through §1,
  UJ-1, §6.1, §7.
- Handoff chain (bmad-prd/spec → bmad-architecture) — carried forward and extended in PRD's own
  Handoff section.

## Real gaps found

1. **Rejected alternative "Generic DS assistant framing — weak on Innovation criterion (20% of
   score)" has no trace in the PRD.** This is the one rejected-option entry that ties directly to a
   scored judging criterion still active in the PRD (SM-4, Innovation & Creativity, 20%), yet SM-4
   never references *why* a generic-assistant framing was rejected or *what differentiates* Causal
   Sense from one. This is actionable demo-messaging guidance that risks being lost since it isn't
   even indirectly implied elsewhere.

2. **The identity framing "EDA and Market Research are entry points that lead users toward causal
   inference — not independent features" is diluted.** The PRD captures the mechanics (nudge in
   FR-12, standalone Market Research in FR-4) but never restates the framing that these modes exist
   to *funnel* users toward Causal Analysis rather than stand as peer features. §4.2's "Also runnable
   standalone" phrasing, if read in isolation, reads closer to "independent feature" than the source
   intent.

3. **Rejected alternative "4 separate per-teammate agents — creates redundant tools, prevents tool
   sharing" is not restated anywhere**, even though the PRD's shared-orchestrator design (FR-13)
   depends on this exact rationale. Since ownership itself changed (an intentional evolution), the
   original "per-teammate agent" framing might read as fully obsolete — but the *tool-sharing*
   argument is still the load-bearing justification for FR-13's architecture and is worth a one-line
   callback so a reader doesn't have to cross-reference forged-idea.md to know why shared tooling
   matters.

4. **Tone/comparative reasoning lost on the intent-recognizer rejection.** Forged-idea's specific
   framing — "misrouting on a math-backed tool is worse than a chatbot" — is a vivid, judge-facing
   argument for why explicit mode buttons matter (stakes are higher for a causal-inference tool than
   a conversational one). PRD's Non-Goals only says "explicitly rejected — see forged-idea Rejected
   Options," delegating the rationale rather than carrying the argument's persuasive force into the
   evaluation-facing document. Minor, but worth a sentence if the PRD is meant to stand alone for
   judges/evaluators without them reading the forged-idea doc.

## Not flagged (by design, not oversight)
- Team/ownership changes, Tavily specifically, cross-model (not "LLM council") Expert Validation,
  domain-agnostic framing over gold-price anchoring — all confirmed intentional evolutions per task
  instructions.
- Most Rejected Options and Key Decisions rationale is deliberately *not* duplicated — PRD §0
  explicitly states it "builds on forged-idea.md ... without duplicating it; that document remains
  the authoritative source for *why* alternatives were rejected." This is a stated editorial choice,
  not a silent drop, so it is not counted as a gap except where (as in #1 above) the missing rationale
  is directly load-bearing for a still-active PRD section (SM-4) and its absence creates a real risk
  of the argument being lost before the demo.
