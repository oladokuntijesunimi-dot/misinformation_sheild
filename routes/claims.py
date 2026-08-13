"""Claim-level routes (section 41)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from services.supabase_service import get_supabase_service
from utils.auth import require_auth

bp = Blueprint("claims", __name__, url_prefix="/api/claims")
db = get_supabase_service()


def _owns_claim(claim: dict, user_id: str) -> bool:
    if not claim:
        return False
    investigation = db.get_investigation(claim["investigation_id"])
    return bool(investigation) and investigation["user_id"] == user_id


@bp.get("/<claim_id>")
@require_auth
def get_claim(claim_id: str):
    claim = db.get_claim(claim_id)
    if not _owns_claim(claim, g.user_id):
        return jsonify({"error": "Not found"}), 404
    evidence = db.list_evidence_for_claim(claim_id)
    return jsonify({**claim, "evidence": evidence})


@bp.get("/<claim_id>/evidence")
@require_auth
def get_claim_evidence(claim_id: str):
    claim = db.get_claim(claim_id)
    if not _owns_claim(claim, g.user_id):
        return jsonify({"error": "Not found"}), 404
    evidence = db.list_evidence_for_claim(claim_id)
    grouped = {"supporting": [], "contradicting": [], "neutral": [], "contextual": []}
    for e in evidence:
        grouped.setdefault(e["evidence_type"], []).append(e)
    return jsonify(grouped)
