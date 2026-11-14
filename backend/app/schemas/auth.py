"""Authentication requests and responses."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import Handle, SingleLineText
from app.schemas.user import CurrentUserOut

# Upper bound protects the Argon2 hasher from multi-megabyte "passwords".
Password = Annotated[str, Field(min_length=8, max_length=128)]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    handle: Handle
    display_name: Annotated[SingleLineText, Field(min_length=1, max_length=50)]

    @model_validator(mode="after")
    def _normalize_and_check(self) -> Self:
        self.email = _normalize_email(self.email)
        lowered = self.password.lower()
        if lowered in {self.email, self.handle, self.email.split("@")[0]}:
            raise ValueError("password must not be the same as your email or handle")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        self.email = _normalize_email(self.email)
        return self


class ChangePasswordRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Password


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    user: CurrentUserOut
