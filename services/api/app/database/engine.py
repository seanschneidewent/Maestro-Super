from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create and cache the database engine."""
    settings = get_settings()
    url = settings.database_url

    # SQLite-specific settings
    if url.startswith("sqlite"):
        return create_engine(
            url,
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
