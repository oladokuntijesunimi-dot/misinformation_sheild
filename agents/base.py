"""
Shared base class for every pipeline agent.

Wraps each agent's run() call with investigation_agents status tracking so
the frontend's investigation-progress view (section 28) reflects real
pipeline state rather than a fake timer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.supabase_service import SupabaseService

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseAgent:
    name: str = "base_agent"

    def __init__(self, db: SupabaseService):
        self.db = db

    async def run(self, investigation_id: str, **kwargs) -> Any:
        self.db.upsert_agent_status(
            investigation_id, self.name, status="running",
            started_at=_now(), error_message=None,
        )
        try:
            result = await self.execute(investigation_id=investigation_id, **kwargs)
            self.db.upsert_agent_status(
                investigation_id, self.name, status="completed",
                completed_at=_now(), output=self._serialize(result),
            )
            return result
        except Exception as exc:
            logger.exception("Agent %s failed for investigation %s", self.name, investigation_id)
            self.db.upsert_agent_status(
                investigation_id, self.name, status="failed",
                completed_at=_now(), error_message=str(exc),
            )
            raise

    async def execute(self, investigation_id: str, **kwargs) -> Any:
        raise NotImplementedError

    @staticmethod
    def _serialize(result: Any) -> Any:
        """Best-effort JSON-safe summary of an agent's output for storage."""
        if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
            return result
        if hasattr(result, "__dict__"):
            return {k: v for k, v in result.__dict__.items()}
        return str(result)
