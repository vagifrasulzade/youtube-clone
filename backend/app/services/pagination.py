"""Keyset (cursor) pagination helpers.

A cursor is the opaque, URL-safe encoding of the sort key of the last item returned,
e.g. [published_at, id]. Keyset pagination stays fast and stable on large tables
(no OFFSET scans, no duplicates when new rows arrive while scrolling).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from app.core.errors import BadRequestError

MAX_LIMIT = 50


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def encode_cursor(*values: Any) -> str:
    def default(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    raw = json.dumps(list(values), default=default, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, size: int) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, TypeError) as exc:
        raise BadRequestError("Invalid cursor", code="invalid_cursor") from exc
    if not isinstance(values, list) or len(values) != size:
        raise BadRequestError("Invalid cursor", code="invalid_cursor")
    return values


def parse_datetime(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise BadRequestError("Invalid cursor", code="invalid_cursor") from exc
