"""Input validation helpers (sections 45 & 46)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

MAX_TEXT_LENGTH = 20000
ALLOWED_INPUT_TYPES = {"text", "url", "document", "social_media", "multiple_claims"}
ALLOWED_CATEGORIES = {
    "Politics", "Health", "Education", "Economy", "Security",
    "Technology", "Finance", "Entertainment", "Other",
}


class ValidationError(ValueError):
    pass


def validate_text_input(text: str) -> str:
    if not text or not text.strip():
        raise ValidationError("Content cannot be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValidationError(f"Content exceeds maximum length of {MAX_TEXT_LENGTH} characters.")
    return text.strip()


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("Please provide a valid http(s) URL.")
    return url


def validate_input_type(input_type: str) -> str:
    if input_type not in ALLOWED_INPUT_TYPES:
        raise ValidationError(f"input_type must be one of {sorted(ALLOWED_INPUT_TYPES)}")
    return input_type


def validate_category(category: str | None) -> str | None:
    if category is None or category == "":
        return None
    if category not in ALLOWED_CATEGORIES:
        raise ValidationError(f"category must be one of {sorted(ALLOWED_CATEGORIES)}")
    return category


def sanitize_filename(filename: str) -> str:
    filename = filename.strip().replace("/", "_").replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:200]
