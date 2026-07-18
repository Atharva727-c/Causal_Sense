"""Guardrail against editorializing language in any LLM-generated narrative
text -- defense-in-depth on top of the system-prompt instruction, the same
pattern as query_agent.py's code-safety blocklist. A narrative should be a
plain statement of what was computed, not a subjective, hedging, or causal
claim the underlying computation doesn't support (a descriptive aggregate
never proves causation, however "obvious" it looks).
"""
from __future__ import annotations

import re

_EDITORIALIZING_PATTERNS = [
    r"\bsurprisingly\b", r"\bclearly\b", r"\bobviously\b", r"\bdefinitely\b",
    r"\bremarkably\b", r"\binterestingly\b", r"\bdramatically\b",
    r"\bdrastically\b", r"\bmassively\b", r"\bhugely\b", r"\bshockingly\b",
    r"\bunfortunately\b", r"\bimpressively\b", r"\bnotably\b",
    r"\bstrikingly\b", r"\bamazing(ly)?\b", r"\bincredibl[ey]\b",
    r"\boutstanding\b", r"\bproves?\b", r"\bcaused? by\b", r"\bcauses?\b",
    r"\bleads? to\b", r"\bdrives?\b", r"\bresults? in\b", r"\bdue to\b",
    r"\bbecause of\b", r"\bclearly shows?\b", r"\bclearly indicates?\b",
    r"\bbest\b", r"\bworst\b",
]
_EDITORIALIZING_RE = re.compile("|".join(_EDITORIALIZING_PATTERNS), re.IGNORECASE)


def strip_editorializing(text: str) -> str:
    """Returns text unchanged if it's plain and factual; returns an empty
    string if it contains subjective/hedging/causal language, so a flagged
    explanation is dropped rather than shown -- the numeric answer itself is
    never affected, only the free-text description of how it was computed."""
    if not text or _EDITORIALIZING_RE.search(text):
        return ""
    return text
