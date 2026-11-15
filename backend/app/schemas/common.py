"""Reusable validated field types."""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints


class RequestModel(BaseModel):
    """Base for request bodies: unknown fields are rejected (422), so fields such as
    `status`, `role` or `channel_id` can never be mass-assigned."""

    model_config = ConfigDict(extra="forbid")


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _lower(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


def _reject_control_chars(allowed: str) -> AfterValidator:
    def check(value: str) -> str:
        for char in value:
            if unicodedata.category(char) in {"Cc", "Cf", "Cs"} and char not in allowed:
                raise ValueError("must not contain control characters")
        return value

    return AfterValidator(check)


# One line of user-visible text (titles, names): trimmed, no control characters.
SingleLineText = Annotated[str, BeforeValidator(_strip), _reject_control_chars("")]

# Multi-line text (descriptions, comments): newlines and tabs allowed.
# U+200D (zero-width joiner) builds emoji such as family and flag sequences.
MultiLineText = Annotated[str, BeforeValidator(_strip), _reject_control_chars("\n\t\r\u200d")]

Handle = Annotated[
    str,
    BeforeValidator(_lower),
    StringConstraints(pattern=r"^[a-z0-9._-]{3,30}$"),
]
