"""
Application configuration via pydantic-settings.

Reads from environment variables (and optionally a .env file).
All configuration is centralised here — no other module should read env vars directly.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    RestockIQ application configuration.

    All fields have reasonable defaults so the application runs out-of-the-box
    in development without a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://restockiq:password@localhost:5432/restockiq"
    )

    # ── WERET Integration ─────────────────────────────────────────────────────
    weret_base_url: str = "http://localhost:3000"
    weret_api_key: str = ""
    weret_webhook_secret: str = ""

    # ── Application ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    app_env: str = "development"
    secret_key: str = "change-me-in-production"

    # ── Solver tuning ─────────────────────────────────────────────────────────
    saa_n_scenarios: int = 200
    saa_seed: int | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env.lower() in ("testing", "test")

    @property
    def db_echo(self) -> bool:
        """Log SQL in development; suppress in production."""
        return self.app_env.lower() == "development"
