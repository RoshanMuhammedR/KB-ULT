from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.auth import AuthService, AuthTokens
from src.core.exceptions import (
    DomainAlreadyExistsError,
    InvalidCredentialsError,
    TokenError,
)
from src.core.identity import Identity
from src.http.dependencies import get_auth_service, get_current_identity
from src.http.schemas.auth import (
    HandoffExchangeRequest,
    HandoffIssueResponse,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _origin_host(request: Request) -> str | None:
    """Hostname of the request's browser Origin (falling back to the Host header). Used to
    enforce that a login happens from the tenant's own domain."""
    origin = request.headers.get("origin")
    if origin:
        host = urlparse(origin).hostname
        if host:
            return host
    host_header = request.headers.get("host")
    if host_header:
        return host_header.split(":", 1)[0]
    return None


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
    http_request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    # Generic 401 on any failure (unknown domain, inactive tenant/user, bad password, or an
    # Origin that doesn't match the tenant domain) — the specific reason is logged
    # server-side only, to avoid account/tenant enumeration.
    try:
        tokens = auth_service.login(
            domain=request.domain,
            email=request.email,
            password=request.password,
            origin_host=_origin_host(http_request),
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


@router.get("/me", response_model=MeResponse)
def me(
    identity: Annotated[Identity, Depends(get_current_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    # Resolves the bearer token's identity into a display profile for the account area.
    try:
        profile = auth_service.me(user_id=identity.user_id, tenant_id=identity.tenant_id)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return MeResponse(
        user_id=str(profile.user_id),
        email=profile.email,
        tenant_id=str(profile.tenant_id),
        domain=profile.domain,
        name=profile.name,
    )


@router.post("/handoff/issue", response_model=HandoffIssueResponse)
def issue_handoff(
    identity: Annotated[Identity, Depends(get_current_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> HandoffIssueResponse:
    # Auth-required: mint a single-use code the caller can carry to their tenant domain.
    code, expires_in = auth_service.issue_handoff(user_id=identity.user_id)
    return HandoffIssueResponse(code=code, expires_in=expires_in)


@router.post("/handoff/exchange", response_model=TokenResponse)
def exchange_handoff(
    request: HandoffExchangeRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    # Public: redeem the single-use code (issued on the marketing origin) for a fresh
    # session on the tenant domain. Generic 401 if unknown/expired/already used.
    try:
        tokens = auth_service.exchange_handoff(request.code)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)
