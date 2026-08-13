"""
Contradiction Agent (section 22).

The pipeline's anti-confirmation-bias safeguard. Independently issues
adversarial queries ("<claim> false", "<claim> debunked", "<claim>
fact check", etc.) through the same Web Research Agent so contradicting
evidence is actively hunted for rather than only whatever the Evidence
Agent happened to classify as contradicting from the primary search pass.
"""
from __future__ import annotations

from typing import Dict, List

from agents.base import BaseAgent
from agents.research_agent import WebResearchAgent

ADVERSARIAL_TEMPLATES = [
    "{claim} false",
    "{claim} fact check",
    "{claim} debunked",
]


class ContradictionAgent(BaseAgent):
    name = "contradiction"

    def __init__(self, db, research_agent: WebResearchAgent):
        super().__init__(db)
        self.research_agent = research_agent

    async def execute(self, investigation_id: str, claim_text: str, **kwargs) -> Dict:
        adversarial_queries = [t.format(claim=claim_text) for t in ADVERSARIAL_TEMPLATES]
        research = await self.research_agent.execute(
            investigation_id=investigation_id, search_queries=adversarial_queries,
        )
        return {
            "adversarial_queries": adversarial_queries,
            "results": research["results"],
        }
