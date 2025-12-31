from functools import lru_cache
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create and cache the database engine."""
    settings = get_settings()

    # SQLite-specific settings
    if settings.database_url and settings.database_url.startswith("sqlite"):
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )

    # PostgreSQL - use separate params to handle special chars in password
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
        # Fallback to DATABASE_URL (may fail with special chars)
        url = settings.database_url
    else:
        # Default to SQLite
        return create_engine(
            "sqlite:///./local.db",
            connect_args={"check_same_thread": False},
            echo=False,
        )

    # PostgreSQL settings
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
    """Check if the database is PostgreSQL."""
    return get_engine().dialect.name == "postgresql"
