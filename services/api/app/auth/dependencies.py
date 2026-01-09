"""FastAPI dependencies for authentication."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import validate_supabase_jwt
from app.auth.schemas import User
from app.config import get_settings

# HTTPBearer with auto_error=False so we can handle missing tokens ourselves
security = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """
    Get current user from JWT or dev bypass.

    - If DEV_USER_ID is set: return mock user (SQLite dev mode)
    - Otherwise: validate JWT and return user from claims

    Usage:
        @app.get("/items")
        def get_items(user: User = Depends(get_current_user)):
            # user.id is the authenticated user's ID
            ...
    """
    settings = get_settings()

    # Dev bypass for local SQLite development
    if settings.dev_user_id:
        return User(id=settings.dev_user_id, email="dev@local.test")

    # Production: require valid JWT
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = validate_supabase_jwt(credentials.credentials)
    return User(id=token_payload.sub, email=token_payload.email)


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    """
    Optional auth - returns None if no token provided.

    Useful for endpoints that work differently for authenticated vs anonymous users.

    Usage:
        @app.get("/public")
        def public_endpoint(user: User | None = Depends(get_current_user_optional)):
            if user:
                # Show personalized content
                ...
            else:
                # Show generic content
                ...
    """
    settings = get_settings()

    if settings.dev_user_id:
        return User(id=settings.dev_user_id, email="dev@local.test")

    if not credentials:
        return None

    try:
        token_payload = validate_supabase_jwt(credentials.credentials)
        return User(id=token_payload.sub, email=token_payload.email)
    except HTTPException:
        return None


def get_current_user_or_anon(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """
    Get current user from JWT, allowing anonymous Supabase users.

    - If DEV_USER_ID is set: return mock user
    - If valid JWT with 'is_anonymous' claim: return anonymous user
    - If valid JWT without 'is_anonymous': return regular user
    - If no token: raise 401
    """
    settings = get_settings()

    if settings.dev_user_id:
        return User(id=settings.dev_user_id, email="dev@local.test", is_anonymous=False)

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = validate_supabase_jwt(credentials.credentials)
    return User(
        id=token_payload.sub,
        email=token_payload.email,
        is_anonymous=token_payload.is_anonymous,
    )
