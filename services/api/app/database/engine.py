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

    # Postgres-specific connection args (keepalives, timeouts)
    # Only apply for PostgreSQL - SQLite doesn't support these
    is_postgres = settings.db_host or (
        settings.database_url and "postgresql" in str(settings.database_url)
    )

    connect_args = {}
    if is_postgres:
        connect_args = {
            "connect_timeout": 10,      # 10s connection timeout
            "keepalives": 1,            # Enable TCP keepalives
            "keepalives_idle": 30,      # Start keepalives after 30s idle
            "keepalives_interval": 10,  # Send keepalive every 10s
            "keepalives_count": 5,      # Drop after 5 failed keepalives
        }

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,  # Recycle connections every 5 min to prevent stale state
        pool_size=10,       # Increased from 5 to handle concurrent requests
        max_overflow=20,    # Increased from 10 for burst capacity
        pool_timeout=10,    # Wait max 10s for connection from pool
        connect_args=connect_args,
        echo=False,
    )


# Default engine instance
engine = get_engine()


def is_postgres() -> bool:
    """Check if the database is PostgreSQL (always True now)."""
    return True
