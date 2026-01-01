from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create and cache the database engine (PostgreSQL only)."""
    settings = get_settings()

    # Use separate params to handle special chars in password
    if settings.db_host:
        url = URL.create(
            drivername="postgresql",
            username=settings.db_user,
            password=settings.db_password,  # SQLAlchemy handles encoding
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
        )
    elif settings.database_url:
        # Fallback to DATABASE_URL
        url = settings.database_url
    else:
        raise ValueError(
            "Database not configured. Set DB_HOST or DATABASE_URL environment variable."
        )

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


# Default engine instance
engine = get_engine()


def is_postgres() -> bool:
    """Check if the database is PostgreSQL (always True now)."""
    return True
