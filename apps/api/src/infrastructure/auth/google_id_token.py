"""Verification of Google ID tokens.

The browser gets a signed ID token from Google Identity Services and posts it here; this
adapter checks the signature, audience and issuer, then hands back the identity inside.
Verification is local — Google's public keys are fetched once and cached by `PyJWKClient` —
so a sign-in costs no extra round trip to Google.

No client secret is involved anywhere: the ID-token flow only needs the (public) client id.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
import structlog
from jwt import PyJWKClient

from src.core.exceptions import InvalidCredentialsError

logger = structlog.get_logger(__name__)

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# Google has issued tokens under both spellings for years; both are legitimate.
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str = ""


class GoogleIdTokenVerifier:
    """Verifies an ID token against Google's published keys.

    Constructed once in the composition root so the JWKS cache inside `PyJWKClient` is
    shared across sign-ins rather than refetched per request.
    """

    def __init__(self, client_id: str, jwks_url: str = GOOGLE_JWKS_URL) -> None:
        self.client_id = client_id
        self._jwks_client = PyJWKClient(jwks_url, cache_keys=True)

    @property
    def configured(self) -> bool:
        """False when no client id is set — the route 503s and the UI hides the button."""
        return bool(self.client_id)

    def verify(self, id_token: str) -> GoogleIdentity:
        if not self.configured:
            raise InvalidCredentialsError("Google sign-in is not configured on this server")

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=list(GOOGLE_ISSUERS),
            )
        except Exception as exc:  # noqa: BLE001 - every failure is one generic denial
            # The specific reason (expired, wrong audience, bad signature) is logged
            # server-side only; the caller gets the same message either way.
            logger.info("google_id_token_rejected", reason=str(exc))
            raise InvalidCredentialsError("Invalid credentials or inactive account") from exc

        email = (claims.get("email") or "").strip().lower()
        if not email:
            raise InvalidCredentialsError("Invalid credentials or inactive account")

        return GoogleIdentity(
            subject=str(claims["sub"]),
            email=email,
            # Google returns this as a bool, but some clients stringify it.
            email_verified=claims.get("email_verified") in (True, "true", "True"),
            name=(claims.get("name") or "").strip(),
        )
