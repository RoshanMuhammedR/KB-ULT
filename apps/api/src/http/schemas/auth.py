from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    # Email is the account's globally-unique identifier; `name` only labels the workspace.
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class GoogleSignInRequest(BaseModel):
    """The ID token Google Identity Services handed the browser."""

    id_token: str = Field(min_length=1, max_length=8192)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    user_id: str
    email: str
    name: str
    tenant_id: str
    workspace_name: str
