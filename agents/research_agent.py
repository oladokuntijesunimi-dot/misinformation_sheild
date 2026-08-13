"""
Web Research Agent (section 18).

Runs the query set produced by the Claim Analysis Agent against the
configured SearchProvider, deduplicates by URL, and ranks results with a
preference for government, official-institution, reputable-news,
academic, and fact-checking sources (section 48: Nigerian source
priority feeds into this ranking too).
"""
from __future__ import annotations

from typing import Dict, List
from urllib.parse import urlparse

from agents.base import BaseAgent
from services.search_service import SearchProvider, SearchResult

PRIORITY_DOMAIN_HINTS = [
    (".gov.ng", 1.0), (".gov", 0.95), ("who.int", 0.95),
    ("dubawa.org", 0.9), ("africacheck.org", 0.9),
    ("reuters.com", 0.88), ("apnews.com", 0.88), ("bbc.com", 0.85),
    ("premiumtimesng.com", 0.82), ("channelstv.com", 0.78),
    (".edu", 0.75), (".ac.ng", 0.75),
]


class WebResearchAgent(BaseAgent):
    name = "web_research"

    def __init__(self, db, search: SearchProvider):
        super().__init__(db)
        self.search = search

    async def execute(self, investigation_id: str, search_queries: List[str], **kwargs) -> Dict:
        seen_urls = set()
        all_results: List[SearchResult] = []

        for query in search_queries[:4]:  # cap fan-out per claim
            results = await self.search.search(query, limit=4)
            for r in results:
                if not r.url or r.url in seen_urls:
                    continue
                seen_urls.add(r.url)
                all_results.append(r)

        ranked = sorted(all_results, key=self._priority_score, reverse=True)[:10]

        return {
            "results": [
                {
                    "title": r.title, "url": r.url, "snippet": r.snippet,
                    "publisher": r.publisher, "published_at": r.published_at,
                    "priority_score": self._priority_score(r),
                }
                for r in ranked
            ],
            "queries_run": len(search_queries[:4]),
            "unique_results": len(ranked),
        }

    @staticmethod
    def _priority_score(result: SearchResult) -> float:
        domain = urlparse(result.url).netloc.lower()
        for hint, score in PRIORITY_DOMAIN_HINTS:
            if hint in domain:
                return score
        return 0.5
