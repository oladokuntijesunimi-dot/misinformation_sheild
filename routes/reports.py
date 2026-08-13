"""Saved reports + PDF export routes (sections 31, 41, 49)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request, send_file

from services.supabase_service import get_supabase_service
from utils.auth import require_auth

bp = Blueprint("reports", __name__, url_prefix="/api/reports")
db = get_supabase_service()

DISCLAIMER = (
    "This is an AI-assisted assessment based on available evidence. "
    "It is not an absolute determination of truth."
)


@bp.get("/<investigation_id>")
@require_auth
def get_report(investigation_id: str):
    investigation = db.get_investigation(investigation_id)
    if not investigation or investigation["user_id"] != g.user_id:
        return jsonify({"error": "Not found"}), 404
    claims = db.list_claims_for_investigation(investigation_id)
    claims_with_evidence = [{**c, "evidence": db.list_evidence_for_claim(c["id"])} for c in claims]
    return jsonify({"investigation": investigation, "claims": claims_with_evidence})


@bp.post("/<investigation_id>/save")
@require_auth
def save_report(investigation_id: str):
    investigation = db.get_investigation(investigation_id)
    if not investigation or investigation["user_id"] != g.user_id:
        return jsonify({"error": "Not found"}), 404
    payload = request.get_json(silent=True) or {}
    saved = db.create_saved_report({
        "user_id": g.user_id,
        "investigation_id": investigation_id,
        "title": payload.get("title", investigation["original_content"][:60]),
        "notes": payload.get("notes", ""),
    })
    return jsonify(saved), 201


@bp.get("")
@require_auth
def list_saved_reports():
    return jsonify(db.list_saved_reports(g.user_id))


@bp.get("/<investigation_id>/export")
@require_auth
def export_pdf(investigation_id: str):
    investigation = db.get_investigation(investigation_id)
    if not investigation or investigation["user_id"] != g.user_id:
        return jsonify({"error": "Not found"}), 404

    claims = db.list_claims_for_investigation(investigation_id)
    buf = _build_pdf(investigation, claims)
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=f"misinformation-shield-report-{investigation_id[:8]}.pdf",
    )


def _build_pdf(investigation: dict, claims: list) -> io.BytesIO:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    y = height - inch

    def line(text, size=11, gap=16, bold=False):
        nonlocal y
        if y < inch:
            c.showPage()
            y = height - inch
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(inch, y, text[:110])
        y -= gap

    line("MISINFORMATION SHIELD", size=16, bold=True, gap=20)
    line("FACT-CHECK REPORT", size=12, bold=True, gap=24)

    for claim in claims:
        line(f"Claim: {claim['claim_text']}", bold=True)
        line(f"Verdict: {(claim.get('verdict') or 'unverifiable').upper()}")
        line(f"Veracity: {claim.get('veracity_score', '-')} / 100")
        line(f"Confidence: {claim.get('confidence_score', '-')}%")
        line("Assessment:")
        for chunk in _wrap(claim.get("summary") or "No summary available.", 95):
            line(chunk, size=10)
        evidence = db.list_evidence_for_claim(claim["id"])
        line("Supporting Evidence:", bold=True)
        for e in [e for e in evidence if e["evidence_type"] == "supporting"][:5]:
            line(f"- {e['title']} ({e.get('publisher', '')})", size=9)
        line("Contradicting Evidence:", bold=True)
        for e in [e for e in evidence if e["evidence_type"] == "contradicting"][:5]:
            line(f"- {e['title']} ({e.get('publisher', '')})", size=9)
        line("", gap=10)

    line(f"Generated: {datetime.now(timezone.utc).isoformat()}", size=9)
    line("Disclaimer:", size=9, bold=True)
    for chunk in _wrap(DISCLAIMER, 100):
        line(chunk, size=9)

    c.save()
    buf.seek(0)
    return buf


def _wrap(text: str, width: int):
    words = text.split()
    lines, current = [], ""
    for w in words:
        if len(current) + len(w) + 1 > width:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}".strip()
    if current:
        lines.append(current)
    return lines
