"""Thin wrapper around the Tavily web search API used by web_search_api.py.

Credentials are read from the TAVILY_API_KEY environment variable only -- no
secrets are hardcoded here. See .env.example.
"""

from __future__ import annotations

import os

import requests

_URL = "https://api.tavily.com/search"


def search(query: str, max_results: int = 5, search_depth: str = "basic") -> list[dict]:
    """Run a single web search and return a list of {title, url, content} dicts."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY environment variable is not set. Copy the key from "
            "web_search_api.py into a local .env file (see .env.example) -- it must not "
            "be hardcoded in source."
        )
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
    }
    response = requests.post(_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json().get("results", [])


def search_many(queries: list[str], max_results_per_query: int = 4, search_depth: str = "basic") -> list[dict]:
    """Run several queries and return deduplicated results (by url). Queries that
    error out (rate limit, network, etc.) are skipped rather than failing the batch."""
    seen_urls: set[str] = set()
    combined: list[dict] = []
    for query in queries:
        try:
            results = search(query, max_results=max_results_per_query, search_depth=search_depth)
        except Exception:
            continue
        for result in results:
            url = result.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            combined.append({**result, "query": query})
    return combined
