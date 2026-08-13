"""
Embedding provider abstraction (section 39 of the spec).

Swappable without touching the RAG pipeline: implement a new subclass and
point EMBEDDING_PROVIDER / EMBEDDING_API_KEY at it.
"""
from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod
from typing import List

from config import config

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        raise NotImplementedError

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """Works with any OpenAI-compatible /embeddings endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1/embeddings"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def embed(self, text: str) -> List[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "input": texts}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return [row["embedding"] for row in data["data"]]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Talks to a local Ollama instance's native batch embeddings endpoint
    (`/api/embed`). Ollama requires no API key and no signup — install it,
    run `ollama pull nomic-embed-text` (or any other embedding model), and
    make sure `ollama serve` is running. Free, local, no rate limits.
    """

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def embed(self, text: str) -> List[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        import httpx

        payload = {"model": self.model, "input": texts}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base_url}/api/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic, hash-based pseudo-embedding. Same input always yields the
    same vector, and semantically similar strings (sharing tokens) end up
    closer in space than unrelated ones — good enough to exercise the
    Pinecone service and RAG agent in tests without any network calls.
    """

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    async def embed(self, text: str) -> List[float]:
        return self._vector_for(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._vector_for(t) for t in texts]

    def _vector_for(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        tokens = text.lower().split()
        if not tokens:
            tokens = [""]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def get_embedding_provider() -> EmbeddingProvider:
    if config.EMBEDDING_PROVIDER == "ollama":
        base_url = config.EMBEDDING_BASE_URL or "http://localhost:11434"
        model = config.EMBEDDING_MODEL or "nomic-embed-text"
        logger.info("Embedding provider: Ollama (%s, model=%s)", base_url, model)
        return OllamaEmbeddingProvider(model=model, base_url=base_url)

    if config.using_real_embeddings:
        return OpenAICompatibleEmbeddingProvider(
            api_key=config.EMBEDDING_API_KEY,
            model=config.EMBEDDING_MODEL,
            base_url=config.EMBEDDING_BASE_URL or "https://api.openai.com/v1/embeddings",
        )

    logger.info("Embedding provider running in mock mode (no EMBEDDING_API_KEY configured)")
    return MockEmbeddingProvider()
