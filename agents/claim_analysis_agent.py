"""
Claim Analysis Agent (section 17).

Breaks each extracted claim into subject/predicate/object plus contextual
entities, and generates the family of search queries the Web Research
Agent will run — including deliberately adversarial queries so the
pipeline searches for disconfirming evidence, not just confirming evidence.
"""
from __future__ import annotations

from typing import Dict, List

from agents.base import BaseAgent
from services.llm_service import LLMProvider

SYSTEM_PROMPT = """You are the Claim Analysis Agent. Given one factual claim, identify its
subject, predicate, object, date, location, and any named entities/organizations/events.
Then generate a list of 5-8 search queries that would help verify OR refute the claim,
including at least two adversarial queries (e.g. "<claim> false", "<claim> debunked",
"<claim> fact check"). Respond ONLY with JSON:
{"subject": "", "predicate": "", "object": "", "date": "", "location": "",
"entities": [], "organizations": [], "events": [], "search_queries": ["..."]}
"""


class ClaimAnalysisAgent(BaseAgent):
    name = "claim_analysis"

    def __init__(self, db, llm: LLMProvider):
        super().__init__(db)
        self.llm = llm

    async def execute(self, investigation_id: str, claim_text: str, category: str = None, **kwargs) -> Dict:
        result = await self.llm.generate_json(
            prompt=f"Claim: {claim_text}\nCategory: {category or 'unspecified'}",
            system_prompt=SYSTEM_PROMPT,
        )
        if not isinstance(result, dict) or not result.get("search_queries"):
            result = self._heuristic_analysis(claim_text, category)
        return result

    @staticmethod
    def _heuristic_analysis(claim_text: str, category: str = None) -> Dict:
        queries: List[str] = [
            claim_text,
            f'"{claim_text}"',
            f"{claim_text} official source",
            f"{claim_text} Nigeria",
            f"{claim_text} government statement",
            f"{claim_text} fact check",
            f"{claim_text} false",
            f"{claim_text} debunked",
        ]
        return {
            "subject": "", "predicate": "", "object": "",
            "date": "", "location": "",
            "entities": [], "organizations": [], "events": [],
            "search_queries": queries,
        }
