"""Reusable validated field types."""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _lower(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


def _reject_control_chars(allowed: str) -> AfterValidator:
    def check(value: str) -> str:
        for char in value:
            if unicodedata.category(char) in {"Cc", "Cf"} and char not in allowed:
                raise ValueError("must not contain control characters")
        return value

    return AfterValidator(check)


# One line of user-visible text (titles, names): trimmed, no control characters.
SingleLineText = Annotated[str, BeforeValidator(_strip), _reject_control_chars("")]

# Multi-line text (descriptions, comments): newlines and tabs allowed.
MultiLineText = Annotated[str, BeforeValidator(_strip), _reject_control_chars("\n\t\r")]

Handle = Annotated[
    str,
    BeforeValidator(_lower),
    StringConstraints(pattern=r"^[a-z0-9._-]{3,30}$"),
]
