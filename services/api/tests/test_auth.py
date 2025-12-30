"""Tests for auth module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.auth.jwt import validate_supabase_jwt
from app.auth.schemas import TokenPayload, User

# Test secret - only used in tests
TEST_SECRET = "test-secret-key-for-testing-only"


def make_test_token(
    user_id: str,
    email: str | None = "test@test.com",
    expired: bool = False,
    secret: str = TEST_SECRET,
) -> str:
    """Create a test JWT token."""
    if expired:
        exp = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        exp = datetime.now(timezone.utc) + timedelta(hours=1)

    payload = {
        "sub": user_id,
        "exp": exp,
    }
    if email:
        payload["email"] = email

    return jwt.encode(payload, secret, algorithm="HS256")


class TestTokenPayload:
    """Test TokenPayload schema."""

    def test_token_payload_creation(self):
        """Test creating a TokenPayload."""
        payload = TokenPayload(sub="user-123", email="test@test.com", exp=1234567890)
        assert payload.sub == "user-123"
        assert payload.email == "test@test.com"
        assert payload.exp == 1234567890

    def test_token_payload_optional_email(self):
        """Test TokenPayload with optional email."""
        payload = TokenPayload(sub="user-123", exp=1234567890)
        assert payload.sub == "user-123"
        assert payload.email is None


class TestUser:
    """Test User schema."""

    def test_user_creation(self):
        """Test creating a User."""
        user = User(id="user-123", email="test@test.com")
        assert user.id == "user-123"
        assert user.email == "test@test.com"

    def test_user_optional_email(self):
        """Test User with optional email."""
        user = User(id="user-123")
        assert user.id == "user-123"
        assert user.email is None


class TestValidateSupabaseJwt:
    """Test JWT validation."""

    def test_valid_jwt(self, monkeypatch):
        """Test validating a valid JWT."""
        from app.config import Settings

        # Mock settings with test secret
        mock_settings = Settings(supabase_jwt_secret=TEST_SECRET)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        token = make_test_token("user-123")
        payload = validate_supabase_jwt(token)

        assert payload.sub == "user-123"
        assert payload.email == "test@test.com"
        assert payload.exp > 0

    def test_valid_jwt_no_email(self, monkeypatch):
        """Test validating a JWT without email claim."""
        from app.config import Settings

        mock_settings = Settings(supabase_jwt_secret=TEST_SECRET)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        token = make_test_token("user-123", email=None)
        payload = validate_supabase_jwt(token)

        assert payload.sub == "user-123"
        assert payload.email is None

    def test_expired_jwt(self, monkeypatch):
        """Test rejecting an expired JWT."""
        from app.config import Settings

        mock_settings = Settings(supabase_jwt_secret=TEST_SECRET)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        token = make_test_token("user-123", expired=True)

        with pytest.raises(HTTPException) as exc:
            validate_supabase_jwt(token)

        assert exc.value.status_code == 401
        assert "Invalid or expired token" in exc.value.detail

    def test_invalid_jwt(self, monkeypatch):
        """Test rejecting an invalid JWT."""
        from app.config import Settings

        mock_settings = Settings(supabase_jwt_secret=TEST_SECRET)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        with pytest.raises(HTTPException) as exc:
            validate_supabase_jwt("invalid-token")

        assert exc.value.status_code == 401
        assert "Invalid or expired token" in exc.value.detail

    def test_wrong_secret(self, monkeypatch):
        """Test rejecting a JWT signed with wrong secret."""
        from app.config import Settings

        mock_settings = Settings(supabase_jwt_secret="different-secret")
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        token = make_test_token("user-123", secret=TEST_SECRET)

        with pytest.raises(HTTPException) as exc:
            validate_supabase_jwt(token)

        assert exc.value.status_code == 401

    def test_missing_secret(self, monkeypatch):
        """Test error when JWT secret not configured."""
        from app.config import Settings

        mock_settings = Settings(supabase_jwt_secret=None)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        token = make_test_token("user-123")

        with pytest.raises(HTTPException) as exc:
            validate_supabase_jwt(token)

        assert exc.value.status_code == 500
        assert "JWT secret not configured" in exc.value.detail


class TestGetCurrentUser:
    """Test get_current_user dependency."""

    def test_dev_bypass(self, monkeypatch):
        """Test dev mode bypasses JWT validation."""
        from app.config import Settings

        mock_settings = Settings(dev_user_id="dev-user-123")
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user

        request = MagicMock()
        user = get_current_user(request, None)

        assert user.id == "dev-user-123"
        assert user.email == "dev@local.test"

    def test_valid_credentials(self, monkeypatch):
        """Test with valid JWT credentials."""
        from app.config import Settings
        from fastapi.security import HTTPAuthorizationCredentials

        # No dev bypass
        mock_settings = Settings(
            dev_user_id=None, supabase_jwt_secret=TEST_SECRET
        )
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user

        request = MagicMock()
        token = make_test_token("user-456", email="real@user.com")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = get_current_user(request, credentials)

        assert user.id == "user-456"
        assert user.email == "real@user.com"

    def test_missing_credentials(self, monkeypatch):
        """Test error when no credentials provided (production mode)."""
        from app.config import Settings

        mock_settings = Settings(dev_user_id=None)
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user

        request = MagicMock()

        with pytest.raises(HTTPException) as exc:
            get_current_user(request, None)

        assert exc.value.status_code == 401
        assert "Not authenticated" in exc.value.detail


class TestGetCurrentUserOptional:
    """Test get_current_user_optional dependency."""

    def test_dev_bypass(self, monkeypatch):
        """Test dev mode returns user even without credentials."""
        from app.config import Settings

        mock_settings = Settings(dev_user_id="dev-user-123")
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user_optional

        user = get_current_user_optional(None)

        assert user is not None
        assert user.id == "dev-user-123"

    def test_no_credentials_returns_none(self, monkeypatch):
        """Test returns None when no credentials (production mode)."""
        from app.config import Settings

        mock_settings = Settings(dev_user_id=None)
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user_optional

        user = get_current_user_optional(None)

        assert user is None

    def test_invalid_token_returns_none(self, monkeypatch):
        """Test returns None on invalid token (instead of raising)."""
        from app.config import Settings
        from fastapi.security import HTTPAuthorizationCredentials

        mock_settings = Settings(dev_user_id=None, supabase_jwt_secret=TEST_SECRET)
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user_optional

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid-token"
        )

        user = get_current_user_optional(credentials)

        assert user is None

    def test_valid_token_returns_user(self, monkeypatch):
        """Test returns user with valid token."""
        from app.config import Settings
        from fastapi.security import HTTPAuthorizationCredentials

        mock_settings = Settings(dev_user_id=None, supabase_jwt_secret=TEST_SECRET)
        monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: mock_settings)
        monkeypatch.setattr("app.auth.jwt.get_settings", lambda: mock_settings)

        from app.auth.dependencies import get_current_user_optional

        token = make_test_token("user-789")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = get_current_user_optional(credentials)

        assert user is not None
        assert user.id == "user-789"
