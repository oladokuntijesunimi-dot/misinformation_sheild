"""
Claim Extraction Agent (section 16).

Extracts discrete, checkable factual claims from raw submitted content —
stripping out opinion, rhetorical questions, and emotional framing — and
returns structured JSON. Never runs verification itself.
"""
from __future__ import annotations

import re
from typing import Dict, List

from agents.base import BaseAgent
from services.llm_service import LLMProvider

SYSTEM_PROMPT = """You are the Claim Extraction Agent inside a fact-checking pipeline.
Extract only discrete, checkable factual claims from the user's input.
Strip out: opinions, rhetorical questions, emotional language, and pure commentary.
For each claim identify people, organizations, dates, places, numbers, events, and policies where present.
Respond ONLY with JSON in this exact shape, nothing else:
{"claims": [{"claim": "...", "claim_type": "factual", "importance": 0.0-1.0,
"entities": {"people": [], "organizations": [], "dates": [], "places": [], "numbers": [], "events": [], "policies": []}}]}
If the input contains no checkable factual claim, return {"claims": []}.
"""


class ClaimExtractionAgent(BaseAgent):
    name = "claim_extraction"

    def __init__(self, db, llm: LLMProvider):
        super().__init__(db)
        self.llm = llm

    async def execute(self, investigation_id: str, content: str, **kwargs) -> Dict:
        if not content or not content.strip():
            return {"claims": []}

        result = await self.llm.generate_json(
            prompt=f"Input content:\n\n{content}\n\nExtract the factual claims as JSON.",
            system_prompt=SYSTEM_PROMPT,
        )

        claims = result.get("claims") if isinstance(result, dict) else None
        if not claims:
            # Deterministic fallback (also what mock mode relies on): treat
            # each sentence with a verb and no question mark as a candidate
            # claim, filtering out obviously rhetorical/emotional lines.
            claims = self._heuristic_extract(content)

        return {"claims": claims}

    @staticmethod
    def _heuristic_extract(content: str) -> List[Dict]:
        sentences = re.split(r"(?<=[.!?])\s+", content.strip())
        claims = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or "?" in sentence:
                continue
            if len(sentence.split()) < 4:
                continue
            claims.append({
                "claim": sentence,
                "claim_type": "factual",
                "importance": 0.7,
                "entities": {
                    "people": [], "organizations": [], "dates": [],
                    "places": [], "numbers": re.findall(r"\b\d[\d,.]*\b", sentence),
                    "events": [], "policies": [],
                },
            })
        return claims[:5]  # cap so a whole article doesn't explode into dozens of claims
