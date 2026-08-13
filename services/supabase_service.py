"""
Supabase service (section 36 of the spec).

Every database read/write in the backend goes through this class rather
than being scattered across agents and routes. In production this wraps
the official `supabase-py` client using the service role key (server-side
only — never sent to the frontend). When no Supabase project is
configured, an in-memory fallback keeps the app runnable for local
development, demos, and the test suite.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import config

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class SupabaseService:
    """Interface every route/agent codes against."""

    # investigations
    def create_investigation(self, data: Dict) -> Dict: raise NotImplementedError
    def update_investigation(self, investigation_id: str, data: Dict) -> Dict: raise NotImplementedError
    def get_investigation(self, investigation_id: str) -> Optional[Dict]: raise NotImplementedError
    def list_investigations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]: raise NotImplementedError
    def delete_investigation(self, investigation_id: str) -> None: raise NotImplementedError

    # claims
    def create_claim(self, data: Dict) -> Dict: raise NotImplementedError
    def update_claim(self, claim_id: str, data: Dict) -> Dict: raise NotImplementedError
    def get_claim(self, claim_id: str) -> Optional[Dict]: raise NotImplementedError
    def list_claims_for_investigation(self, investigation_id: str) -> List[Dict]: raise NotImplementedError

    # evidence
    def create_evidence(self, data: Dict) -> Dict: raise NotImplementedError
    def list_evidence_for_claim(self, claim_id: str) -> List[Dict]: raise NotImplementedError

    # sources
    def get_source(self, domain: str) -> Optional[Dict]: raise NotImplementedError
    def upsert_source(self, data: Dict) -> Dict: raise NotImplementedError

    # documents
    def create_document(self, data: Dict) -> Dict: raise NotImplementedError
    def update_document(self, document_id: str, data: Dict) -> Dict: raise NotImplementedError
    def list_documents(self, user_id: Optional[str] = None) -> List[Dict]: raise NotImplementedError
    def delete_document(self, document_id: str) -> None: raise NotImplementedError
    def create_document_chunk(self, data: Dict) -> Dict: raise NotImplementedError

    # investigation_agents
    def upsert_agent_status(self, investigation_id: str, agent_name: str, **fields) -> Dict: raise NotImplementedError
    def list_agents_for_investigation(self, investigation_id: str) -> List[Dict]: raise NotImplementedError

    # saved_reports
    def create_saved_report(self, data: Dict) -> Dict: raise NotImplementedError
    def list_saved_reports(self, user_id: str) -> List[Dict]: raise NotImplementedError

    # profiles
    def get_profile(self, user_id: str) -> Optional[Dict]: raise NotImplementedError

    # admin / analytics
    def get_platform_statistics(self) -> Dict: raise NotImplementedError


class RealSupabaseService(SupabaseService):
    def __init__(self, url: str, service_role_key: str):
        from supabase import create_client  # imported lazily; optional dep in mock mode
        self.client = create_client(url, service_role_key)

    def _table(self, name: str):
        return self.client.table(name)

    def create_investigation(self, data: Dict) -> Dict:
        return self._table("investigations").insert(data).execute().data[0]

    def update_investigation(self, investigation_id: str, data: Dict) -> Dict:
        return self._table("investigations").update(data).eq("id", investigation_id).execute().data[0]

    def get_investigation(self, investigation_id: str) -> Optional[Dict]:
        rows = self._table("investigations").select("*").eq("id", investigation_id).execute().data
        return rows[0] if rows else None

    def list_investigations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        return (self._table("investigations").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).range(offset, offset + limit - 1).execute().data)

    def delete_investigation(self, investigation_id: str) -> None:
        self._table("investigations").delete().eq("id", investigation_id).execute()

    def create_claim(self, data: Dict) -> Dict:
        return self._table("claims").insert(data).execute().data[0]

    def update_claim(self, claim_id: str, data: Dict) -> Dict:
        return self._table("claims").update(data).eq("id", claim_id).execute().data[0]

    def get_claim(self, claim_id: str) -> Optional[Dict]:
        rows = self._table("claims").select("*").eq("id", claim_id).execute().data
        return rows[0] if rows else None

    def list_claims_for_investigation(self, investigation_id: str) -> List[Dict]:
        return self._table("claims").select("*").eq("investigation_id", investigation_id).execute().data

    def create_evidence(self, data: Dict) -> Dict:
        return self._table("evidence").insert(data).execute().data[0]

    def list_evidence_for_claim(self, claim_id: str) -> List[Dict]:
        return self._table("evidence").select("*").eq("claim_id", claim_id).execute().data

    def get_source(self, domain: str) -> Optional[Dict]:
        rows = self._table("sources").select("*").eq("domain", domain).execute().data
        return rows[0] if rows else None

    def upsert_source(self, data: Dict) -> Dict:
        return self._table("sources").upsert(data, on_conflict="domain").execute().data[0]

    def create_document(self, data: Dict) -> Dict:
        return self._table("documents").insert(data).execute().data[0]

    def update_document(self, document_id: str, data: Dict) -> Dict:
        return self._table("documents").update(data).eq("id", document_id).execute().data[0]

    def list_documents(self, user_id: Optional[str] = None) -> List[Dict]:
        q = self._table("documents").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        return q.order("created_at", desc=True).execute().data

    def delete_document(self, document_id: str) -> None:
        self._table("documents").delete().eq("id", document_id).execute()

    def create_document_chunk(self, data: Dict) -> Dict:
        return self._table("document_chunks").insert(data).execute().data[0]

    def upsert_agent_status(self, investigation_id: str, agent_name: str, **fields) -> Dict:
        existing = (self._table("investigation_agents").select("*")
                    .eq("investigation_id", investigation_id).eq("agent_name", agent_name).execute().data)
        payload = {"investigation_id": investigation_id, "agent_name": agent_name, **fields}
        if existing:
            return (self._table("investigation_agents").update(fields)
                     .eq("id", existing[0]["id"]).execute().data[0])
        return self._table("investigation_agents").insert(payload).execute().data[0]

    def list_agents_for_investigation(self, investigation_id: str) -> List[Dict]:
        return (self._table("investigation_agents").select("*")
                .eq("investigation_id", investigation_id).execute().data)

    def create_saved_report(self, data: Dict) -> Dict:
        return self._table("saved_reports").insert(data).execute().data[0]

    def list_saved_reports(self, user_id: str) -> List[Dict]:
        return (self._table("saved_reports").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).execute().data)

    def get_profile(self, user_id: str) -> Optional[Dict]:
        rows = self._table("profiles").select("*").eq("id", user_id).execute().data
        return rows[0] if rows else None

    def get_platform_statistics(self) -> Dict:
        investigations = self._table("investigations").select("id", count="exact").execute()
        claims = self._table("claims").select("id", count="exact").execute()
        documents = self._table("documents").select("id", count="exact").execute()
        return {
            "total_investigations": investigations.count or 0,
            "total_claims": claims.count or 0,
            "documents_indexed": documents.count or 0,
        }


class InMemorySupabaseService(SupabaseService):
    """
    Development/demo/test fallback. Mirrors the Postgres schema's shape
    closely enough that routes and agents behave identically regardless of
    which implementation is wired up.
    """

    def __init__(self):
        self.investigations: Dict[str, Dict] = {}
        self.claims: Dict[str, Dict] = {}
        self.evidence: Dict[str, Dict] = {}
        self.sources: Dict[str, Dict] = {}
        self.documents: Dict[str, Dict] = {}
        self.document_chunks: Dict[str, Dict] = {}
        self.investigation_agents: Dict[str, Dict] = {}
        self.saved_reports: Dict[str, Dict] = {}
        self.profiles: Dict[str, Dict] = {
            "demo-user": {
                "id": "demo-user", "full_name": "Demo User", "role": "user",
                "created_at": _now(), "updated_at": _now(),
            }
        }

    # investigations ----------------------------------------------------------
    def create_investigation(self, data: Dict) -> Dict:
        row = {"id": _new_id(), "created_at": _now(), "completed_at": None,
               "progress": 0, "status": "queued", **data}
        self.investigations[row["id"]] = row
        return row

    def update_investigation(self, investigation_id: str, data: Dict) -> Dict:
        row = self.investigations[investigation_id]
        row.update(data)
        return row

    def get_investigation(self, investigation_id: str) -> Optional[Dict]:
        return self.investigations.get(investigation_id)

    def list_investigations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        rows = [r for r in self.investigations.values() if r.get("user_id") == user_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset:offset + limit]

    def delete_investigation(self, investigation_id: str) -> None:
        self.investigations.pop(investigation_id, None)
        for cid in [c["id"] for c in self.claims.values() if c["investigation_id"] == investigation_id]:
            self.claims.pop(cid, None)
            for eid in [e["id"] for e in self.evidence.values() if e["claim_id"] == cid]:
                self.evidence.pop(eid, None)

    # claims -----------------------------------------------------------------
    def create_claim(self, data: Dict) -> Dict:
        row = {"id": _new_id(), "created_at": _now(), **data}
        self.claims[row["id"]] = row
        return row

    def update_claim(self, claim_id: str, data: Dict) -> Dict:
        row = self.claims[claim_id]
        row.update(data)
        return row

    def get_claim(self, claim_id: str) -> Optional[Dict]:
        return self.claims.get(claim_id)

    def list_claims_for_investigation(self, investigation_id: str) -> List[Dict]:
        return [c for c in self.claims.values() if c["investigation_id"] == investigation_id]

    # evidence ----------------------------------------------------------------
    def create_evidence(self, data: Dict) -> Dict:
        row = {"id": _new_id(), "created_at": _now(), **data}
        self.evidence[row["id"]] = row
        return row

    def list_evidence_for_claim(self, claim_id: str) -> List[Dict]:
        return [e for e in self.evidence.values() if e["claim_id"] == claim_id]

    # sources -------------------------------------------------------------------
    def get_source(self, domain: str) -> Optional[Dict]:
        return self.sources.get(domain)

    def upsert_source(self, data: Dict) -> Dict:
        domain = data["domain"]
        row = {**self.sources.get(domain, {"id": _new_id(), "created_at": _now()}), **data}
        self.sources[domain] = row
        return row

    # documents -------------------------------------------------------------------
    def create_document(self, data: Dict) -> Dict:
        row = {"id": _new_id(), "created_at": _now(), "updated_at": _now(), **data}
        self.documents[row["id"]] = row
        return row

    def update_document(self, document_id: str, data: Dict) -> Dict:
        row = self.documents[document_id]
        row.update(data)
        row["updated_at"] = _now()
        return row

    def list_documents(self, user_id: Optional[str] = None) -> List[Dict]:
        rows = list(self.documents.values())
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows

    def delete_document(self, document_id: str) -> None:
        self.documents.pop(document_id, None)
        for cid in [c["id"] for c in self.document_chunks.values() if c["document_id"] == document_id]:
            self.document_chunks.pop(cid, None)

    def create_document_chunk(self, data: Dict) -> Dict:
        row = {"id": _new_id(), "created_at": _now(), **data}
        self.document_chunks[row["id"]] = row
        return row

    # investigation_agents ----------------------------------------------------
    def upsert_agent_status(self, investigation_id: str, agent_name: str, **fields) -> Dict:
        key = f"{investigation_id}:{agent_name}"
        row = self.investigation_agents.get(key, {
            "id": _new_id(), "investigation_id": investigation_id,
            "agent_name": agent_name, "status": "pending",
            "output": None, "error_message": None,
            "started_at": None, "completed_at": None,
        })
        row.update(fields)
        self.investigation_agents[key] = row
        return row

    def list_agents_for_investigation(self, investigation_id: str) -> List[Dict]:
        return [a for a in self.investigation_agents.values() if a["investigation_id"] == investigation_id]

    # saved_reports -------------------------------------------------------------
    def create_saved_report(self, data: Dict) -> Dict:
        row = {"id": _new_id(), "created_at": _now(), **data}
        self.saved_reports[row["id"]] = row
        return row

    def list_saved_reports(self, user_id: str) -> List[Dict]:
        return [r for r in self.saved_reports.values() if r["user_id"] == user_id]

    # profiles --------------------------------------------------------------------
    def get_profile(self, user_id: str) -> Optional[Dict]:
        return self.profiles.get(user_id)

    # admin / analytics ------------------------------------------------------------
    def get_platform_statistics(self) -> Dict:
        return {
            "total_investigations": len(self.investigations),
            "total_claims": len(self.claims),
            "documents_indexed": sum(1 for d in self.documents.values() if d.get("indexed")),
        }


_singleton: Optional[SupabaseService] = None


def get_supabase_service() -> SupabaseService:
    global _singleton
    if _singleton is not None:
        return _singleton
    if config.using_real_supabase:
        try:
            _singleton = RealSupabaseService(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
            return _singleton
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to initialize real Supabase client, falling back to in-memory: %s", exc)
    logger.info("Supabase service running in in-memory mode (no SUPABASE credentials configured)")
    _singleton = InMemorySupabaseService()
    return _singleton
