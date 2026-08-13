"""
Investigation Orchestrator (sections 14 & 15).

Wires the nine agents together in the fixed sequence the spec requires:

  Claim Extraction -> Claim Analysis -> (Web Research + RAG in parallel)
  -> Evidence -> Source Credibility -> Contradiction -> Verification
  -> Report Generation

Deliberately NOT "claim -> LLM -> true/false" (section 55). Each stage
persists to Supabase and updates investigation_agents so the frontend can
show real, non-simulated progress.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

from agents.claim_agent import ClaimExtractionAgent
from agents.claim_analysis_agent import ClaimAnalysisAgent
from agents.research_agent import WebResearchAgent
from agents.rag_agent import RAGAgent
from agents.evidence_agent import EvidenceAgent
from agents.source_agent import SourceCredibilityAgent
from agents.contradiction_agent import ContradictionAgent
from agents.verification_agent import VerificationAgent
from agents.report_agent import ReportGeneratorAgent
from services.supabase_service import SupabaseService
from services.llm_service import LLMProvider
from services.search_service import SearchProvider
from services.embedding_service import EmbeddingProvider
from services.pinecone_service import PineconeService

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


STATUS_SEQUENCE = [
    ("extracting", 10), ("researching", 35), ("retrieving", 55),
    ("evaluating", 75), ("verifying", 90), ("completed", 100),
]


class InvestigationOrchestrator:
    def __init__(self, db: SupabaseService, llm: LLMProvider, search: SearchProvider,
                 embeddings: EmbeddingProvider, pinecone: PineconeService):
        self.db = db
        self.claim_agent = ClaimExtractionAgent(db, llm)
        self.analysis_agent = ClaimAnalysisAgent(db, llm)
        self.research_agent = WebResearchAgent(db, search)
        self.rag_agent = RAGAgent(db, embeddings, pinecone)
        self.evidence_agent = EvidenceAgent(db, llm)
        self.source_agent = SourceCredibilityAgent(db, llm)
        self.contradiction_agent = ContradictionAgent(db, self.research_agent)
        self.verification_agent = VerificationAgent(db, llm)
        self.report_agent = ReportGeneratorAgent(db)

    def _set_status(self, investigation_id: str, status: str, progress: int):
        self.db.update_investigation(investigation_id, {"status": status, "progress": progress})

    async def run(self, investigation_id: str) -> Dict:
        investigation = self.db.get_investigation(investigation_id)
        if not investigation:
            raise ValueError(f"Investigation {investigation_id} not found")

        try:
            self._set_status(investigation_id, "extracting", STATUS_SEQUENCE[0][1])
            extraction = await self.claim_agent.run(
                investigation_id, content=investigation["original_content"],
            )
            extracted_claims = extraction.get("claims", [])
            if not extracted_claims:
                self.db.update_investigation(investigation_id, {
                    "status": "unverifiable", "progress": 100, "completed_at": _now(),
                })
                return {"claims": [], "status": "unverifiable"}

            processed_claims: List[Dict] = []

            for raw_claim in extracted_claims:
                claim_row = self.db.create_claim({
                    "investigation_id": investigation_id,
                    "claim_text": raw_claim["claim"],
                    "normalized_claim": raw_claim["claim"],
                    "claim_type": raw_claim.get("claim_type", "factual"),
                    "category": investigation.get("category"),
                    "importance": raw_claim.get("importance", 0.7),
                })
                claim_id = claim_row["id"]

                self._set_status(investigation_id, "researching", STATUS_SEQUENCE[1][1])
                analysis = await self.analysis_agent.run(
                    investigation_id, claim_text=raw_claim["claim"], category=investigation.get("category"),
                )

                research_task = self.research_agent.run(
                    investigation_id, search_queries=analysis["search_queries"],
                )
                rag_task = self.rag_agent.run(
                    investigation_id, claim_text=raw_claim["claim"],
                )
                research, rag_result = await asyncio.gather(research_task, rag_task)

                self._set_status(investigation_id, "retrieving", STATUS_SEQUENCE[2][1])
                contradiction = await self.contradiction_agent.run(
                    investigation_id, claim_text=raw_claim["claim"],
                )

                all_web_results = research["results"] + contradiction["results"]
                # de-dupe by URL again after merging the two search passes
                dedup = {r["url"]: r for r in all_web_results if r.get("url")}
                merged_results = list(dedup.values())

                self._set_status(investigation_id, "evaluating", STATUS_SEQUENCE[3][1])
                source_ratings = await self.source_agent.run(
                    investigation_id, evidence_urls=[r["url"] for r in merged_results],
                )

                evidence_result = await self.evidence_agent.run(
                    investigation_id, claim_text=raw_claim["claim"],
                    raw_results=merged_results, source_ratings=source_ratings["ratings"],
                )

                # Persist evidence rows (web research + evidence classification)
                stored_evidence: List[Dict] = []
                for e in evidence_result["evidence"]:
                    stored = self.db.create_evidence({"claim_id": claim_id, **e})
                    stored_evidence.append(stored)

                # RAG evidence stored as "contextual" unless explicitly classified
                for rag_item in rag_result.get("matches", []):
                    stored = self.db.create_evidence({
                        "claim_id": claim_id,
                        "title": rag_item["title"],
                        "url": rag_item["url"] or "internal://knowledge-base",
                        "publisher": rag_item.get("publisher") or "Knowledge base",
                        "published_at": None,
                        "snippet": rag_item["snippet"],
                        "evidence_type": "contextual",
                        "relevance_score": rag_item["relevance_score"],
                        "credibility_score": 0.75,
                        "source_type": "knowledge_base",
                    })
                    stored_evidence.append(stored)

                supporting = [e for e in stored_evidence if e["evidence_type"] == "supporting"]
                contradicting_ev = [e for e in stored_evidence if e["evidence_type"] == "contradicting"]
                neutral = [e for e in stored_evidence if e["evidence_type"] in ("neutral", "contextual")]

                self._set_status(investigation_id, "verifying", STATUS_SEQUENCE[4][1])
                verdict = await self.verification_agent.run(
                    investigation_id, claim_text=raw_claim["claim"],
                    supporting=supporting, contradicting=contradicting_ev,
                    neutral=neutral, rag_evidence=rag_result.get("matches", []),
                )

                updated_claim = self.db.update_claim(claim_id, {
                    "verdict": verdict["verdict"],
                    "veracity_score": verdict["veracity_score"],
                    "confidence_score": verdict["confidence"],
                    "summary": verdict["summary"],
                    "key_findings": verdict["key_findings"],
                    "limitations": verdict["limitations"],
                })

                report = await self.report_agent.run(
                    investigation_id, claim=updated_claim, evidence=stored_evidence,
                )

                processed_claims.append({"claim": updated_claim, "report": report})

            self.db.update_investigation(investigation_id, {
                "status": "completed", "progress": 100, "completed_at": _now(),
            })
            return {"claims": processed_claims, "status": "completed"}

        except Exception as exc:
            logger.exception("Investigation %s failed", investigation_id)
            self.db.update_investigation(investigation_id, {
                "status": "failed", "error_message": str(exc), "completed_at": _now(),
            })
            raise
