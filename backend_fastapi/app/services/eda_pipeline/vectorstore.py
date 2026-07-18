"""Session-scoped hybrid vector store.

Chroma provides the dense (embedding) half and rich metadata filtering; a
persisted BM25 index provides the sparse/keyword half. Results are fused with
Reciprocal Rank Fusion (RRF) so a chunk that ranks well on *either* signal
surfaces — which is exactly what "hybrid search" buys you.

Each chunk carries metadata (notably ``cell_index`` and ``section``) so the
ReAct agent can filter retrieval and jump back to the exact notebook cell.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.services.eda_pipeline.chunking import Chunk
from app.services.eda_pipeline.embeddings import ChromaEmbeddingFunction
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9_]+")
_RRF_K = 60  # standard RRF damping constant


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _matches(meta: dict, where: Optional[dict]) -> bool:
    """Simple equality metadata filter for the BM25 side (mirrors Chroma `where`)."""
    if not where:
        return True
    return all(meta.get(k) == v for k, v in where.items())


class HybridVectorStore:
    """Chroma dense search + BM25 keyword search, fused with RRF, per session."""

    def __init__(self, ws: Workspace) -> None:
        import chromadb

        self.ws = ws
        self._client = chromadb.PersistentClient(path=str(ws.chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name=ws.collection_name,
            embedding_function=ChromaEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
        # BM25 corpus persisted alongside so it survives restarts.
        self._corpus: list[dict[str, Any]] = self._load_corpus()
        self._bm25 = None
        self._rebuild_bm25()

    # ── persistence of the BM25 corpus ────────────────────────────────────────
    def _load_corpus(self) -> list[dict[str, Any]]:
        if self.ws.bm25_path.exists():
            try:
                return json.loads(self.ws.bm25_path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Corrupt bm25.json — starting fresh")
        return []

    def _save_corpus(self) -> None:
        self.ws.bm25_path.write_text(json.dumps(self._corpus), encoding="utf-8")

    def _rebuild_bm25(self) -> None:
        if not self._corpus:
            self._bm25 = None
            return
        try:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in self._corpus])
        except Exception as exc:  # pragma: no cover
            logger.warning("BM25 unavailable (%s) — dense-only retrieval", exc)
            self._bm25 = None

    # ── writes ────────────────────────────────────────────────────────────────
    def add_chunks(self, chunks: list[Chunk]) -> int:
        chunks = [c for c in chunks if c.text.strip()]
        if not chunks:
            return 0
        self._collection.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )
        for c in chunks:
            self._corpus.append({"id": c.id, "text": c.text, "metadata": c.metadata})
        self._save_corpus()
        self._rebuild_bm25()
        logger.info("Added %d chunks to session %s", len(chunks), self.ws.session_id)
        return len(chunks)

    @property
    def count(self) -> int:
        return len(self._corpus)

    # ── search ──────────────────────────────────────────────────────────────
    def _dense_ranked(self, query: str, n: int, where: Optional[dict]) -> list[str]:
        try:
            res = self._collection.query(
                query_texts=[query],
                n_results=n,
                where=where or None,
            )
            return (res.get("ids") or [[]])[0]
        except Exception as exc:
            logger.warning("Dense query failed: %s", exc)
            return []

    def _sparse_ranked(self, query: str, n: int, where: Optional[dict]) -> list[str]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        ranked: list[str] = []
        for i in order:
            item = self._corpus[i]
            if scores[i] <= 0:
                break
            if _matches(item["metadata"], where):
                ranked.append(item["id"])
            if len(ranked) >= n:
                break
        return ranked

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        where: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """Hybrid top-k. Returns dicts: ``{id, text, metadata, score}``."""
        if not self._corpus:
            return []
        pool = max(k * 3, 12)
        dense = self._dense_ranked(query, pool, where)
        sparse = self._sparse_ranked(query, pool, where)

        # Reciprocal Rank Fusion across the two rankings.
        fused: dict[str, float] = {}
        for ranking in (dense, sparse):
            for rank, cid in enumerate(ranking):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)

        by_id = {c["id"]: c for c in self._corpus}
        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        out: list[dict[str, Any]] = []
        for cid, score in top:
            item = by_id.get(cid)
            if item:
                out.append({
                    "id": cid,
                    "text": item["text"],
                    "metadata": item["metadata"],
                    "score": round(score, 6),
                })
        return out


def get_store(ws: Workspace) -> HybridVectorStore:
    return HybridVectorStore(ws)
