"""
Web search provider abstraction (section 18 / 40 of the spec).

Real implementations should call an external search API (e.g. a news/search
API of your choice — Tavily, Serper, Bing, NewsAPI, etc). This module only
needs the environment variables SEARCH_PROVIDER and SEARCH_API_KEY to be set;
no code elsewhere in the app needs to change to switch providers.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from config import config

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    publisher: Optional[str] = None
    published_at: Optional[str] = None


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, limit: int = 8) -> List[SearchResult]:
        raise NotImplementedError


class GenericHTTPSearchProvider(SearchProvider):
    """
    A thin adapter for search APIs that accept {query} and return a JSON
    list of results. Configure SEARCH_PROVIDER's base URL / response shape
    here for your chosen vendor before flipping SEARCH_PROVIDER away from
    'mock' in production.
    """

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    async def search(self, query: str, limit: int = 8) -> List[SearchResult]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"q": query, "limit": limit}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(self.base_url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", [])[:limit]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", item.get("description", "")),
                publisher=item.get("source"),
                published_at=item.get("published_at"),
            ))
        return results


class TavilySearchProvider(SearchProvider):
    """
    Tavily (tavily.com) — a search API built specifically for LLM/RAG
    evidence grounding, which is exactly this app's use case. Has a usable
    free tier (1,000 searches/month at time of writing; verify current
    limits on their pricing page since these change).
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"

    async def search(self, query: str, limit: int = 8) -> List[SearchResult]:
        import httpx

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self.base_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", [])[:limit]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                publisher=None,  # WebResearchAgent/SourceCredibilityAgent derive this from the URL's domain
                published_at=item.get("published_date"),
            ))
        return results


class MockSearchProvider(SearchProvider):
    """
    Returns no fabricated evidence. When no real search provider is
    configured, agents must be able to tell the difference between "we
    searched and found nothing" and "evidence exists" — this provider
    always returns an empty result set so the Verification Agent correctly
    falls back to 'unverifiable' rather than ever inventing a source.
    """

    async def search(self, query: str, limit: int = 8) -> List[SearchResult]:
        logger.info("Mock search provider called for query=%r (no SEARCH_API_KEY configured)", query)
        return []


def get_search_provider() -> SearchProvider:
    if config.SEARCH_PROVIDER == "tavily" and config.SEARCH_API_KEY:
        logger.info("Search provider: Tavily")
        return TavilySearchProvider(api_key=config.SEARCH_API_KEY)

    if config.using_real_search:
        # Base URL left generic — set it to your chosen vendor's endpoint.
        base_url = config.__dict__.get("SEARCH_BASE_URL") or "https://api.search-provider.example/v1/search"
        return GenericHTTPSearchProvider(api_key=config.SEARCH_API_KEY, base_url=base_url)

    logger.info("Search provider running in mock mode (no SEARCH_API_KEY configured)")
    return MockSearchProvider()
