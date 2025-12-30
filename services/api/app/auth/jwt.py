"""Supabase JWT validation."""

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.auth.schemas import TokenPayload
from app.config import get_settings


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
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
