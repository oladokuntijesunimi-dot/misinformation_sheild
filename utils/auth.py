"""
Auth utilities (sections 8 & 45).

The frontend authenticates users via Supabase Auth and attaches the
resulting access token as `Authorization: Bearer <jwt>` on API requests.
This module validates that JWT server-side — the Flask backend never
trusts the frontend for authorization decisions.
"""
from __future__ import annotations

import functools
import logging
from typing import Optional

from flask import g, jsonify, request

from config import config

logger = logging.getLogger(__name__)

DEMO_USER_ID = "demo-user"


def _decode_supabase_jwt(token: str) -> Optional[dict]:
    """
    Decode and verify a Supabase-issued JWT using the project's JWT secret
    (derived from SUPABASE_SERVICE_ROLE_KEY in a real deployment — Supabase
    signs user JWTs with a project-specific secret available in your
    project's API settings). Returns the decoded claims, or None if invalid.
    """
    if not config.using_real_supabase:
        return None
    try:
        import jwt as pyjwt
        # In production, set SUPABASE_JWT_SECRET from your Supabase project's
        # API settings; falling back to service role key is NOT correct for
        # real deployments and is only a development convenience.
        import os
        secret = os.getenv("SUPABASE_JWT_SECRET", "")
        if not secret:
            logger.warning("SUPABASE_JWT_SECRET not set; cannot verify real JWTs")
            return None
        return pyjwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except Exception as exc:
        logger.info("JWT verification failed: %s", exc)
        return None


def get_current_user_id() -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()

    if config.using_real_supabase:
        claims = _decode_supabase_jwt(token)
        return claims.get("sub") if claims else None

    if config.DEMO_MODE:
        # Explicitly opted into demo mode: accept any bearer token and map
        # it to one shared demo user. Only reachable when DEMO_MODE=true
        # was deliberately set — never a silent fallback.
        return DEMO_USER_ID

    # No real Supabase AND no explicit demo-mode opt-in: refuse. The
    # alternative — quietly accepting any token as a valid "demo-user" —
    # is exactly the kind of thing that looks like it's working in a demo
    # and is actually wide open once deployed. Fail loudly instead.
    logger.warning(
        "Rejected request: no Supabase credentials configured and DEMO_MODE "
        "is not enabled. Set real SUPABASE_* env vars, or explicitly set "
        "DEMO_MODE=true if you understand this disables real authentication."
    )
    return None


def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        g.user_id = user_id
        return fn(*args, **kwargs)
    return wrapper


def require_admin(db):
    """Factory: require_admin(db_service) -> decorator, since role lives in Supabase."""
    def decorator(fn):
        @functools.wraps(fn)
        @require_auth
        def wrapper(*args, **kwargs):
            profile = db.get_profile(g.user_id)
            if not profile or profile.get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
