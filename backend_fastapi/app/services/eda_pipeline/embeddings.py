"""Embedding backends for the vector store.

Two implementations behind one tiny interface:

* :class:`DialEmbedder`  — real embeddings via the DIAL Azure-OpenAI proxy
  (deployment name from ``DIAL_EMBEDDINGS_DEPLOYMENT``). Used when a key is set.
* :class:`HashEmbedder`  — a deterministic, dependency-free, offline embedder
  (hashed bag-of-words). Not semantically meaningful, but lets the whole
  retrieval path run and be tested with no network / no API key.

:func:`get_embedder` picks automatically. :class:`ChromaEmbeddingFunction`
adapts either one to Chroma's ``EmbeddingFunction`` protocol.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)
_s = get_settings()

_TOKEN = re.compile(r"[a-z0-9_]+")


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


# ══════════════════════════════════════════════════════════════════════════════
# Offline deterministic fallback
# ══════════════════════════════════════════════════════════════════════════════
class HashEmbedder:
    """Hashed bag-of-words → fixed-dim L2-normalized vector. Deterministic."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall((text or "").lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


# ══════════════════════════════════════════════════════════════════════════════
# DIAL (Azure OpenAI) embeddings
# ══════════════════════════════════════════════════════════════════════════════
class DialEmbedder:
    """Wraps ``langchain_openai.AzureOpenAIEmbeddings`` pointed at DIAL."""

    dim = 0  # unknown until first call; not needed for cosine search

    def __init__(self) -> None:
        from langchain_openai import AzureOpenAIEmbeddings

        self._client = AzureOpenAIEmbeddings(
            azure_endpoint=_s.dial_endpoint,
            api_key=_s.dial_api_key,
            api_version=_s.dial_api_version,
            azure_deployment=_s.dial_embeddings_deployment,
            timeout=_s.dial_timeout,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


# ══════════════════════════════════════════════════════════════════════════════
# Selection + Chroma adapter
# ══════════════════════════════════════════════════════════════════════════════
@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    if _s.dial_api_key:
        try:
            emb = DialEmbedder()
            logger.info("Embeddings: DIAL deployment %r", _s.dial_embeddings_deployment)
            return emb
        except Exception as exc:  # pragma: no cover
            logger.warning("DIAL embedder unavailable (%s) — falling back to HashEmbedder", exc)
    logger.warning("Embeddings: offline HashEmbedder (no DIAL_API_KEY) — retrieval is keyword-ish only")
    return HashEmbedder()


class ChromaEmbeddingFunction:
    """Adapter so Chroma can call our :class:`Embedder`.

    Implemented as a duck-typed callable (``__call__(input) -> embeddings``),
    which satisfies Chroma's ``EmbeddingFunction`` protocol across 0.4/0.5.
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or get_embedder()

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002 (Chroma's arg name)
        return self._embedder.embed_documents(list(input))

    # Chroma (>=1.x) calls ``embed_query(input=[...])`` on the query path — it
    # must accept the ``input`` kwarg and return one embedding per query string.
    def embed_query(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._embedder.embed_documents(list(input))

    # Chroma persists the EF name to guard against silent backend swaps.
    def name(self) -> str:
        return f"causalsense-{type(self._embedder).__name__.lower()}"
