"""Async Anthropic client with streaming support and system-prompt management."""
from __future__ import annotations
import logging
from functools import lru_cache
from typing import Any, AsyncIterator

import anthropic
from anthropic.types import MessageParam

from app.config import get_settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)
_s = get_settings()

# ── System prompts ────────────────────────────────────────────────────────────

BASE_PROMPT = """You are CausalSense, an elite quantitative analyst and strategic advisor.
You specialise in causal inference, market intelligence, and data-driven decisions.
You always structure outputs in clean markdown with clear sections.
You quantify uncertainty with probability-weighted scenarios whenever possible.
Your scenario tables use exactly these columns: Scenario | Probability | Expected Outcome | Key Drivers | Risk Flags."""

EDA_PROMPT = """You are CausalSense EDA Agent — an expert data scientist for exploratory data analysis.
Given data context you:
1. Assess data quality (missing values, outliers, type anomalies)
2. Compute descriptive statistics (mean, median, std, skewness, kurtosis, IQR)
3. Surface distributions and pairwise correlations
4. Flag anomalies and structural patterns
5. Conclude with 5-7 prioritised, actionable recommendations
Structure your answer with: **Data Quality**, **Univariate Analysis**, **Bivariate Correlations**, **Anomalies**, **Recommendations** sections."""

MARKET_RESEARCH_PROMPT = """You are CausalSense Market Research Agent — a tier-1 strategy consultant.
For every research request you produce:
1. Market sizing: TAM / SAM / SOM with methodology
2. Competitive landscape with estimated market-share breakdown
3. Consumer segmentation and behavioural drivers
4. Macro + micro trend analysis (5-year horizon)
5. A 12-row probability-weighted scenario table (4 bull / 4 base / 4 bear)
Every figure must be sourced or estimated with explicit assumptions stated."""

_PROMPTS: dict[str | None, str] = {
    None: BASE_PROMPT,
    "eda": EDA_PROMPT,
    "market_research": MARKET_RESEARCH_PROMPT,
}


def get_system_prompt(mode: str | None) -> str:
    return _PROMPTS.get(mode, BASE_PROMPT)


# ── Mock text used when no API key is configured ─────────────────────────────

_MOCK: dict[str | None, str] = {
    None: (
        "**Mock response** — CausalSense is running in demo mode.\n\n"
        "To enable real AI responses, set `ANTHROPIC_API_KEY` in your `.env` file.\n\n"
        "| Scenario | Probability | Expected Outcome | Key Drivers | Risk Flags |\n"
        "|----------|-------------|-----------------|-------------|------------|\n"
        "| Bull case | 25 % | +40 % revenue | Adoption surge | Competition |\n"
        "| Base case | 50 % | +15 % revenue | Steady growth | Macro slowdown |\n"
        "| Bear case | 25 % | -5 % revenue | Market saturation | Regulatory change |"
    ),
    "eda": (
        "**EDA Mock** — Running statistical analysis on your dataset.\n\n"
        "**Data Quality:** 2 % missing values in `revenue` column; no duplicate rows detected.\n\n"
        "**Univariate Analysis:** `revenue` mean = 142 k, std = 38 k, skewness = 0.82 (right-tailed).\n\n"
        "**Recommendations:** 1) Impute missing revenue with median. 2) Log-transform for modelling."
    ),
    "market_research": (
        "**Market Research Mock** — Conducting competitive intelligence.\n\n"
        "**Market Sizing:** TAM = $4.2 B · SAM = $1.1 B · SOM = $85 M (Year 1 target).\n\n"
        "**Competitive Landscape:** Player A holds ~32 % share; Players B & C each ~18 %.\n\n"
        "**12 Scenarios:** Bull (4): disruption-led upside 35-60 %. Base (4): organic growth 10-20 %. Bear (4): contraction -5 to -15 %."
    ),
}


# ── LLM service ───────────────────────────────────────────────────────────────

class LLMService:
    """Thin async wrapper around the Anthropic SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or _s.anthropic_api_key
        self._client: anthropic.AsyncAnthropic | None = (
            anthropic.AsyncAnthropic(api_key=key, timeout=_s.claude_timeout)
            if key
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    def mock_text(self, mode: str | None) -> str:
        return _MOCK.get(mode, _MOCK[None])

    async def stream(
        self,
        messages: list[MessageParam],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """
        Async generator that yields (event_type, event_data) pairs:
          - ("text",          {"text": str})
          - ("input_tokens",  {"count": int})
          - ("output_tokens", {"count": int})
          - ("tool_use",      {"id": str, "name": str})
        """
        if self._client is None:
            raise LLMError("No ANTHROPIC_API_KEY configured.", status_code=503)

        kwargs: dict[str, Any] = {
            "model": _s.claude_model,
            "max_tokens": max_tokens or _s.claude_max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    match event.type:
                        case "content_block_delta":
                            if hasattr(event.delta, "text"):
                                yield "text", {"text": event.delta.text}
                        case "message_start":
                            if event.message.usage:
                                yield "input_tokens", {"count": event.message.usage.input_tokens}
                        case "message_delta":
                            if event.usage:
                                yield "output_tokens", {"count": event.usage.output_tokens}
                        case "content_block_start":
                            blk = event.content_block
                            if getattr(blk, "type", None) == "tool_use":
                                yield "tool_use", {"id": blk.id, "name": blk.name}
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Connection error: {exc}", status_code=503)
        except anthropic.RateLimitError:
            raise LLMError("Rate limit exceeded.", status_code=429)
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error: {exc.message}", status_code=502)

    async def complete(
        self,
        messages: list[MessageParam],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Non-streaming single completion (for tool orchestration)."""
        if self._client is None:
            raise LLMError("No ANTHROPIC_API_KEY configured.", status_code=503)
        response = await self._client.messages.create(
            model=_s.claude_model,
            max_tokens=max_tokens or _s.claude_max_tokens,
            messages=messages,
            system=system or BASE_PROMPT,
        )
        return response.content[0].text if response.content else ""


@lru_cache(maxsize=1)
def get_llm() -> LLMService:
    return LLMService()
