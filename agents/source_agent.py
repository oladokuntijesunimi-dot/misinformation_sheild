"""
Source Credibility Agent (section 20).

Scores each distinct publisher/domain that surfaced evidence. Reuses and
refreshes the `sources` table so ratings compound across investigations.
Crucially: a low-credibility source lowers weight, it never single-handedly
flips a verdict to false — that judgement is reserved for the Verification
Agent weighing all evidence together.
"""
from __future__ import annotations

from typing import Dict, List
from urllib.parse import urlparse

from agents.base import BaseAgent
from services.llm_service import LLMProvider
from services.supabase_service import SupabaseService

GOV_HINTS = (".gov.ng", ".gov", "cbn.gov.ng", "statehouse.gov.ng")
FACT_CHECK_HINTS = ("dubawa.org", "africacheck.org", "politifact.com", "snopes.com")
INSTITUTIONAL_HINTS = ("who.int", "un.org", "worldbank.org")


class SourceCredibilityAgent(BaseAgent):
    name = "source_credibility"

    def __init__(self, db: SupabaseService, llm: LLMProvider):
        super().__init__(db)
        self.llm = llm

    async def execute(self, investigation_id: str, evidence_urls: List[str], **kwargs) -> Dict:
        domains = sorted({urlparse(u).netloc.lower() for u in evidence_urls if u})
        ratings: Dict[str, Dict] = {}

        for domain in domains:
            existing = self.db.get_source(domain)
            if existing and existing.get("credibility_score") is not None:
                ratings[domain] = existing
                continue

            score, source_type, reason = self._heuristic_rating(domain)
            record = self.db.upsert_source({
                "domain": domain,
                "name": domain,
                "source_type": source_type,
                "credibility_score": score,
                "credibility_reason": reason,
                "last_evaluated": kwargs.get("_now"),
            })
            ratings[domain] = record

        return {"ratings": ratings}

    @staticmethod
    def _heuristic_rating(domain: str):
        if any(hint in domain for hint in GOV_HINTS):
            return 0.93, "government", "Official government domain."
        if any(hint in domain for hint in FACT_CHECK_HINTS):
            return 0.88, "fact_checking", "Established fact-checking organization."
        if any(hint in domain for hint in INSTITUTIONAL_HINTS):
            return 0.9, "institutional", "Recognized international institution."
        if domain.endswith(".edu") or ".ac." in domain:
            return 0.8, "academic", "Academic institution domain."
        if any(k in domain for k in ("reuters", "apnews", "bbc")):
            return 0.88, "news", "International wire service or public broadcaster."
        # unknown domain — moderate, not-yet-corroborated default
        return 0.55, "unknown", "Domain not yet independently evaluated; treat evidence with caution."
