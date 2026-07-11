# Version Verification Review — Architecture Spine Stack Table

**Reviewed doc:** `ARCHITECTURE-SPINE.md` (Causal Sense, architecture-Causal_sense-2026-07-11)
**Review date:** 2026-07-11
**Method:** WebSearch + WebFetch against PyPI, GitHub Releases, npm/GitHub mirrors, and official docs (not training-data recall).

## Verdict: PASS with minor gaps

Every version claim the doc makes as "verified" checks out against live sources as of 2026-07-11. No fabricated version numbers found. A few unpinned dependencies are flagged as acceptable-but-worth-a-line-item gaps, and one interop caveat on DoWhy/EconML ATE semantics is worth carrying into implementation notes.

## Detailed findings

### 1. Python `>=3.12,<3.14` — CONFIRMED
- **DoWhy 0.14** (PyPI, latest release, 2025-11-08): `Requires-Python: <3.14,>=3.9`. Confirmed directly from the PyPI project page. Matches the doc's claim exactly.
- **EconML 0.16.0** (PyPI, latest release, 2025-07-10): `Requires-Python: >=3.9`; classifiers list Python 3.9–3.13 explicitly (wheels built for cp39–cp313), no 3.14 wheels/classifier. Matches the doc's "supports up to Python 3.13" claim.
- Conclusion: the upper bound of `<3.14` is correctly driven by DoWhy's hard `Requires-Python` ceiling; EconML's lack of 3.13+ wheels reinforces the same ceiling. The pin is accurate and current.

### 2. FastAPI `~0.139` "current stable" — CONFIRMED
- GitHub release `fastapi/fastapi` tag `0.139.0`, published 2026-07-01, is the latest tagged release. PyPI project page corroborates 0.139.0 as latest upload (2026-07-01). Doc's "current stable, verified 2026-07-11" claim holds as of the review date.

### 3. React `19.2.7` "verified" — CONFIRMED
- GitHub `facebook/react` release tag `v19.2.7`, dated 2026-06-01 (patch fixing a Server Actions FormData regression from 19.2.6). This is the latest 19.x patch as of the review date. Claim holds.

### 4. Vite `8.1.4` + `@vitejs/plugin-react` v6 — CONFIRMED
- GitHub `vitejs/vite` releases list `v8.1.4` as the top-of-list release, dated 2026-07-09 — 2 days before the doc's "verified 2026-07-11" date, consistent.
- `vitejs/vite-plugin-react` releases: latest is `plugin-react@6.0.3` (2026-06-23), confirming v6 is current stable and compatible with Vite 8 (v6 dropped Babel in favor of Oxc for React Refresh transform per plugin changelog/blog notes).
- Both figures are real, current, and internally consistent (Vite 8 + plugin-react v6 pairing is the documented recommended combination).

### 5. DoWhy + EconML interop for FR-10 ATE estimation — CONFIRMED as viable, with a caveat to note
- EconML ships a `econml.dowhy.DoWhyWrapper` specifically to be driven through DoWhy's `causal_estimators` API, and DoWhy's own `dowhy.causal_estimators.econml` module wraps EconML estimators — this is an officially supported, bidirectional integration, not an assumed one.
- DoWhy's `estimate_effect()` supports `target_units="ate"/"att"/"atc"` with `estimand_type="nonparametric-ate"`, which is the mechanism FR-10 would use.
- **Caveat found (py-why/dowhy GitHub issue #1289):** users report confusion/inconsistency when using EconML's DML estimator through DoWhy for continuous-treatment ATE at specific dose points — the DML-derived ATE can be insensitive to the `control_value`/`treatment_value` range in ways that diverge from a plain GLM/logistic baseline, and the coefficient reported by the underlying model doesn't always match the ATE DoWhy returns. This is a known usability/interpretation gap, not a broken integration — worth a one-line implementation note in `tools/ate_estimation.py`'s docstring or a smoke-test to confirm ATE output matches expectations for the demo's treatment variable(s), especially if any continuous (non-binary) treatment is used.

### 6. Unpinned dependencies — acceptable gap, flagged for the record
| Dependency | Doc's pin | Assessment |
| --- | --- | --- |
| pandas | "latest stable" | Acceptable — pandas is a stable, low-churn substrate dependency; no known DoWhy/EconML pandas ceiling was surfaced in the above searches. Low risk for a short-lived hackathon build. |
| openai SDK (DIAL) | "latest stable" | Confirmed latest is `openai` Python SDK v2.45.0 (released 2026-07-09). No DIAL-specific compatibility statement was found in official OpenAI docs (DIAL is EPAM's proxy, not an OpenAI-documented target) — this is a real gap: the doc should note that DIAL compatibility is asserted by the DIAL adapter's own contract/testing, not by upstream openai SDK docs, since no source verifies "latest openai SDK works against DIAL" as a general claim. |
| tavily-python | "latest stable" | Not independently verified — no search was run against Tavily's own release notes/PyPI for a specific version or known breaking changes. Acceptable to leave unpinned for a build substrate, but the "latest stable" language wasn't itself verified the way FastAPI/React/Vite were; recommend either pinning at implementation start or dropping the implied-verification framing for consistency with the rest of the table. |
| uv | "existing project package manager (already in use)" | No version claim made — not applicable to this audit. |

## Summary of what was and wasn't independently verified
- **Independently verified via live web sources:** DoWhy 0.14 Python range, EconML 0.16.0 Python range, FastAPI 0.139.0, React 19.2.7, Vite 8.1.4, @vitejs/plugin-react 6.0.3, DoWhy↔EconML integration existence and a real interop caveat, openai SDK current version (2.45.0).
- **Not independently verified (flagged, not necessarily wrong):** tavily-python's actual latest version/changelog; pandas's actual latest version number; whether openai SDK v2.x has any behavioral quirks specifically against a DIAL-style OpenAI-compatible proxy (inherently unverifiable from public OpenAI docs since DIAL is a third-party gateway).

## Recommendation
No changes required to the pinned versions — they are accurate and current as of 2026-07-11. Two small doc improvements suggested (not blocking):
1. Add a one-line caveat near FR-10 / `ate_estimation.py` about the DML+continuous-treatment ATE interpretation gotcha (GitHub issue #1289) so whoever implements ATE Estimation tests it against the demo dataset's actual treatment type.
2. Either verify+pin `tavily-python` and `pandas` to specific versions or soften "latest stable" to "unpinned by design" so the table doesn't imply the same verification rigor applied to FastAPI/React/Vite.
