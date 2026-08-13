"""
Evidence Agent (section 21).

Normalizes raw web-research + RAG results into classified, scored evidence
records ready to persist to Supabase. Classification (supporting /
contradicting / neutral / contextual) is delegated to the LLM per item,
with a conservative keyword-based fallback so the pipeline still runs in
mock mode.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from agents.base import BaseAgent
from services.llm_service import LLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Evidence Agent. Given a claim and a single search result
(title + snippet), classify the result's relationship to the claim as exactly one of:
"supporting", "contradicting", "neutral", or "contextual". Also give a relevance_score
(0-1, how directly it addresses the claim) and be honest if it's only tangential.
Respond ONLY with JSON: {"evidence_type": "...", "relevance_score": 0.0}
"""

CONTRADICTION_HINTS = ("false", "debunked", "denies", "denied", "incorrect", "no evidence", "myth", "hoax")
SUPPORT_HINTS = ("confirms", "confirmed", "announced", "verified", "true")


class EvidenceAgent(BaseAgent):
    name = "evidence"

    def __init__(self, db, llm: LLMProvider):
        super().__init__(db)
        self.llm = llm

    async def execute(self, investigation_id: str, claim_text: str,
                       raw_results: List[Dict], source_ratings: Dict[str, Dict], **kwargs) -> Dict:
        from urllib.parse import urlparse

        evidence: List[Dict] = []
        for item in raw_results[:8]:
            domain = urlparse(item.get("url", "")).netloc.lower()
            rating = source_ratings.get(domain, {})
            credibility = rating.get("credibility_score", 0.5)

            classification = await self._classify(claim_text, item)

            evidence.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "publisher": item.get("publisher") or domain,
                "published_at": item.get("published_at"),
                "snippet": item.get("snippet", ""),
                "evidence_type": classification["evidence_type"],
                "relevance_score": classification["relevance_score"],
                "credibility_score": credibility,
                "source_type": rating.get("source_type", "unknown"),
            })

        return {"evidence": evidence}

    async def _classify(self, claim_text: str, item: Dict) -> Dict:
        fallback = self._heuristic_classify(item)
        if fallback["evidence_type"] != "contextual":
            return fallback

        try:
            result = await self.llm.generate_json(
                prompt=f"Claim: {claim_text}\n\nResult title: {item.get('title', '')}\n"
                       f"Result snippet: {item.get('snippet', '')}",
                system_prompt=SYSTEM_PROMPT,
            )
            if isinstance(result, dict) and result.get("evidence_type") in (
                "supporting", "contradicting", "neutral", "contextual"
            ):
                result.setdefault("relevance_score", 0.5)
                return result
        except Exception as exc:
            logger.warning("Evidence LLM classification failed; using heuristic fallback: %s", exc)

        return fallback

    @staticmethod
    def _heuristic_classify(item: Dict) -> Dict:
        # Heuristic fallback
        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if any(h in text for h in CONTRADICTION_HINTS):
            return {"evidence_type": "contradicting", "relevance_score": 0.6}
        if any(h in text for h in SUPPORT_HINTS):
            return {"evidence_type": "supporting", "relevance_score": 0.6}
        return {"evidence_type": "contextual", "relevance_score": 0.4}
