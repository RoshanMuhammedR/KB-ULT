class KBError(Exception):
    """Base application exception."""


class UnsupportedSourceTypeError(KBError):
    """Raised when no parser is registered for a source type."""


class FileStorageError(KBError):
    """Raised when object storage operations fail."""


class IngestionError(KBError):
    """Raised by the worker when an ingestion attempt fails.

    Re-raised out of `process_ingestion` so the queue engine can drive its retry
    policy; the asset/job records already carry the failed step and error detail.
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


class DomainAlreadyExistsError(AuthError):
    """Registration hit the global-unique `tenants.domain` constraint."""


class InvalidCredentialsError(AuthError):
    """Login failed. Deliberately generic — never says which factor failed (see
    the anti-enumeration handling in the auth service)."""


class TokenError(AuthError):
    """An access/refresh token was missing, malformed, expired, or revoked."""
