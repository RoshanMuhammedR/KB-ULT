from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.auth import AuthService, AuthTokens
from src.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    TokenError,
)
from src.core.config import Settings, get_settings
from src.core.identity import Identity
from src.http.dependencies import get_auth_service, get_current_identity
from src.http.schemas.auth import (
    GoogleSignInRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
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
    # Creates the workspace and its owner user atomically, then auto-logs-in (returns tokens).
    try:
        tokens = auth_service.register(
            email=request.email,
            password=request.password,
            name=request.name,
        )
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    # Generic 401 on any failure (unknown email, bad password, inactive user/workspace) — the
    # specific reason is logged server-side only, to avoid account enumeration.
    try:
        tokens = auth_service.login(email=request.email, password=request.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _to_token_response(tokens)


@router.post("/google", response_model=TokenResponse)
def google_sign_in(
    request: GoogleSignInRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    # Signs in or registers in one step from a Google ID token the browser already holds.
    # 503 rather than 401 when unconfigured: it's a server capability that's missing, not a
    # bad credential, and the client uses that to hide the button.
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this server",
        )
    try:
        tokens = auth_service.sign_in_with_google(request.id_token)
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
    # expire (~15 min) — the deliberate tradeoff of stateless access tokens.
    auth_service.logout(request.refresh_token)


@router.get("/me", response_model=MeResponse)
def me(
    identity: Annotated[Identity, Depends(get_current_identity)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    # Resolves the authenticated identity into a display profile for the account area.
    try:
        profile = auth_service.me(user_id=identity.user_id, tenant_id=identity.tenant_id)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return MeResponse(
        user_id=str(profile.user_id),
        email=profile.email,
        name=profile.name,
        tenant_id=str(profile.tenant_id),
        workspace_name=profile.workspace_name,
    )
