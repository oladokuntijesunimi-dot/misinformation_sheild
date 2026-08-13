"""
Auth route (section 8).

Password hashing, sessions, tokens, OAuth, email verification, and
password reset are all handled by Supabase Auth on the frontend via the
Supabase JS client — this backend never touches passwords. This route
just exposes the caller's profile, keyed off the verified JWT.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from services.supabase_service import get_supabase_service
from utils.auth import require_auth

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
db = get_supabase_service()


@bp.get("/me")
@require_auth
def me():
    profile = db.get_profile(g.user_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)
