"""
Misinformation Shield — single-process Flask app.

Run locally with:

    python app.py

This serves the server-rendered UI (Jinja templates in templates/, static
assets in static/) AND the JSON API (blueprints under /api/*) from one
Flask process — no Node.js, no separate frontend server, nothing else to
start. The page templates talk to the same /api/* endpoints from
JavaScript in the browser, using the fixed `demo-token` bearer token that
DEMO_MODE accepts (see utils/auth.py).

In production, run behind a real WSGI server, e.g.:

    gunicorn -w 4 -b 0.0.0.0:8000 app:app
"""
from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template

from config import config

logging.basicConfig(level=logging.INFO if not config.DEBUG else logging.DEBUG)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

    _warn_about_auth_mode()
    _configure_cors(app)
    _configure_rate_limiting(app)
    _register_blueprints(app)
    _register_page_routes(app)
    _register_error_handlers(app)

    @app.get("/api/health")
    def health():
        if config.using_real_supabase:
            auth_mode = "supabase"
        elif config.DEMO_MODE:
            auth_mode = "demo (INSECURE — any bearer token is accepted as one shared user)"
        else:
            auth_mode = "disabled (no real Supabase and DEMO_MODE is not set — all requests are rejected)"

        return jsonify({
            "status": "ok",
            "providers": {
                "llm": "groq" if config.using_real_llm else "mock",
                "supabase": "connected" if config.using_real_supabase else "in-memory",
                "pinecone": "connected" if config.using_real_pinecone else "in-memory",
                "search": config.SEARCH_PROVIDER if config.using_real_search else "mock",
                "embeddings": config.EMBEDDING_PROVIDER if config.using_real_embeddings else "mock",
                "auth": auth_mode,
            },
        })

    return app


def _warn_about_auth_mode():
    if config.using_real_supabase:
        return
    if config.DEMO_MODE:
        logger.warning(
            "=" * 78 + "\n"
            "DEMO_MODE is enabled with no real Supabase project configured.\n"
            "Every visitor is being treated as ONE SHARED user with no real\n"
            "authentication. This is intended for local development and demos\n"
            "ONLY — never deploy this publicly without real Supabase credentials.\n" + "=" * 78
        )
    else:
        logger.warning(
            "=" * 78 + "\n"
            "No real Supabase credentials AND DEMO_MODE is not set.\n"
            "ALL API requests will be rejected with 401 Unauthorized until you\n"
            "either configure real SUPABASE_* env vars, or explicitly set\n"
            "DEMO_MODE=true in your .env (local development / demos only).\n" + "=" * 78
        )


def _configure_cors(app: Flask):
    from flask_cors import CORS
    # The UI is served from this same Flask app now, so cross-origin
    # requests to /api/* are no longer required for normal use — this
    # just keeps the option open for a separately hosted client.
    CORS(app, resources={r"/api/*": {"origins": [config.FRONTEND_URL, "*"]}}, supports_credentials=False)


def _configure_rate_limiting(app: Flask):
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        limiter = Limiter(
            get_remote_address, app=app,
            default_limits=[f"{config.RATE_LIMIT_PER_MINUTE} per minute"],
            storage_uri="memory://",
        )
        app.extensions["limiter"] = limiter
    except ImportError:
        logger.warning("flask-limiter not installed; rate limiting disabled")


def _register_blueprints(app: Flask):
    from routes import admin, auth, claims, documents, investigations, reports

    app.register_blueprint(auth.bp)
    app.register_blueprint(investigations.bp)
    app.register_blueprint(claims.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(admin.bp)


def _register_page_routes(app: Flask):
    """Server-rendered pages. All data fetching happens client-side against
    the /api/* JSON endpoints registered above, using the shared demo
    bearer token — see static/js/app.js."""

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/verify")
    def verify():
        return render_template("verify.html")

    @app.get("/investigations")
    def investigations_page():
        return render_template("investigations.html")

    @app.get("/investigations/<investigation_id>")
    def investigation_detail(investigation_id: str):
        return render_template("investigation.html", investigation_id=investigation_id)

    @app.get("/about")
    def about():
        return render_template("about.html")


def _register_error_handlers(app: Flask):
    @app.errorhandler(404)
    def not_found(_):
        if _wants_json():
            return jsonify({"error": "Not found"}), 404
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": "File too large"}), 413

    @app.errorhandler(Exception)
    def unhandled(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        # Never leak raw stack traces to clients (section 53).
        logger.exception("Unhandled error")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


def _wants_json() -> bool:
    from flask import request
    return request.path.startswith("/api/")


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  Misinformation Shield running → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=config.DEBUG)
