"""
Verification Agent (sections 23-25).

Takes ALL gathered evidence — supporting, contradicting, neutral, RAG,
source credibility — and produces the final verdict, veracity score, and
confidence score. This is the only agent allowed to render a verdict, and
it must never invent evidence: if evidence is insufficient the verdict is
"unverifiable" (section 47, Anti-Hallucination System).
"""
from __future__ import annotations

from typing import Dict, List

from agents.base import BaseAgent
from services.llm_service import LLMProvider

VERDICT_BANDS = [
    (90, 100, "verified"),
    (75, 89, "mostly_true"),
    (50, 74, "partially_true"),
    (30, 49, "misleading"),
    (10, 29, "mostly_false"),
    (0, 9, "false"),
]

SYSTEM_PROMPT = """You are the Verification Agent, the final decision-maker in a fact-checking
pipeline. You are given a claim plus supporting evidence, contradicting evidence, neutral
evidence, and RAG knowledge-base evidence, each with source credibility scores.

Rules:
- Never invent sources, quotations, or facts not present in the evidence provided.
- Weigh evidence by both relevance_score and credibility_score.
- If evidence is thin, conflicting without resolution, or mostly low-credibility, prefer
  "unverifiable" over guessing.
- Output veracity_score 0-100 representing how strongly evidence supports the claim
  (0 = strongly contradicted, 100 = strongly confirmed).
- Output confidence 0-100 representing how confident you are in this assessment GIVEN
  the amount and quality of evidence available (thin evidence -> low confidence, even if
  what little evidence exists points clearly one way or the other).
- summary: 2-4 sentences, evidence-based, plain language.
- key_findings: array of short bullet strings, each traceable to evidence.
- limitations: array of short bullet strings describing gaps or uncertainty.

Respond ONLY with JSON:
{"veracity_score": 0, "confidence": 0, "summary": "", "key_findings": [], "limitations": []}
"""


class VerificationAgent(BaseAgent):
    name = "verification"

    def __init__(self, db, llm: LLMProvider):
        super().__init__(db)
        self.llm = llm

    async def execute(self, investigation_id: str, claim_text: str,
                       supporting: List[Dict], contradicting: List[Dict],
                       neutral: List[Dict], rag_evidence: List[Dict], **kwargs) -> Dict:

        total_evidence = len(supporting) + len(contradicting) + len(neutral) + len(rag_evidence)

        if total_evidence == 0:
            return self._unverifiable(
                "No supporting, contradicting, or contextual evidence could be found for "
                "this claim with the currently configured search and knowledge-base sources."
            )

        prompt = self._build_prompt(claim_text, supporting, contradicting, neutral, rag_evidence)
        result = await self.llm.generate_json(prompt=prompt, system_prompt=SYSTEM_PROMPT)

        if not isinstance(result, dict) or "veracity_score" not in result:
            result = self._heuristic_verdict(supporting, contradicting, neutral, total_evidence)

        veracity_score = max(0, min(100, int(result.get("veracity_score", 50))))
        confidence = max(0, min(100, float(result.get("confidence", 40))))
        verdict = self._band_for_score(veracity_score)

        # Low total evidence volume caps confidence regardless of what the LLM said,
        # per section 47's "clearly communicate uncertainty" requirement.
        if total_evidence < 3:
            confidence = min(confidence, 45)
            if total_evidence < 2:
                return self._unverifiable(
                    "Only minimal evidence was found; this is not enough to reach a "
                    "reliable verdict."
                )

        return {
            "verdict": verdict,
            "veracity_score": veracity_score,
            "confidence": round(confidence, 2),
            "summary": result.get("summary", ""),
            "key_findings": result.get("key_findings", []),
            "limitations": result.get("limitations", []),
        }

    @staticmethod
    def _band_for_score(score: int) -> str:
        for low, high, label in VERDICT_BANDS:
            if low <= score <= high:
                return label
        return "unverifiable"

    @staticmethod
    def _unverifiable(reason: str) -> Dict:
        return {
            "verdict": "unverifiable",
            "veracity_score": 50,
            "confidence": 15.0,
            "summary": reason,
            "key_findings": [],
            "limitations": [reason],
        }

    @staticmethod
    def _heuristic_verdict(supporting: List[Dict], contradicting: List[Dict],
                            neutral: List[Dict], total: int) -> Dict:
        def weight(items):
            return sum(i.get("relevance_score", 0.5) * i.get("credibility_score", 0.5) for i in items)

        sup_w, con_w = weight(supporting), weight(contradicting)
        denom = sup_w + con_w
        if denom == 0:
            score = 50
        else:
            score = round((sup_w / denom) * 100)

        confidence = min(90.0, 20 + total * 8)

        return {
            "veracity_score": score,
            "confidence": confidence,
            "summary": (
                f"Based on {len(supporting)} supporting, {len(contradicting)} contradicting, "
                f"and {len(neutral)} neutral evidence items found."
            ),
            "key_findings": [],
            "limitations": ["Generated via heuristic scoring (no LLM configured)."],
        }

    @staticmethod
    def _build_prompt(claim_text: str, supporting, contradicting, neutral, rag_evidence) -> str:
        def fmt(items, label):
            lines = [f"{label} ({len(items)}):"]
            for e in items[:6]:
                lines.append(
                    f"- {e.get('title', '')} [{e.get('publisher', '')}] "
                    f"relevance={e.get('relevance_score')} credibility={e.get('credibility_score')}: "
                    f"{e.get('snippet', '')[:200]}"
                )
            return "\n".join(lines)

        return "\n\n".join([
            f"Claim: {claim_text}",
            fmt(supporting, "SUPPORTING EVIDENCE"),
            fmt(contradicting, "CONTRADICTING EVIDENCE"),
            fmt(neutral, "NEUTRAL/CONTEXTUAL EVIDENCE"),
            fmt(rag_evidence, "KNOWLEDGE BASE EVIDENCE"),
        ])
