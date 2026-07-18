from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    # `domain` is the tenant's globally-unique slug; it also identifies the tenant at login.
    domain: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
