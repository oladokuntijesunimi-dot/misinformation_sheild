"""Admin routes (sections 12, 33, 41)."""
from __future__ import annotations

from collections import Counter

from flask import Blueprint, jsonify

from services.supabase_service import get_supabase_service
from utils.auth import require_admin

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
db = get_supabase_service()


@bp.get("/statistics")
@require_admin(db)
def statistics():
    base = db.get_platform_statistics()

    # Extra breakdowns for the admin dashboard/analytics charts (section 34).
    # For the in-memory dev service we can inspect state directly; a real
    # deployment would issue grouped Supabase queries here instead.
    verdict_counts = Counter()
    category_counts = Counter()
    if hasattr(db, "claims"):
        for claim in db.claims.values():
            if claim.get("verdict"):
                verdict_counts[claim["verdict"]] += 1
            if claim.get("category"):
                category_counts[claim["category"]] += 1

    return jsonify({
        **base,
        "verdict_distribution": dict(verdict_counts),
        "category_distribution": dict(category_counts),
    })
