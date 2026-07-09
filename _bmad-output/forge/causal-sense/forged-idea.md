# Causal Sense — Forged Idea

## Identity
AI-native causal inference engine. One product, one question it answers: *what actually caused this?* Everything else serves that answer. EDA and Market Research are entry points that lead users toward causal inference — not independent features.

## Architecture

```
User uploads data
        ↓
[ EDA ] [ Market Research ] [ Causal Analysis ] [ What-if Sim ]
        ↓ (user picks mode)
Solution Orchestrator (composes tools for chosen mode)
        ↓
Final Answer + AI-native nudge ("spike detected — run causal analysis?")
```

**No LLM-based intent recognizer.** User selects mode explicitly. AI adds value *after* selection via proactive suggestions, not before via routing.

## Locked Pipeline (Causal Analysis mode — the flagship)

| Step | Owner | Role |
|---|---|---|
| 1. EDA | Rupesh | Understand data, detect patterns & anomalies |
| 2. Market Research | Atharva | Search real-world events as **upstream** causal candidates — enriches the DAG before it's drafted |
| 3. LLM DAG Draft | Core | Build causal graph from data patterns + external context |
| 4. Expert Validation | Core | Hybrid: LLM council scores edge confidence; high-confidence edges auto-validated; ambiguous edges escalated to user in plain language |
| 5. ATE Estimation | Core | Isolate true causal effect, control for confounders (DoWhy / EconML) |
| 6. What-if Simulator | Sahil | Post-causation intervention simulator — P(Y\|do(X)) |
| 7. NL Insight Builder | Aaishwarya | Plain-language explanation of causal results |

## Standalone Modes

| Mode | Steps used | Entry point behavior |
|---|---|---|
| EDA | Step 1 only | After output, AI nudges toward Causal Analysis if anomaly detected |
| Market Research | Step 2 only | Standalone event/context search for a given topic or timeframe |
| Causal Analysis | Steps 1–7 | Full flagship pipeline |
| What-if Sim | Step 6 only | Requires prior causal analysis to have been run |

## Key Decisions

- **Explicit UI mode buttons** over LLM intent recognizer — more reliable, no misrouting risk, faster to build
- **AI-native nudge post-EDA** — proactive suggestion toward deeper analysis, not pre-selection routing
- **Market research runs upstream** — informs DAG construction, not post-hoc justification
- **Expert validation is hybrid** — LLM council auto-validates high-confidence edges; user only reviews ambiguous ones in plain language (no causal expertise required)
- **What-if simulator uses causal graph**, not plain regression — P(Y|do(X))
- **Causal inference is the core identity** — all features serve one answer
- **Single shared-tools agent** — all steps share tools, no per-teammate silos

## Rejected Options

- LLM-based intent recognizer — fragile, misrouting on a math-backed tool is worse than a chatbot
- 4 separate per-teammate agents — creates redundant tools, prevents tool sharing
- Market research as downstream explainer — post-hoc rationalization, hallucination risk
- User-only DAG validation without AI assistance — excludes non-expert users
- Full LLM council validation with no human — collective hallucination risk on novel/proprietary data
- Generic DS assistant framing — weak on Innovation criterion (20% of score)

## Surviving Weak Points

- LLMs can hallucinate DAG edges — expert validation canvas is mandatory, not optional; hybrid council mitigates but doesn't eliminate
- AI tool use (25% of score, highest weight) — Claude's role in each step must be explicitly articulated in demo and docs
- 7-step pipeline scope — anchor the demo to one end-to-end dataset (e.g. gold prices) to keep it tight

## Handoff
Feed this into `bmad-prd` or `bmad-spec` to define requirements, then `bmad-architecture` for the technical spine.
Recommended demo dataset: gold prices 2020–2023 (clear anomalies, well-known causal events, good for judges).
