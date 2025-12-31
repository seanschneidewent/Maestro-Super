"""Supabase JWT validation."""

import httpx
from functools import lru_cache
from fastapi import HTTPException, status
import jwt
from jwt import PyJWKClient

from app.auth.schemas import TokenPayload
from app.config import get_settings


_jwks_client = None


def get_jwks_client():
    """Get or create JWKS client."""
    global _jwks_client
    if _jwks_client is None:
        settings = get_settings()
        if settings.supabase_url:
            jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
            _jwks_client = PyJWKClient(jwks_url)
    return _jwks_client


def validate_supabase_jwt(token: str) -> TokenPayload:
    """
    Validate Supabase JWT and extract claims.

    Args:
        token: The JWT token string (without "Bearer " prefix)

    Returns:
        TokenPayload with user_id (sub), email, and expiration

    Raises:
        HTTPException 401 on invalid/expired token
    """
    settings = get_settings()

    # First try JWKS verification (for ECC keys)
    jwks_client = get_jwks_client()
    if jwks_client:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                options={"verify_aud": False},
            )
            return TokenPayload(
                sub=payload["sub"],
                email=payload.get("email"),
                exp=payload["exp"],
            )
        except jwt.exceptions.PyJWTError as e:
            # Log but continue to try HS256 fallback
            print(f"JWKS verification failed: {e}")

    # Fallback to HS256 with legacy secret
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret not configured",
        )

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return TokenPayload(
            sub=payload["sub"],
            email=payload.get("email"),
            exp=payload["exp"],
        )
    except jwt.exceptions.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
