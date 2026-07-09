# PRD Quality Review — Causal Sense (prd-Causal_sense-2026-07-08)

## Overall verdict

This PRD is decision-ready and unusually well-specified for a 5-6 day hackathon build: FRs carry concrete testable thresholds, trade-offs are named rather than smoothed over, and the judging-criteria-shaped Success Metrics section is a deliberate, well-executed fit to its actual audience rather than a rubric deviation. The main risks are mechanical, not structural: three inline `[ASSUMPTION]` tags (Constraints/Guardrails and Cross-Cutting NFRs) never made it into the §9 Assumptions Index, and UJ protagonists are role-generic rather than named individuals, which will cost the downstream UX pass some grounding. Nothing here blocks a build decision.

## 1. Decision-readiness — strong

Decisions are stated as decisions, not buried as considerations: FR-11 states outright "the system never infers mode from free-text intent" and backs it with a Non-Goal and a forged-idea cross-reference, rather than hedging. §6.2 Out of Scope gives an actual reason per omission ("not needed for a live single-session demo," "judges will not bring their own CSV"), and the one live tension — tunable confidence-threshold UI — gets a genuine `[NOTE FOR PM]` at line 238 flagging it as a possible Responsible-AI talking point, not a safe checkpoint. Open Questions (§8) are genuinely unresolved (model pairing not yet chosen, anomaly count pending dataset arrival, Tavily query-derivation strategy undecided) rather than rhetorical.

### Findings
- **medium** No demo-day contingency decision (no §) — FR-1's edge case and the Reliability NFR cover *graceful degradation* if the pipeline errors, but there is no stated decision for what the presenter does if the live pipeline stalls/fails mid-demo (e.g., fallback to a recorded run). Given the entire PRD is keyed to "must prove itself live, on stage... without failure" (§1), this is the single highest-consequence failure mode and it's implicitly assumed away rather than decided. *Fix:* Add a one-line contingency decision (own it or explicitly non-goal it) near the Reliability NFR (§ Cross-Cutting NFRs).

## 2. Substance over theater — strong

No persona bloat (JTBD-style bullets in §2.1, not a persona gallery) and no floating differentiation section. NFRs are not boilerplate: FR-1's 5-second latency, FR-7's 0.8 confidence threshold, FR-8's 50-row/2-variable floor, and the 60-90s end-to-end target are all product-specific numbers, several explicitly marked as retunable placeholders rather than dressed up as final. The Vision statement (§1) is specific to this product's bet ("not just 'X correlates with Y' but 'X caused Y, by this much, controlling for these confounders'") and would not swap cleanly into a generic BI-tool PRD — it earns its place.

No findings — this dimension does not need one.

## 3. Strategic coherence — strong

The thesis is explicit and singular: causal answer over correlation, with a human-in-the-loop cross-model validation as the trust mechanism. Feature order follows the locked 7-step pipeline (§4.3), not ease-of-build. The Success Metrics section is intentionally structured around the six weighted hackathon judging criteria rather than generic product metrics (DAU/MAU-style activity counters are absent) — this is the correct shape for a PRD whose "market" is a judging panel, and it is executed well: SM-1/SM-4/SM-6 map directly to the thesis (AI use, novelty of the cross-model validator, responsible-AI), and two counter-metrics (SM-C1, SM-C2) explicitly name what NOT to optimize, preventing the SM section from degenerating into "everything is good."

No findings — this dimension does not need one.

## 4. Done-ness clarity — strong, with minor gaps

Every FR (FR-1 through FR-13) carries at least one numeric or binary-testable consequence — e.g. FR-2's "≥95% of cases," FR-7's "0.8" threshold with explicit accept/reject behavior, FR-9's requirement to name cause/effect/effect-size/confounders "in a single readable paragraph, with no unexplained statistical terms." Vague-adjective language is largely absent; the one instance of "gracefully" (FR-3's feature-specific NFR, line 113) is immediately anchored to a concrete consequence ("partial output + explanation") rather than left as an adjective.

### Findings
- **low** "Domain-agnostic" claim in FR-3 lacks a test (§4.1 FR-3) — "Anomaly/pattern detection is domain-agnostic... so it works across arbitrary tabular datasets" is a structural claim with no stated verification method (e.g., a second, unrehearsed dataset run pre-submission). *Fix:* Add a consequence like "verified against at least one non-demo dataset before submission" or explicitly defer verification as a risk.

