class KBError(Exception):
    """Base application exception."""


class UnsupportedSourceTypeError(KBError):
    """Raised when no parser is registered for a source type."""


class FileStorageError(KBError):
    """Raised when object storage operations fail."""


class DuplicateAssetVersionError(KBError):
    """Two uploads of the same filename computed the same version number.

    `uq_asset_lineage_version` catches it, which is the constraint doing its job — the
    caller's move is to recompute the version and try again, not to surface a 500.
    """


class IngestionError(KBError):
    """Raised by the worker when an ingestion attempt fails.

    Re-raised out of `process_ingestion` so the queue engine can drive its retry
    policy; the asset/job records already carry the failed step and error detail.
    """


class ProviderUnavailableError(KBError):
    """The AI gateway is failing and the circuit breaker has stopped calling it.

    Raised without any network round-trip: a provider that has failed repeatedly is not
    worth a per-call timeout, and burning an ingestion job's whole retry budget against a
    host that is down helps nobody.
    """


class MissingTenantContextError(KBError):
    """Raised when a tenant-scoped query/flush runs with no tenant in context.

    The tenant auto-filter fails CLOSED: rather than silently returning or writing
    across all tenants, any access to a `TenantScoped` table without a current tenant
    raises this. Legitimate cross-tenant/no-tenant work (auth, migrations, seeds, the
    break-glass path) must run inside `system_scope()`.
    """


class AuthError(KBError):
    """Base for authentication/registration failures."""


class EmailAlreadyExistsError(AuthError):
    """Registration hit the global-unique `users.email` constraint."""


class InvalidCredentialsError(AuthError):
    """Login failed. Deliberately generic — never says which factor failed (see
    the anti-enumeration handling in the auth service)."""


class TokenError(AuthError):
    """An access/refresh token was missing, malformed, expired, or revoked."""
