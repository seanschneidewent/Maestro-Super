"""Database session management with RLS context support."""

import json
from collections.abc import Generator
from typing import Any

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.auth.schemas import User
from app.database.engine import get_engine, is_postgres

# Session factory
SessionLocal = sessionmaker(
    bind=get_engine(),
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, Any, None]:
    """
    FastAPI dependency that yields a database session.

    Note: This is for unauthenticated routes. For authenticated routes,
    use get_db_with_rls which sets up RLS context.

    Usage:
        @app.get("/health")
        def health_check(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_with_rls(user: User) -> Generator[Session, Any, None]:
    """
    Get a database session with RLS context set for the user.

    On PostgreSQL: Sets request.jwt.claims so RLS policies can access user_id
    On SQLite: No-op (RLS not supported)

    Args:
        user: The authenticated user

    Usage:
        @app.get("/projects")
        def get_projects(
            user: User = Depends(get_current_user),
            db: Session = Depends(lambda: get_db_with_rls(user))
        ):
            ...

    Note: The standard pattern is to use get_authenticated_db() instead,
    which combines auth + db in one dependency.
    """
    db = SessionLocal()
    try:
        # Set RLS context on Postgres
        if is_postgres():
            db.execute(
                text("SET LOCAL request.jwt.claims = :claims"),
                {"claims": json.dumps({"sub": user.id})},
            )
        yield db
    finally:
        db.close()


def get_authenticated_db(user: User = Depends("app.auth.dependencies:get_current_user")):
    """
    Combined dependency for authenticated routes with RLS context.

    This is the standard dependency for authenticated routes:
    - Validates JWT (or uses dev bypass)
    - Creates session with RLS context set

    Usage:
        from app.database.session import get_authenticated_db
        from app.auth import User

        @app.get("/projects")
        def get_projects(user: User, db: Session = Depends(get_authenticated_db)):
            # user is authenticated
            # db has RLS context set
            ...

    Note: This is defined as a factory to avoid circular imports.
    Import and use create_authenticated_db_dependency() in your router.
    """
    # This is a placeholder - actual implementation below


def create_authenticated_db_dependency():
    """
    Factory to create the authenticated DB dependency.

    Call this once in your app setup to avoid circular imports.

    Usage:
        # In main.py or router
        from app.database.session import create_authenticated_db_dependency
        get_authenticated_db = create_authenticated_db_dependency()

        @app.get("/projects")
        def get_projects(db: Session = Depends(get_authenticated_db)):
            ...
    """
    from app.auth.dependencies import get_current_user

    def _get_authenticated_db(
        user: User = Depends(get_current_user),
    ) -> Generator[Session, Any, None]:
        """Yield database session with RLS context for authenticated user."""
        db = SessionLocal()
        try:
            # Set RLS context on Postgres
            if is_postgres():
                db.execute(
                    text("SET LOCAL request.jwt.claims = :claims"),
                    {"claims": json.dumps({"sub": user.id})},
                )
            yield db
        finally:
            db.close()

    return _get_authenticated_db
