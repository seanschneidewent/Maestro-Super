from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database - can use either DATABASE_URL or separate params
    database_url: str | None = None

    # Separate DB params (for passwords with special characters)
    db_host: str | None = None
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str | None = None
    db_name: str = "postgres"

    # Auth - dev mode bypass
    dev_user_id: str | None = None  # Set this to bypass JWT auth in local dev

    # Supabase Auth (production)
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None
    supabase_service_key: str | None = None

    # AI Services (for later phases)
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None

    # CORS - production frontend URL
    frontend_url: str | None = None  # Set to Vercel URL in production

    @property
    def is_dev_mode(self) -> bool:
        """Check if running in dev mode with auth bypass."""
        return self.dev_user_id is not None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
