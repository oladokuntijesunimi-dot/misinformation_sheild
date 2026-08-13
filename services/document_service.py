"""
Document processing service (sections 32 & 46 of the spec).

Handles text extraction from uploaded PDF / DOCX / TXT / HTML files and
chunking for embedding. Kept separate from the RAG agent so it can be
reused by both the knowledge-base upload flow and ad-hoc "analyze this
document" claim submissions.
"""
from __future__ import annotations

import re
from typing import List

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html", ".htm"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB default ceiling; overridden by config.MAX_UPLOAD_MB in routes


def is_allowed_filename(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def extract_text(file_bytes: bytes, file_type: str) -> str:
    """Extract plain text from raw file bytes based on declared file_type."""
    file_type = file_type.lower().lstrip(".")
    if file_type == "txt":
        return file_bytes.decode("utf-8", errors="ignore")
    if file_type in ("html", "htm"):
        raw = file_bytes.decode("utf-8", errors="ignore")
        return re.sub(r"<[^>]+>", " ", raw)
    if file_type == "pdf":
        return _extract_pdf(file_bytes)
    if file_type == "docx":
        return _extract_docx(file_bytes)
    raise ValueError(f"Unsupported file_type: {file_type}")


def _extract_pdf(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        return ""


def _extract_docx(file_bytes: bytes) -> str:
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        return ""


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    """
    Simple sliding-window chunker on whitespace-normalized text. Good
    enough for semantic retrieval; swap for a token-aware splitter if
    precise token budgets matter for your embedding model.
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    chunks = []
    start = 0
    n = len(normalized)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = end - overlap
    return chunks
