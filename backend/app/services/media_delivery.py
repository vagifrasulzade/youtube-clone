"""Serve an object from storage AFTER the caller has been authorized.

- accel (production): return an empty response with `X-Accel-Redirect` to nginx's
  internal location; nginx fetches a 60-second presigned URL from MinIO and streams it,
  passing the client's Range header through (206, seeking, keep-alive).
- proxy (dev/tests): stream from MinIO through FastAPI, forwarding Range.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from botocore.exceptions import ClientError
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.storage import s3

# A single byte range only ("bytes=start-end", "bytes=start-", "bytes=-suffix").
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 256 * 1024
ACCEL_PREFIX = "/_media"


def _safe_range(header: str | None) -> str | None:
    if not header:
        return None
    match = _RANGE_RE.match(header.strip())
    if not match or (not match.group(1) and not match.group(2)):
        return None  # malformed or multi-range: serve the whole object
    return header.strip()


def serve_object(
    request: Request, bucket: str, key: str, *, content_type: str, cache_control: str
) -> Response:
    headers = {
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }
    settings = get_settings()

    if settings.media_delivery == "accel":
        signed = urlsplit(
            s3.presign_get(bucket, key, expires_in=settings.internal_presign_ttl_seconds)
        )
        target = f"{ACCEL_PREFIX}{signed.path}" + (f"?{signed.query}" if signed.query else "")
        return Response(
            status_code=200,
            media_type=content_type,
            headers={**headers, "X-Accel-Redirect": target},
        )

    try:
        obj = s3.get_stream(bucket, key, _safe_range(request.headers.get("range")))
    except ClientError as exc:
        error = exc.response.get("Error", {})
        if error.get("Code") == "InvalidRange":
            size = s3.head(bucket, key)
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{size.size if size else 0}"},
            )
        raise NotFoundError("Media not found", code="media_not_found") from exc

    headers["Accept-Ranges"] = "bytes"
    headers["Content-Length"] = str(obj["ContentLength"])
    status_code = 200
    if obj.get("ContentRange"):
        headers["Content-Range"] = obj["ContentRange"]
        status_code = 206
    return StreamingResponse(
        obj["Body"].iter_chunks(chunk_size=_CHUNK),
        status_code=status_code,
        media_type=content_type,
        headers=headers,
    )


def cache_control_for(openly_viewable: bool) -> str:
    return "public, max-age=3600" if openly_viewable else "private, no-store"
