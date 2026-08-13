"""
RAG Agent (section 19).

Embeds the claim and retrieves semantically similar chunks from Pinecone,
via document_chunks metadata in Supabase for traceability back to the
source document.
"""
from __future__ import annotations

from typing import Dict, List

from agents.base import BaseAgent
from services.embedding_service import EmbeddingProvider
from services.pinecone_service import PineconeService
from services.supabase_service import SupabaseService

DEFAULT_NAMESPACE = "knowledge-base"


class RAGAgent(BaseAgent):
    name = "rag"

    def __init__(self, db: SupabaseService, embeddings: EmbeddingProvider, pinecone: PineconeService):
        super().__init__(db)
        self.embeddings = embeddings
        self.pinecone = pinecone

    async def execute(self, investigation_id: str, claim_text: str, top_k: int = 5, **kwargs) -> Dict:
        embedding = await self.embeddings.embed(claim_text)
        matches = self.pinecone.search(embedding=embedding, top_k=top_k, namespace=DEFAULT_NAMESPACE)

        evidence: List[Dict] = []
        for match in matches:
            meta = match.metadata or {}
            evidence.append({
                "title": meta.get("title", "Knowledge base document"),
                "url": meta.get("source", ""),
                "publisher": meta.get("source"),
                "snippet": meta.get("content_preview", ""),
                "relevance_score": round(match.score, 3),
                "document_id": meta.get("document_id"),
                "category": meta.get("category"),
                "country": meta.get("country"),
                "document_type": meta.get("document_type"),
            })

        return {"matches": evidence, "count": len(evidence)}
