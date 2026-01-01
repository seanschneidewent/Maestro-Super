from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import Base and all models to ensure they're registered
from app.database.base import Base
from app.models import (  # noqa: F401
    Discipline,
    Page,
    Pointer,
    PointerReference,
    Project,
    Query,
    UsageEvent,
)

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate support
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from environment or config."""
    import os
    from urllib.parse import quote_plus

    # Try DATABASE_URL environment variable first
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # Try building from separate DB_* variables (Railway style)
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME", "postgres")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD")
    db_port = os.getenv("DB_PORT", "5432")

    if db_host and db_password:
        # URL-encode the password to handle special characters
        encoded_password = quote_plus(db_password)
        return f"postgresql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"

    # Fall back to alembic.ini
    return config.get_main_option("sqlalchemy.url", "sqlite:///./local.db")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Override sqlalchemy.url with our URL
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Detect if we're using SQLite
        is_sqlite = connection.dialect.name == "sqlite"

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,  # Only use batch mode for SQLite
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
