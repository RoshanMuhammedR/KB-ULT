import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

# structlog is an optional import in this test environment, matching the other service tests.
sys.modules.setdefault("structlog", SimpleNamespace(get_logger=lambda *_: Mock()))

from src.application.auth.service import AuthService  # noqa: E402
from src.core.exceptions import InvalidCredentialsError  # noqa: E402
from src.domain.entities.tenant import Tenant, TenantStatus  # noqa: E402
from src.domain.entities.user import User, UserStatus  # noqa: E402
from src.domain.interfaces.auth import GoogleIdentity  # noqa: E402


class _StubVerifier:
    """Constructor seam — no network, no Google keys, no real JWT."""

    def __init__(self, identity: GoogleIdentity | None = None, error: Exception | None = None):
        self.identity = identity
        self.error = error

    def verify(self, id_token: str) -> GoogleIdentity:
        if self.error is not None:
            raise self.error
        assert self.identity is not None
        return self.identity


def _identity(**overrides) -> GoogleIdentity:
    values = {
        "subject": "google-sub-123",
        "email": "dana@example.com",
        "email_verified": True,
        "name": "Dana Okafor",
    }
    values.update(overrides)
    return GoogleIdentity(**values)


def _user(**overrides) -> User:
    values = {
        "tenant_id": uuid4(),
        "email": "dana@example.com",
        "password_hash": "argon2-hash",
        "status": UserStatus.ACTIVE,
    }
    values.update(overrides)
    return User(**values)


def _build_service(verifier: _StubVerifier, **overrides) -> tuple[AuthService, dict]:
    tenant_repo = Mock()
    user_repo = Mock()
    refresh_repo = Mock()
    token_service = Mock()

    tenant_repo.get.return_value = Tenant(name="Dana", status=TenantStatus.ACTIVE)
    tenant_repo.create.side_effect = lambda tenant: tenant
    user_repo.get_by_google_sub.return_value = None
    user_repo.get_by_email.return_value = None
    user_repo.create.side_effect = lambda user: user
    token_service.issue_access_token.return_value = ("access-token", 900)

    mocks = {
        "tenant_repo": tenant_repo,
        "user_repo": user_repo,
        "refresh_repo": refresh_repo,
        "token_service": token_service,
    }
    mocks.update(overrides)

    service = AuthService(
        tenant_repo=mocks["tenant_repo"],
        user_repo=mocks["user_repo"],
        refresh_repo=mocks["refresh_repo"],
        password_hasher=Mock(),
        token_service=mocks["token_service"],
        unit_of_work=Mock(),
        refresh_ttl_seconds=3600,
        google_verifier=verifier,
    )
    return service, mocks


class GoogleSignInTest(TestCase):
    def test_new_email_creates_a_tenant_and_a_passwordless_user(self) -> None:
        service, mocks = _build_service(_StubVerifier(_identity()))

        tokens = service.sign_in_with_google("id-token")

        self.assertEqual(tokens.access_token, "access-token")
        mocks["tenant_repo"].create.assert_called_once()
        created = mocks["user_repo"].create.call_args[0][0]
        self.assertEqual(created.email, "dana@example.com")
        self.assertEqual(created.google_sub, "google-sub-123")
        self.assertIsNone(created.password_hash)
        # Google already verified the address, so the account starts verified.
        self.assertIsNotNone(created.email_verified_at)

    def test_returning_google_user_is_resolved_by_subject(self) -> None:
        existing = _user(google_sub="google-sub-123", password_hash=None)
        service, mocks = _build_service(_StubVerifier(_identity()))
        mocks["user_repo"].get_by_google_sub.return_value = existing

        service.sign_in_with_google("id-token")

        mocks["user_repo"].create.assert_not_called()
        mocks["tenant_repo"].create.assert_not_called()
        mocks["user_repo"].link_google.assert_not_called()

    def test_existing_password_account_is_linked_not_duplicated(self) -> None:
        existing = _user()
        service, mocks = _build_service(_StubVerifier(_identity()))
        mocks["user_repo"].get_by_google_sub.return_value = None
        mocks["user_repo"].get_by_email.return_value = existing
        mocks["user_repo"].link_google.return_value = _user(
            google_sub="google-sub-123", tenant_id=existing.tenant_id
        )

        service.sign_in_with_google("id-token")

        mocks["user_repo"].link_google.assert_called_once_with(existing.id, "google-sub-123")
        # One account, one library — no second tenant is created.
        mocks["tenant_repo"].create.assert_not_called()
        mocks["user_repo"].create.assert_not_called()

    def test_unverified_google_email_is_refused(self) -> None:
        # The check that makes linking-by-email safe in the first place.
        service, mocks = _build_service(_StubVerifier(_identity(email_verified=False)))

        with self.assertRaises(InvalidCredentialsError):
            service.sign_in_with_google("id-token")

        mocks["user_repo"].create.assert_not_called()
        mocks["user_repo"].link_google.assert_not_called()

    def test_inactive_user_is_denied_generically(self) -> None:
        service, mocks = _build_service(_StubVerifier(_identity()))
        mocks["user_repo"].get_by_google_sub.return_value = _user(
            google_sub="google-sub-123", status=UserStatus.SUSPENDED
        )

        with self.assertRaises(InvalidCredentialsError):
            service.sign_in_with_google("id-token")

    def test_inactive_tenant_is_denied_generically(self) -> None:
        service, mocks = _build_service(_StubVerifier(_identity()))
        mocks["user_repo"].get_by_google_sub.return_value = _user(google_sub="google-sub-123")
        mocks["tenant_repo"].get.return_value = Tenant(name="Dana", status=TenantStatus.SUSPENDED)

        with self.assertRaises(InvalidCredentialsError):
            service.sign_in_with_google("id-token")

    def test_an_invalid_token_surfaces_as_the_same_generic_error(self) -> None:
        service, _ = _build_service(
            _StubVerifier(error=InvalidCredentialsError("Invalid credentials or inactive account"))
        )

        with self.assertRaises(InvalidCredentialsError):
            service.sign_in_with_google("tampered-token")

    def test_google_sign_in_without_a_verifier_is_refused(self) -> None:
        service, _ = _build_service(_StubVerifier(_identity()))
        service.google_verifier = None

        with self.assertRaises(InvalidCredentialsError):
            service.sign_in_with_google("id-token")


class PasswordLoginAgainstGoogleAccountTest(TestCase):
    def test_password_login_on_a_passwordless_account_is_generically_denied(self) -> None:
        # Must be indistinguishable from a wrong password: no account enumeration, and no
        # hint about how the account was created.
        service, mocks = _build_service(_StubVerifier(_identity()))
        mocks["user_repo"].get_by_email.return_value = _user(
            password_hash=None, google_sub="google-sub-123"
        )

        with self.assertRaises(InvalidCredentialsError) as caught:
            service.login(email="dana@example.com", password="whatever-they-typed")

        self.assertIn("Invalid credentials", str(caught.exception))
