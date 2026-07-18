from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.auth import AuthService, AuthTokens
from src.core.exceptions import (
    DomainAlreadyExistsError,
    InvalidCredentialsError,
    TokenError,
)
from src.http.dependencies import get_auth_service
from src.http.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_token_response(tokens: AuthTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    # Creates the tenant and its single user atomically, then auto-logs-in (returns tokens).
    try:
        tokens = auth_service.register(
            domain=request.domain,
            email=request.email,
            password=request.password,
            name=request.name,
        )
    except DomainAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    # Generic 401 on any failure (unknown domain, inactive tenant/user, bad password) — the
    # specific reason is logged server-side only, to avoid account/tenant enumeration.
    try:
        tokens = auth_service.login(
            domain=request.domain, email=request.email, password=request.password
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: RefreshRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        tokens = auth_service.refresh(request.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: LogoutRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    # Idempotent: revokes the refresh-token family. Access tokens remain valid until they
    # expire (~15 min) — the deliberate tradeoff of stateless access tokens (plan §4).
    auth_service.logout(request.refresh_token)
