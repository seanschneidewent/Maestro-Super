"""Rate limiting dependencies for FastAPI."""

import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_current_user_or_anon
from app.auth.schemas import User
from app.database.session import get_db
from app.services.usage import UsageService

logger = logging.getLogger(__name__)


def get_current_user_id(user: User = Depends(get_current_user)) -> str:
    """Extract user ID from authenticated user."""
    return user.id


async def check_rate_limit(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """
    Dependency that checks rate limits and raises 429 if exceeded.

    Use this in routes that need rate limiting:
        @router.post("/endpoint")
        async def endpoint(
            user: User = Depends(check_rate_limit),
            db: Session = Depends(get_db),
        ):
            ...

    Returns:
        The authenticated user if within limits

    Raises:
        HTTPException 429 if rate limited
    """
    allowed, error_info = UsageService.check_rate_limit(db, user.id)

    if not allowed:
        logger.warning(f"Rate limit exceeded for user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_info,
            headers={"Retry-After": str(error_info.get("retry_after", 3600))},
        )

    return user


async def check_rate_limit_or_anon(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_or_anon),
) -> User:
    """
    Rate limit check that allows anonymous users.
    Same logic as check_rate_limit but accepts anonymous JWT tokens.
    """
    allowed, error_info = UsageService.check_rate_limit(db, user.id)

    if not allowed:
        logger.warning(f"Rate limit exceeded for user {user.id} (anonymous={user.is_anonymous})")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_info,
            headers={"Retry-After": str(error_info.get("retry_after", 3600))},
        )

    return user


async def check_pointer_limit(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """
    Check if project is within pointer limit.

    Raises:
        HTTPException 400 if limit exceeded
    """
    allowed, error_info = UsageService.check_pointer_limit(db, user.id, project_id)

    if not allowed:
        logger.warning(f"Pointer limit exceeded for project {project_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_info,
        )
