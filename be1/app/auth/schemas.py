"""Public request, response, and error schemas for the authentication API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.config import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

PhoneInput = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=5,
        max_length=32,
    ),
]
PasswordInput = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    ),
]


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictRequestModel):
    phone: PhoneInput
    password: PasswordInput
    password_confirmation: PasswordInput

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(StrictRequestModel):
    phone: PhoneInput
    password: PasswordInput


class UserResponse(BaseModel):
    id: uuid.UUID
    phone_e164: str
    masked_phone: str
    is_active: bool


class AuthSessionResponse(BaseModel):
    user: UserResponse
    access_expires_at: datetime
    is_new_user: bool = False


class ValidationIssue(BaseModel):
    field: str
    code: str
    message: str


class ApiError(BaseModel):
    code: str
    message: str
    details: list[ValidationIssue] | dict[str, Any] | None = None


class ApiErrorResponse(BaseModel):
    error: ApiError
