"""Application settings, loaded from the environment only (12-factor)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    app_name: str = "TwinPM"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+asyncpg://twinpm:twinpm@localhost:5432/twinpm"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr = SecretStr("dev-only-change-me-0123456789abcdef0123456789")
    jwt_access_ttl_seconds: int = 15 * 60
    jwt_refresh_ttl_seconds: int = 7 * 24 * 3600
    cookie_secure: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3100"])
    fernet_key: SecretStr | None = None

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_model_orchestrator: str = "claude-opus-5-5"
    demo_mode: bool = False
    demo_live_ticks: bool = False
    llm_max_output_tokens: int = 2048
    llm_timeout_seconds: float = 60.0

    seed_demo_password: SecretStr = SecretStr("TwinPM-demo-2026!")
    models_dir: str = "models"
    otel_exporter_otlp_endpoint: str | None = None
    langsmith_tracing: bool = False

    rate_limit_ai_per_minute: int = 20
    rate_limit_auth_per_minute: int = 10

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_demo_mode(self) -> bool:
        """Demo mode is forced when no Anthropic key is configured."""
        key = self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else ""
        return self.demo_mode or not key


@lru_cache
def get_settings() -> Settings:
    return Settings()
