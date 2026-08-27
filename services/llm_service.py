"""
LLM provider abstraction.

`LLMProvider` is the interface every agent codes against. `GroqProvider` is
the initial concrete implementation. `MockLLMProvider` lets the whole
pipeline — and the test suite — run deterministically with zero network
calls and zero API keys, which is what section 54 of the spec requires
("Tests must not require real API calls").
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from config import config

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                        json_mode: bool = False, temperature: float = 0.2) -> str:
        """Return the raw text completion for a prompt."""
        raise NotImplementedError

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None,
                             temperature: float = 0.1) -> Any:
        """Convenience wrapper: generate then parse JSON, tolerating code fences."""
        raw = await self.generate(prompt, system_prompt=system_prompt,
                                   json_mode=True, temperature=temperature)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("LLM output was not valid JSON, returning empty structure")
            return {}


class GroqProvider(LLMProvider):
    """Calls Groq's OpenAI-compatible chat completions endpoint."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        # Allow overriding the Groq/OpenAI-compatible base URL via env var
        # (useful when the provider's route changes or for private endpoints).
        if getattr(config, "LLM_BASE_URL", ""):
            # keep any provided base URL but strip trailing slash
            self.base_url = config.LLM_BASE_URL.rstrip("/")
        else:
            self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                        json_mode: bool = False, temperature: float = 0.2) -> str:
        import httpx

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            tried = [self.base_url]
            try:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                status = getattr(exc.response, "status_code", None)
                logger.warning("LLM request to %s failed with status %s", self.base_url, status)
                # If we got a 404 from the default Groq host, try a couple of
                # reasonable alternative endpoints automatically before failing
                # (helps when provider changed their hostname/path).
                fallbacks = []
                if "api.groq.com" in self.base_url:
                    fallbacks.append(self.base_url.replace("api.groq.com", "api.groq.ai"))
                if "/openai/v1/" in self.base_url:
                    fallbacks.append(self.base_url.replace("/openai/v1/", "/v1/"))
                # Combine both transformations as a last resort
                if "api.groq.com" in self.base_url and "/openai/v1/" in self.base_url:
                    candidate = self.base_url.replace("api.groq.com", "api.groq.ai").replace("/openai/v1/", "/v1/")
                    fallbacks.append(candidate)

                for url in fallbacks:
                    if url in tried:
                        continue
                    tried.append(url)
                    logger.info("Retrying LLM request with fallback URL: %s", url)
                    resp = await client.post(url, json=payload, headers=headers)
                    try:
                        resp.raise_for_status()
                        data = resp.json()
                        # update base_url to the working endpoint for subsequent calls
                        self.base_url = url
                        return data["choices"][0]["message"]["content"]
                    except httpx.HTTPStatusError:
                        logger.warning("Fallback URL %s also failed (status=%s)", url, resp.status_code)
                        continue
                # No fallback succeeded — re-raise the original exception for upstream handling
                raise


class MockLLMProvider(LLMProvider):
    """
    Deterministic stand-in used when no LLM_API_KEY is configured, and in
    tests. It performs lightweight heuristic text processing rather than
    real reasoning — good enough to exercise the full pipeline end to end
    without ever inventing evidence.
    """

    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                        json_mode: bool = False, temperature: float = 0.2) -> str:
        # Agents call generate_json for structured steps; a plain generate()
        # call is only used for prose (e.g. the final explanation), so
        # return a short, honest placeholder that agents can safely use.
        return (
            "Evidence-based assessment generated in mock mode. Configure "
            "LLM_API_KEY to enable real model reasoning."
        )


def get_llm_provider() -> LLMProvider:
    if config.using_real_llm and config.LLM_PROVIDER == "groq":
        return GroqProvider(api_key=config.LLM_API_KEY, model=config.LLM_MODEL)
    logger.info("LLM provider running in mock mode (no LLM_API_KEY configured)")
    return MockLLMProvider()
