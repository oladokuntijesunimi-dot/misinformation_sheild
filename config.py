"""
Central configuration for the Misinformation Shield Flask backend.

All secrets are read from environment variables and never sent to the
frontend. Loaded from the single, shared `.env` at the project root (see
`.env.example` there for the full list) — the frontend reads the same file
via next.config.mjs, so there is only one place to configure both apps.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# config.py lives at the project root now
_ROOT_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ROOT_ENV_PATH)


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- Flask -------------------------------------------------------------
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DEBUG: bool = _env_bool("FLASK_DEBUG", True)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Explicit opt-in for running without real Supabase auth. When False
    # (the default) and no real Supabase project is configured, every
    # request is rejected rather than silently treated as one shared
    # "demo-user" — deploying without either real auth or this explicit
    # acknowledgement is very likely a mistake, not an intentional choice.
    DEMO_MODE: bool = _env_bool("DEMO_MODE", False)

    # --- Supabase ------------------------------------------------------------
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # --- LLM -------------------------------------------------------------------
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")

    # --- Pinecone ------------------------------------------------------------
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX: str = os.getenv("PINECONE_INDEX", "misinformation-shield")
    PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "")

    # --- Search -----------------------------------------------------------------
    SEARCH_PROVIDER: str = os.getenv("SEARCH_PROVIDER", "mock")
    SEARCH_API_KEY: str = os.getenv("SEARCH_API_KEY", "")

    # --- Embeddings ---------------------------------------------------------------
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "mock")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "")

    # --- Uploads -------------------------------------------------------------------
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "15"))
    ALLOWED_EXTENSIONS: tuple = field(default_factory=lambda: (".pdf", ".docx", ".txt"))

    # --- Rate limiting ----------------------------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))

    # --- Background task queue -----------------------------------------------------
    # If set, investigations run via RQ + Redis in a separate worker process
    # (see `backend/worker.py`) so the API request returns immediately.
    # If unset, falls back to an in-process background thread — no Redis
    # needed, still non-blocking, but doesn't survive process restarts and
    # doesn't scale across multiple app instances. See README.
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    @property
    def using_real_llm(self) -> bool:
        return bool(self.LLM_API_KEY) and self.LLM_PROVIDER != "mock"

    @property
    def using_real_supabase(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY)

    @property
    def using_real_pinecone(self) -> bool:
        return bool(self.PINECONE_API_KEY)

    @property
    def using_real_search(self) -> bool:
        return bool(self.SEARCH_API_KEY) and self.SEARCH_PROVIDER != "mock"

    @property
    def using_real_embeddings(self) -> bool:
        # Ollama runs locally and needs no API key, unlike hosted providers.
        if self.EMBEDDING_PROVIDER == "ollama":
            return True
        return bool(self.EMBEDDING_API_KEY) and self.EMBEDDING_PROVIDER != "mock"

    @property
    def using_real_task_queue(self) -> bool:
        return bool(self.REDIS_URL)


config = Config()
