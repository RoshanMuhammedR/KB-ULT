from __future__ import annotations

from pwdlib import PasswordHash


class Argon2PasswordHasher:
    """`IPasswordHasher` backed by pwdlib's recommended Argon2id hasher.

    Isolates the crypto dependency in infrastructure (the application/domain layers only
    see the `IPasswordHasher` port). Argon2id is the modern default; verifying a malformed
    hash (e.g. the seeded default user's `!disabled`) returns False rather than raising.
    """

    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password, password_hash)
        except Exception:  # noqa: BLE001 - a malformed/legacy hash is a failed verify, not a crash
            return False
