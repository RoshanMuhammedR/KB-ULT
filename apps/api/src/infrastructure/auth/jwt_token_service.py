from __future__ import annotations

import time
import uuid
from uuid import UUID

import jwt

from src.core.exceptions import TokenError
from src.domain.interfaces.auth import AccessTokenClaims


class JwtTokenService:
    """`ITokenService` backed by PyJWT (HS256). Isolates the JWT dependency here.

    Access tokens carry `sub` (user id), `tid` (tenant id), `jti`, and a short `exp`.
    Revocation is handled by rotating refresh tokens (plan §4), so access tokens are not
    checked against any store — a valid signature + unexpired `exp` is sufficient.
    """

    def __init__(self, secret: str, algorithm: str, access_ttl_seconds: int) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_ttl = access_ttl_seconds

    def issue_access_token(self, user_id: UUID, tenant_id: UUID) -> tuple[str, int]:
        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "tid": str(tenant_id),
            "jti": uuid.uuid4().hex,
            "type": "access",
            "iat": now,
            "exp": now + self._access_ttl,
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, self._access_ttl

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise TokenError(f"Invalid access token: {exc}") from exc

        if payload.get("type") != "access":
            raise TokenError("Not an access token")
        try:
            return AccessTokenClaims(
                user_id=UUID(payload["sub"]),
                tenant_id=UUID(payload["tid"]),
                jti=payload["jti"],
            )
        except (KeyError, ValueError) as exc:
            raise TokenError("Malformed access-token claims") from exc