## 5. Scope honesty — adequate (mechanical gap, not a judgment gap)

§5 Non-Goals is substantive (six explicit exclusions, each with a reason or cross-reference), and §6.2 de-scopes multi-variable what-if, accounts, non-CSV sources, and threshold tuning honestly with rationale rather than silent omission. Open-items density (3 Open Questions, ~13 `[ASSUMPTION]` tags, 1 `[NOTE FOR PM]`) is proportionate for a hackathon-stakes PRD — not the density you'd expect on a PRD that's a green light for a production system.

### Findings
- **medium** Assumptions Index roundtrip is incomplete (§9 vs. Constraints/Guardrails and Cross-Cutting NFRs) — three inline `[ASSUMPTION]` tags never made it into §9: the CSV-non-persistence guardrail (line 285), the no-logging-without-consent guardrail (line 289), and the 60-90 second end-to-end latency target (line 294). Anyone using §9 as the single "what's unconfirmed" checklist will miss these. *Fix:* Add three entries to §9, or note in §9's header that Constraints/NFRs assumptions are tracked inline only.

## 6. Downstream usability — adequate

Glossary (§3) terms are used consistently in the FRs that follow (DAG, ATE, Confounder, Drafting/Validator LLM, Mode, Solution Orchestrator, NL Insight all recur with the same meaning). FR IDs (FR-1–FR-13), UJ IDs (UJ-1–UJ-3), and SM IDs (SM-1–SM-6 plus SM-C1/C2) are contiguous with no gaps or duplicates, and cross-references (e.g. "see FR-10 Out of Scope," "see forged-idea Key Decisions") resolve to real sections.

### Findings
- **medium** UJ protagonists are role-generic, not named (§2.3) — UJ-1's persona is "A team presenter," UJ-2's is "Same session as UJ-1," UJ-3's is "A user unsure whether their data has anything interesting in it." The rubric's downstream-usability bar wants a named protagonist carrying context inline; the handoff to `bmad-ux` (named in the Handoff section) will need to invent or request names/context to spec concrete screens. Given the small, known cast (the team + judges), this is a light fix. *Fix:* Name the presenter (e.g. one of Atharva/Sahil/Aaishwarya/Rupesh) and give the UJ-3 persona a one-line concrete context (role, what dataset, why they're unsure) before handoff to UX.

## 7. Shape fit — strong

This is correctly shaped as a chain-top PRD for a small, known-audience live demo: UJs are load-bearing because the product genuinely has a UX (four modes, a live pipeline) and the judges are a real, if narrow, "user." The Success Metrics section deliberately mirrors the hackathon's six weighted judging criteria instead of forcing generic engagement/retention metrics onto a one-shot demo — this is the right shape-fit call for this product, not a deviation to penalize. The MVP-scope section (§6) reads as problem-solving-kind scope logic (narrow, bulletproof pipeline over broad format support), consistent with SM-C2's explicit rationale.

No findings — this dimension does not need one.

## Mechanical notes

- **Assumptions Index roundtrip gap**: three inline `[ASSUMPTION]` tags (lines 285, 289, 294 — Constraints/Guardrails and Cross-Cutting NFRs sections) are not indexed in §9. All ten §9 entries do resolve to a real inline tag (no orphan index entries), so the gap is one-directional (inline → index).
- **Glossary case drift (low)**: §3's Expert Validation entry uses lowercase "validator LLM" mid-sentence while the dedicated glossary entry two lines below capitalizes "Drafting LLM / Validator LLM" as a term. Purely cosmetic; the FRs downstream consistently use the capitalized form.
- **ID continuity**: FR-1–FR-13, UJ-1–UJ-3, SM-1–SM-6/SM-C1–C2 are all contiguous with no gaps or duplicates. Cross-references checked (FR-10 Out of Scope ↔ FR-13 consequence, §2.2 ↔ NFR-Performance, forged-idea references) all resolve.
- **UJ protagonist naming**: see Downstream Usability finding above — protagonists are roles, not names, throughout §2.3.
- **Required sections**: all sections expected for a chain-top, small-team hackathon PRD are present (Vision, Target User, Glossary, Features/FRs, Non-Goals, MVP Scope, Success Metrics, Open Questions, Assumptions Index, Constraints/Guardrails, Cross-Cutting NFRs, Handoff). Nothing structurally missing.
