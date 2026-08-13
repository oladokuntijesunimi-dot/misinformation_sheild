"""Investigation routes (sections 13, 14, 26, 30, 41)."""
from __future__ import annotations

import logging

from flask import Blueprint, g, jsonify, request

from services.supabase_service import get_supabase_service
from services.task_queue import get_task_queue
from utils.auth import require_auth
from utils.validation import ValidationError, validate_category, validate_input_type, validate_text_input, validate_url

logger = logging.getLogger(__name__)
bp = Blueprint("investigations", __name__, url_prefix="/api/investigations")

db = get_supabase_service()


@bp.post("")
@require_auth
def create_investigation():
    payload = request.get_json(silent=True) or {}
    input_type = payload.get("input_type", "text")
    content = payload.get("content", "")
    source_url = payload.get("source_url")
    category = payload.get("category")

    try:
        input_type = validate_input_type(input_type)
        category = validate_category(category)
        if input_type == "url":
            source_url = validate_url(source_url or content)
            content = validate_text_input(content or source_url)
        else:
            content = validate_text_input(content)
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    investigation = db.create_investigation({
        "user_id": g.user_id,
        "input_type": input_type,
        "original_content": content,
        "source_url": source_url,
        "category": category,
        "status": "queued",
        "progress": 0,
    })

    # Enqueue and return immediately — the pipeline (multiple LLM calls +
    # multiple search rounds per claim) runs out-of-request, either on a
    # separate RQ worker process (if REDIS_URL is set) or an in-process
    # background thread otherwise. Either way this request does not block
    # on it; the frontend polls GET /api/investigations/:id for progress.
    try:
        get_task_queue().enqueue_investigation(investigation["id"])
    except Exception:
        logger.exception("Failed to enqueue investigation %s", investigation["id"])
        db.update_investigation(investigation["id"], {
            "status": "failed", "error_message": "Failed to start the investigation pipeline.",
        })

    investigation = db.get_investigation(investigation["id"])
    return jsonify(_serialize_investigation(investigation)), 202


@bp.get("")
@require_auth
def list_investigations():
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    rows = db.list_investigations(g.user_id, limit=limit, offset=offset)
    return jsonify([_serialize_investigation(r) for r in rows])


@bp.get("/<investigation_id>")
@require_auth
def get_investigation(investigation_id: str):
    investigation = db.get_investigation(investigation_id)
    if not investigation or investigation["user_id"] != g.user_id:
        return jsonify({"error": "Not found"}), 404

    claims = db.list_claims_for_investigation(investigation_id)
    claims_with_evidence = []
    for claim in claims:
        evidence = db.list_evidence_for_claim(claim["id"])
        claims_with_evidence.append({**claim, "evidence": evidence})

    agents = db.list_agents_for_investigation(investigation_id)

    return jsonify({
        **_serialize_investigation(investigation),
        "claims": claims_with_evidence,
        "agents": agents,
    })


@bp.delete("/<investigation_id>")
@require_auth
def delete_investigation(investigation_id: str):
    investigation = db.get_investigation(investigation_id)
    if not investigation or investigation["user_id"] != g.user_id:
        return jsonify({"error": "Not found"}), 404
    db.delete_investigation(investigation_id)
    return jsonify({"deleted": True})


def _serialize_investigation(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "input_type": row["input_type"],
        "original_content": row["original_content"],
        "source_url": row.get("source_url"),
        "status": row["status"],
        "progress": row.get("progress", 0),
        "category": row.get("category"),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
        "error_message": row.get("error_message"),
    }
