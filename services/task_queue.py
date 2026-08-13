"""
Task queue abstraction.

The investigation pipeline (multiple LLM calls + multiple search rounds
per claim) routinely takes longer than a typical HTTP request timeout.
This module gets it out of the request/response cycle:

- `RQTaskQueue` — real production path. Enqueues a job onto Redis via RQ;
  a separate `python worker.py` process picks it up and runs it. Survives
  API process restarts, scales across multiple API instances, and is what
  `render.yaml`'s optional worker service runs.
- `InProcessTaskQueue` — zero-dependency fallback for local development
  and small demos. Runs the job on a background thread within the same
  process, so the HTTP request still returns immediately, but the job is
  lost if the process restarts and this does not coordinate across
  multiple instances.

Either way, the API request returns as soon as the investigation row is
created with status="queued" — the frontend's existing polling loop
(`investigation/[id]/page.tsx`) picks up progress from there. No frontend
changes were needed for this.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from abc import ABC, abstractmethod

from config import config

logger = logging.getLogger(__name__)


class TaskQueue(ABC):
    @abstractmethod
    def enqueue_investigation(self, investigation_id: str) -> None:
        raise NotImplementedError


def _run_pipeline_sync(investigation_id: str) -> None:
    """
    Shared job body for both queue implementations, and for the RQ worker
    process (backend/worker.py imports this same function so the enqueued
    job reference is stable and picklable).
    """
    from agents.orchestrator import InvestigationOrchestrator
    from services.embedding_service import get_embedding_provider
    from services.llm_service import get_llm_provider
    from services.pinecone_service import get_pinecone_service
    from services.search_service import get_search_provider
    from services.supabase_service import get_supabase_service

    db = get_supabase_service()
    orchestrator = InvestigationOrchestrator(
        db=db,
        llm=get_llm_provider(),
        search=get_search_provider(),
        embeddings=get_embedding_provider(),
        pinecone=get_pinecone_service(),
    )
    try:
        asyncio.run(orchestrator.run(investigation_id))
    except Exception:
        logger.exception("Investigation pipeline failed for %s", investigation_id)


class InProcessTaskQueue(TaskQueue):
    def enqueue_investigation(self, investigation_id: str) -> None:
        thread = threading.Thread(
            target=_run_pipeline_sync, args=(investigation_id,), daemon=True,
        )
        thread.start()
        logger.info("Investigation %s queued on in-process background thread", investigation_id)


class RQTaskQueue(TaskQueue):
    def __init__(self, redis_url: str):
        import redis as redis_module
        from rq import Queue

        self._redis = redis_module.from_url(redis_url)
        self._queue = Queue("investigations", connection=self._redis)

    def enqueue_investigation(self, investigation_id: str) -> None:
        # Imported by string path (not the function object) so the worker
        # process — which imports this module fresh — resolves the same
        # function without needing to pickle a closure.
        job = self._queue.enqueue(
            "services.task_queue._run_pipeline_sync",
            investigation_id,
            job_timeout=600,  # 10 minutes; a multi-claim investigation can take a while
        )
        logger.info("Investigation %s enqueued on RQ (job id %s)", investigation_id, job.id)


_singleton: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _singleton
    if _singleton is not None:
        return _singleton

    if config.using_real_task_queue:
        try:
            _singleton = RQTaskQueue(redis_url=config.REDIS_URL)
            logger.info("Task queue: RQ + Redis (%s)", config.REDIS_URL)
            return _singleton
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to connect to Redis at %s, falling back to in-process queue: %s",
                         config.REDIS_URL, exc)

    logger.info("Task queue running in-process (no REDIS_URL configured) — see README for the production setup")
    _singleton = InProcessTaskQueue()
    return _singleton
