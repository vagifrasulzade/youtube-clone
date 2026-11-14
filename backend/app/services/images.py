"""Safe handling of user-supplied images (avatars, banners, custom thumbnails).

Every image is fully decoded and re-encoded to a fresh JPEG. This strips metadata
(EXIF/GPS), normalizes orientation and defeats polyglot files: what we store is
pixels we produced, not bytes the user sent.
"""

from __future__ import annotations

import warnings
from io import BytesIO
from typing import BinaryIO, Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import PayloadTooLargeError, UnsupportedMediaError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000  # decompression-bomb guard (e.g. a 50k x 50k PNG of a few KB)

ImageKind = Literal["avatar", "banner", "thumbnail"]

# Anything Pillow raises on malformed or hostile input.
_DECODE_ERRORS = (
    UnidentifiedImageError,
    Image.DecompressionBombError,
    Image.DecompressionBombWarning,
    OSError,
    SyntaxError,
    ValueError,
)

TARGET_SIZES: dict[ImageKind, tuple[int, int]] = {
    "avatar": (800, 800),
    "banner": (2560, 1440),
    "thumbnail": (1280, 720),
}


def read_limited(stream: BinaryIO, max_bytes: int) -> bytes:
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"Image must be at most {max_bytes // 1024} KB",
            code="file_too_large",
            details={"max_bytes": max_bytes},
        )
    if not data:
        raise UnsupportedMediaError("Empty file", code="invalid_image")
    return data


def reencode_jpeg(data: bytes, kind: ImageKind) -> bytes:
    """Validate and re-encode; crop to the target aspect ratio (cover)."""
    invalid = UnsupportedMediaError("Upload a JPEG, PNG or WebP image", code="invalid_image")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(BytesIO(data)) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise invalid
                if source.width * source.height > MAX_PIXELS:
                    raise invalid
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
        except _DECODE_ERRORS as exc:
            raise invalid from exc

    image = ImageOps.fit(image, TARGET_SIZES[kind], Image.Resampling.LANCZOS)
    out = BytesIO()
    image.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue()
