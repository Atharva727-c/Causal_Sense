"""Thin wrapper around the Azure/DIAL OpenAI-compatible chat endpoint used by the agent.

Credentials are read from environment variables only (DIAL_API_KEY, DIAL_ENDPOINT,
DIAL_API_VERSION, DIAL_MODEL) -- no secrets are hardcoded here. See .env.example
for the variable names; populate a local, gitignored .env with the values from
LLM.py to run this locally.
"""

from __future__ import annotations

import json
import os
import re

from openai import AzureOpenAI

_DEFAULT_ENDPOINT = "https://ai-proxy.lab.epam.com"
_DEFAULT_API_VERSION = "2024-02-01"
_DEFAULT_MODEL = "gpt-5.5-2026-04-24-reasoning"

_client: AzureOpenAI | None = None


def get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("DIAL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DIAL_API_KEY environment variable is not set. Copy the key from LLM.py "
                "into a local .env file (see .env.example) -- it must not be hardcoded in source."
            )
        _client = AzureOpenAI(
            api_key=api_key,
            api_version=os.environ.get("DIAL_API_VERSION", _DEFAULT_API_VERSION),
            azure_endpoint=os.environ.get("DIAL_ENDPOINT", _DEFAULT_ENDPOINT),
        )
    return _client


def chat(messages: list[dict], model: str | None = None, response_format: dict | None = None) -> str:
    client = get_client()
    kwargs = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = client.chat.completions.create(
        model=model or os.environ.get("DIAL_MODEL", _DEFAULT_MODEL),
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


def _sanitize(obj):
    if isinstance(obj, str):
        return obj.replace("�", "'")
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    return obj


def chat_json(system_prompt: str, user_prompt: str, model: str | None = None) -> dict:
    """Ask the model for a JSON object, robust to models that don't support
    an explicit JSON response_format."""
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_prompt
            + "\n\nRespond with ONLY a single valid JSON object. No markdown fences, no commentary. "
            "Use plain ASCII punctuation only (straight quotes, regular hyphens) -- no smart "
            "quotes, em-dashes, or other special punctuation.",
        },
    ]
    try:
        content = chat(messages, model=model, response_format={"type": "json_object"})
        result = _extract_json(content)
    except Exception:
        content = chat(messages, model=model)
        result = _extract_json(content)
    return _sanitize(result)
