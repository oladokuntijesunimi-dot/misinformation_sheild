"""
Report Generator Agent (final step of the pipeline, section 49).

Assembles the persisted claim + evidence + verdict into the structured
report shape the frontend result page and PDF export both consume. Adds
no new judgement — pure presentation-layer aggregation.
"""
from __future__ import annotations

from typing import Dict, List

from agents.base import BaseAgent

DISCLAIMER = (
    "This is an AI-assisted assessment based on available evidence. "
    "It is not an absolute determination of truth."
)


class ReportGeneratorAgent(BaseAgent):
    name = "report_generation"

    async def execute(self, investigation_id: str, claim: Dict, evidence: List[Dict], **kwargs) -> Dict:
        supporting = [e for e in evidence if e["evidence_type"] == "supporting"]
        contradicting = [e for e in evidence if e["evidence_type"] == "contradicting"]
        neutral = [e for e in evidence if e["evidence_type"] == "neutral"]
        contextual = [e for e in evidence if e["evidence_type"] == "contextual"]

        return {
            "claim_text": claim.get("claim_text"),
            "verdict": claim.get("verdict"),
            "veracity_score": claim.get("veracity_score"),
            "confidence_score": claim.get("confidence_score"),
            "summary": claim.get("summary"),
            "key_findings": claim.get("key_findings", []),
            "limitations": claim.get("limitations", []),
            "evidence": {
                "supporting": supporting,
                "contradicting": contradicting,
                "neutral": neutral,
                "contextual": contextual,
            },
            "source_count": len({e["url"] for e in evidence if e.get("url")}),
            "disclaimer": DISCLAIMER,
        }
