import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.auth import AuthTokens
from src.core.config import get_settings
from src.http.dependencies.services import get_auth_service
from src.http.routes import auth as auth_routes

TOKENS = AuthTokens(access_token="acc", refresh_token="ref", token_type="bearer", expires_in=900)


class _StubAuthService:
    async def login(self, **kwargs):
        return TOKENS

    async def register(self, **kwargs):
        return TOKENS

    async def refresh(self, *args):
        return TOKENS

    async def sign_in_with_google(self, *args):
        return TOKENS


class AuthRouteSerializationTests(unittest.TestCase):
    """Every auth route must return a serialisable body, not a coroutine.

    These endpoints all funnel through one `_to_token_response` helper. When that helper was
    made `async` without updating its call sites, all four returned a coroutine and FastAPI
    raised ResponseValidationError - a 500 on every sign-in, which reached production because
    nothing exercised route serialisation. The service layer is stubbed on purpose: what is
    under test is the response contract, not authentication itself.
    """

    def setUp(self):
        settings = get_settings()

        class _Settings:
            google_client_id = "test-client-id.apps.googleusercontent.com"

            def __getattr__(self, name):
                return getattr(settings, name)

        app = FastAPI()
        app.include_router(auth_routes.router)
        app.dependency_overrides[get_auth_service] = lambda: _StubAuthService()
        app.dependency_overrides[get_settings] = lambda: _Settings()
        self.client = TestClient(app)

    def _assert_tokens(self, response, expected_status):
        self.assertEqual(response.status_code, expected_status, response.text)
        self.assertEqual(response.json()["access_token"], "acc")
        self.assertEqual(response.json()["expires_in"], 900)

    def test_login_returns_tokens(self):
        self._assert_tokens(
            self.client.post("/auth/login", json={"email": "a@b.co", "password": "hunter2!x"}), 200
        )

    def test_register_returns_tokens(self):
        self._assert_tokens(
            self.client.post(
                "/auth/register",
                json={"email": "a@b.co", "password": "hunter2!x", "name": "Ada"},
            ),
            201,
        )

    def test_refresh_returns_tokens(self):
        self._assert_tokens(self.client.post("/auth/refresh", json={"refresh_token": "r"}), 200)

    def test_google_sign_in_returns_tokens(self):
        self._assert_tokens(self.client.post("/auth/google", json={"id_token": "tok"}), 200)


if __name__ == "__main__":
    unittest.main()
