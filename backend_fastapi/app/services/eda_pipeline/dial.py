"""DIAL (EPAM Azure-OpenAI proxy) clients.

Two entry points:
* :func:`chat_json` — raw ``openai.AzureOpenAI`` call used for the turn-1
  analysis. Supports multimodal (text + image) content and forces a JSON object
  response. Reasoning-model-safe (omits ``temperature``, uses
  ``max_completion_tokens``).
* :func:`get_langchain_chat` — a ``langchain_openai.AzureChatOpenAI`` bound to
  the same deployment, for the LangGraph ReAct agent.

When ``DIAL_API_KEY`` is unset the module runs in **mock mode** so the whole
pipeline is exercisable offline (the sandbox can't reach the DIAL endpoint).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
_s = get_settings()


def available() -> bool:
    return bool(_s.dial_api_key)


# ══════════════════════════════════════════════════════════════════════════════
# Raw openai client (turn-1 multimodal analysis)
# ══════════════════════════════════════════════════════════════════════════════
@lru_cache(maxsize=1)
def _openai_client():
    from openai import AzureOpenAI

    return AzureOpenAI(
        api_key=_s.dial_api_key,
        api_version=_s.dial_api_version,
        azure_endpoint=_s.dial_endpoint,
        timeout=_s.dial_timeout,
    )


def _completion_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": _s.dial_chat_deployment}
    if _s.dial_is_reasoning_model:
        kwargs["max_completion_tokens"] = _s.dial_max_completion_tokens
    else:
        kwargs["max_tokens"] = _s.dial_max_completion_tokens
        kwargs["temperature"] = 0
    return kwargs


def chat_json(
    system: str,
    user_content: Any,
    *,
    force_json: bool = True,
) -> dict[str, Any]:
    """
    Single completion returning a parsed JSON object.

    ``user_content`` may be a plain string or an OpenAI multimodal content list
    (mix of ``{"type":"text",...}`` and ``{"type":"image_url",...}`` blocks).
    """
    if not available():
        return _mock_turn1()

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    kwargs = _completion_kwargs()
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = _openai_client().chat.completions.create(messages=messages, **kwargs)
        raw = resp.choices[0].message.content or "{}"
        return _loads_lenient(raw)
    except Exception as exc:
        logger.exception("DIAL chat_json failed")
        raise RuntimeError(f"DIAL chat call failed: {exc}") from exc


def _loads_lenient(raw: str) -> dict[str, Any]:
    """Parse JSON, tolerating stray markdown fences the model may add."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


# ══════════════════════════════════════════════════════════════════════════════
# LangChain chat model (ReAct agent)
# ══════════════════════════════════════════════════════════════════════════════
@lru_cache(maxsize=1)
def get_langchain_chat():
    """AzureChatOpenAI bound to the DIAL deployment for the ReAct agent."""
    from langchain_openai import AzureChatOpenAI

    kwargs: dict[str, Any] = dict(
        azure_endpoint=_s.dial_endpoint,
        api_key=_s.dial_api_key,
        api_version=_s.dial_api_version,
        azure_deployment=_s.dial_chat_deployment,
        timeout=_s.dial_timeout,
    )
    if _s.dial_is_reasoning_model:
        kwargs["max_completion_tokens"] = _s.dial_max_completion_tokens
        # LangChain always sends `temperature`; reasoning models only accept the
        # default (1). Non-reasoning models get 0 for determinism.
        kwargs["temperature"] = 1
    else:
        kwargs["max_tokens"] = _s.dial_max_completion_tokens
        kwargs["temperature"] = 0
    return AzureChatOpenAI(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# Mock mode (offline)
# ══════════════════════════════════════════════════════════════════════════════
def _mock_turn1() -> dict[str, Any]:
    return {
        "facts": (
            "- **[MOCK]** DIAL not configured; this is placeholder output.\n"
            "- Dataset explored via steps 1-6; see notebook cells.\n"
            "- Set `DIAL_API_KEY` in `.env` to enable real analysis."
        ),
        "detailed": (
            "[[CELL=2 | SECTION=Load | KIND=cell]]\n"
            "Mock interpretation of the data-loading cell.\n\n"
            "[[SECTION=Transformations | KIND=step8]]\n"
            "Mock suggestion: standardize numerics, log-transform skewed columns."
        ),
        "user_response": (
            "**[Mock EDA response]**\n\nDIAL is not configured, so this is a placeholder. "
            "Add `DIAL_API_KEY` to `.env` to get a real, plot-aware analysis."
        ),
        "followups": [
            "Which features correlate most with the target?",
            "Are there outliers I should worry about?",
            "What transformations do you recommend?",
            "Is there evidence of seasonality or trend?",
            "What additional data would improve a model?",
        ],
    }
