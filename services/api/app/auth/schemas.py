"""Auth schemas for user and token data."""

from pydantic import BaseModel


class User(BaseModel):
    """Authenticated user information."""

    id: str
    email: str | None = None
    is_anonymous: bool = False


class TokenPayload(BaseModel):
    """JWT token payload from Supabase."""

    sub: str  # user_id
    email: str | None = None
    exp: int
    is_anonymous: bool = False
