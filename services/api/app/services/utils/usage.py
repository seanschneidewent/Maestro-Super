"""Usage tracking and rate limiting service."""

import logging
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.pointer import Pointer
from app.models.user_usage import UserUsage

logger = logging.getLogger(__name__)
settings = get_settings()


class UsageService:
    """Service for tracking and checking usage limits."""

    @staticmethod
    def get_or_create_daily_usage(db: Session, user_id: str) -> UserUsage:
        """Get or create today's usage record for a user."""
        today = date.today()

        usage = (
            db.query(UserUsage)
            .filter(UserUsage.user_id == user_id, UserUsage.date == today)
            .first()
        )

        if not usage:
            usage = UserUsage(user_id=user_id, date=today)
            db.add(usage)
            db.commit()
            db.refresh(usage)

        return usage

    @staticmethod
    def check_rate_limit(
        db: Session, user_id: str
    ) -> tuple[bool, Optional[dict]]:
        """
        Check if user is within rate limits.

        Returns:
            (allowed, error_info) where error_info is None if allowed,
            or a dict with limit details if denied.
        """
        usage = UsageService.get_or_create_daily_usage(db, user_id)

        # Check request limit
        if usage.requests_count >= settings.max_requests_per_day:
            return False, {
                "detail": "Daily request limit exceeded. Resets at midnight UTC.",
                "error_type": "rate_limit",
                "limits": {
                    "requests": {
                        "used": usage.requests_count,
                        "max": settings.max_requests_per_day,
                    },
                    "tokens": {
                        "used": usage.tokens_used,
                        "max": settings.max_tokens_per_day,
                    },
                },
                "retry_after": UsageService._seconds_until_midnight(),
            }

        # Check token limit
        if usage.tokens_used >= settings.max_tokens_per_day:
            return False, {
                "detail": "Daily token limit exceeded. Resets at midnight UTC.",
                "error_type": "rate_limit",
                "limits": {
                    "requests": {
                        "used": usage.requests_count,
                        "max": settings.max_requests_per_day,
                    },
                    "tokens": {
                        "used": usage.tokens_used,
                        "max": settings.max_tokens_per_day,
                    },
                },
                "retry_after": UsageService._seconds_until_midnight(),
            }

        return True, None

    @staticmethod
    def check_pointer_limit(
        db: Session, user_id: str, project_id: str
    ) -> tuple[bool, Optional[dict]]:
        """
        Check if project is within pointer limit.

        Returns:
            (allowed, error_info)
        """
        from app.models.discipline import Discipline
        from app.models.page import Page

        # Count pointers in project through disciplines -> pages -> pointers
        pointer_count = (
            db.query(func.count(Pointer.id))
            .join(Page, Pointer.page_id == Page.id)
            .join(Discipline, Page.discipline_id == Discipline.id)
            .filter(Discipline.project_id == project_id)
            .scalar()
        )

        if pointer_count >= settings.max_pointers_per_project:
            return False, {
                "detail": f"Project pointer limit ({settings.max_pointers_per_project}) reached.",
                "error_type": "limit_exceeded",
                "limits": {
                    "pointers": {
                        "used": pointer_count,
                        "max": settings.max_pointers_per_project,
                    },
                },
            }

        return True, None

    @staticmethod
    def increment_request(db: Session, user_id: str) -> None:
        """Increment the request counter for today."""
        usage = UsageService.get_or_create_daily_usage(db, user_id)
        usage.requests_count += 1
        db.commit()
        logger.debug(f"User {user_id} requests today: {usage.requests_count}")

    @staticmethod
    def increment_tokens(db: Session, user_id: str, tokens: int) -> None:
        """Increment the token counter for today."""
        usage = UsageService.get_or_create_daily_usage(db, user_id)
        usage.tokens_used += tokens
        db.commit()
        logger.debug(f"User {user_id} tokens today: {usage.tokens_used}")

    @staticmethod
    def increment_pointers(db: Session, user_id: str, count: int = 1) -> None:
        """Increment the pointer counter for today."""
        usage = UsageService.get_or_create_daily_usage(db, user_id)
        usage.pointers_created += count
        db.commit()
        logger.debug(f"User {user_id} pointers today: {usage.pointers_created}")

    @staticmethod
    def get_usage_summary(db: Session, user_id: str) -> dict:
        """Get current usage summary for a user."""
        usage = UsageService.get_or_create_daily_usage(db, user_id)
        return {
            "date": str(usage.date),
            "requests": {
                "used": usage.requests_count,
                "max": settings.max_requests_per_day,
                "remaining": max(0, settings.max_requests_per_day - usage.requests_count),
            },
            "tokens": {
                "used": usage.tokens_used,
                "max": settings.max_tokens_per_day,
                "remaining": max(0, settings.max_tokens_per_day - usage.tokens_used),
            },
            "pointers": {
                "created_today": usage.pointers_created,
            },
        }

    @staticmethod
    def _seconds_until_midnight() -> int:
        """Calculate seconds until midnight UTC."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Add one day to get next midnight
        from datetime import timedelta

        next_midnight = midnight + timedelta(days=1)
        return int((next_midnight - now).total_seconds())
