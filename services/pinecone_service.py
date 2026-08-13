"""
Pinecone service (section 37 of the spec).

Pinecone is responsible ONLY for vector storage and semantic similarity
search. It never stores application-of-record data — that lives in
Supabase Postgres (see supabase_service.py / document_chunks table for the
metadata pointer back to each vector).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import config

logger = logging.getLogger(__name__)


@dataclass
class VectorMatch:
    id: str
    score: float
    metadata: Dict


class PineconeService:
    def upsert_documents(self, vectors: List[Dict], namespace: Optional[str] = None) -> int:
        """vectors: [{id, values, metadata}, ...]. Returns count upserted."""
        raise NotImplementedError

    def search(self, embedding: List[float], top_k: int = 10,
               namespace: Optional[str] = None, filter: Optional[Dict] = None) -> List[VectorMatch]:
        raise NotImplementedError

    def delete_document(self, document_id: str, namespace: Optional[str] = None) -> None:
        raise NotImplementedError


class RealPineconeService(PineconeService):
    def __init__(self, api_key: str, index_name: str):
        from pinecone import Pinecone  # imported lazily so the package is optional in mock mode

        self._pc = Pinecone(api_key=api_key)
        self._index = self._pc.Index(index_name)

    def upsert_documents(self, vectors: List[Dict], namespace: Optional[str] = None) -> int:
        self._index.upsert(vectors=vectors, namespace=namespace or "")
        return len(vectors)

    def search(self, embedding: List[float], top_k: int = 10,
               namespace: Optional[str] = None, filter: Optional[Dict] = None) -> List[VectorMatch]:
        result = self._index.query(
            vector=embedding, top_k=top_k, namespace=namespace or "",
            filter=filter, include_metadata=True,
        )
        return [
            VectorMatch(id=m["id"], score=m["score"], metadata=m.get("metadata", {}))
            for m in result.get("matches", [])
        ]

    def delete_document(self, document_id: str, namespace: Optional[str] = None) -> None:
        self._index.delete(filter={"document_id": document_id}, namespace=namespace or "")


class InMemoryPineconeService(PineconeService):
    """
    Cosine-similarity in-memory index used when PINECONE_API_KEY is not
    configured. Lets the RAG agent and knowledge base run end to end in
    development and tests without any external dependency.
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Dict]] = {}  # namespace -> id -> {values, metadata}

    def upsert_documents(self, vectors: List[Dict], namespace: Optional[str] = None) -> int:
        ns = namespace or ""
        bucket = self._store.setdefault(ns, {})
        for v in vectors:
            bucket[v["id"]] = {"values": v["values"], "metadata": v.get("metadata", {})}
        return len(vectors)

    def search(self, embedding: List[float], top_k: int = 10,
               namespace: Optional[str] = None, filter: Optional[Dict] = None) -> List[VectorMatch]:
        ns = namespace or ""
        bucket = self._store.get(ns, {})
        scored = []
        for vec_id, entry in bucket.items():
            if filter and not self._matches_filter(entry["metadata"], filter):
                continue
            score = self._cosine(embedding, entry["values"])
            scored.append(VectorMatch(id=vec_id, score=score, metadata=entry["metadata"]))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]

    def delete_document(self, document_id: str, namespace: Optional[str] = None) -> None:
        ns = namespace or ""
        bucket = self._store.get(ns, {})
        to_delete = [vid for vid, e in bucket.items() if e["metadata"].get("document_id") == document_id]
        for vid in to_delete:
            del bucket[vid]

    @staticmethod
    def _matches_filter(metadata: Dict, filter: Dict) -> bool:
        for key, val in filter.items():
            if metadata.get(key) != val:
                return False
        return True

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (norm_a * norm_b)


def get_pinecone_service() -> PineconeService:
    if config.using_real_pinecone:
        try:
            return RealPineconeService(api_key=config.PINECONE_API_KEY, index_name=config.PINECONE_INDEX)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to initialize real Pinecone client, falling back to in-memory: %s", exc)
    logger.info("Pinecone service running in in-memory mode (no PINECONE_API_KEY configured)")
    return InMemoryPineconeService()
