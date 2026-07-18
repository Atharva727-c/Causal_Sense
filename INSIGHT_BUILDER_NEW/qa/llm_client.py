"""Thin wrapper around the Azure-OpenAI-compatible LLM endpoint.

This is the only place in the codebase that talks to an LLM. Every call in
and out of it is plain text/JSON — the LLM never receives raw data rows and
never returns a computed number itself, only structured intent or narration.
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    AzureOpenAI,
    InternalServerError,
    RateLimitError,
)

load_dotenv()

_client: AzureOpenAI | None = None

MAX_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 1.0
# Only transient/infrastructure failures are retried here -- never auth or
# bad-request errors, which won't resolve themselves on a second attempt.
_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)


_REQUIRED_ENV_VARS = ("DIAL_API_KEY", "DIAL_API_VERSION", "DIAL_ENDPOINT", "DIAL_MODEL")


def llm_available() -> bool:
    """Whether the LLM endpoint is configured at all. LLM-backed pipeline
    nodes are conditional on this, so an unconfigured environment skips them
    cleanly instead of raising KeyError mid-pipeline."""
    return all(os.environ.get(v) for v in _REQUIRED_ENV_VARS)


def get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        _client = AzureOpenAI(
            api_key=os.environ["DIAL_API_KEY"],
            api_version=os.environ["DIAL_API_VERSION"],
            azure_endpoint=os.environ["DIAL_ENDPOINT"],
        )
    return _client


def complete(prompt: str, system: str | None = None) -> str:
    client = get_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=os.environ["DIAL_MODEL"],
                messages=messages,
            )
            return response.choices[0].message.content or ""
        except _RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(_RETRY_BASE_DELAY_SECONDS * (2**attempt))
    raise last_error
