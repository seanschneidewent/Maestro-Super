from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Model Constants
# Centralized model names to avoid hardcoding throughout the codebase.
# ---------------------------------------------------------------------------
BRAIN_MODE_MODEL = "gemini-3-flash-preview"
BRAIN_MODE_THINKING_LEVEL = "high"
USE_AGENTIC_VISION = True
QUERY_VISION_MODEL = "gemini-2.0-flash"
AGENT_QUERY_MODEL = "gemini-3-flash-preview"
FAST_ROUTER_MODEL = "gemma-3-4b-it"

# V3 Shell models
MAESTRO_MODEL = "gemini-3-flash-preview"
LEARNING_MODEL = "gemini-3-flash-preview"

# V3 Pass 2 Enrichment
PASS2_MODEL = BRAIN_MODE_MODEL  # Same model as Brain Mode by default


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
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
    openrouter_api_key: str | None = None  # For Kimi K2 query agent
    voyage_api_key: str | None = None

    # Brain Mode - Agentic Vision
    brain_mode_model: str = BRAIN_MODE_MODEL
    brain_mode_thinking_level: str = BRAIN_MODE_THINKING_LEVEL
    use_agentic_vision: bool = USE_AGENTIC_VISION
    fast_router_model: str = FAST_ROUTER_MODEL

    # V3 Shell models
    maestro_model: str = MAESTRO_MODEL
    learning_model: str = LEARNING_MODEL

    # V3 Pass 2 Enrichment
    pass2_model: str = PASS2_MODEL
    pass2_max_concurrent: int = 3
    pass2_poll_interval: float = 5.0  # seconds between poll cycles

    # CORS - production frontend URL
    frontend_url: str | None = None  # Set to Vercel URL in production

    # Rate Limiting
    max_requests_per_day: int = 1000
    max_tokens_per_day: int = 5000000  # 5 million
    max_pointers_per_project: int = 1000

    # Demo Project (for anonymous landing page demo)
    demo_project_id: str | None = None

    # Telegram Bot
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_default_project_id: str | None = None  # v1 shortcut for single-project

    # Heartbeat System
    heartbeat_enabled: bool = False
    heartbeat_schedule: str = "06:30,12:00"  # comma-separated HH:MM
    heartbeat_timezone: str = "America/Chicago"

    # Benchmark System (Phase 7)
    benchmark_enabled: bool = True  # Log all interactions for emergent scoring

    @property
    def is_dev_mode(self) -> bool:
        """Check if running in dev mode with auth bypass."""
        return self.dev_user_id is not None

    @property
    def telegram_enabled(self) -> bool:
        """Check if Telegram bot is configured."""
        return self.telegram_bot_token is not None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
