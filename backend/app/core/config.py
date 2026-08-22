"""Application configuration. All secrets come from the environment."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )

    # --- app ---
    APP_NAME: str = "ProspectIQ AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- database ---
    DATABASE_URL: str = "postgresql+psycopg://postgres:password@localhost:5432/prospectiq"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- redis / celery ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # --- security ---
    SECRET_KEY: str = "dev-only-insecure-change-me"
    # Fernet key used to encrypt provider API keys at rest.
    # Derived from SECRET_KEY when left blank so development needs no extra config.
    ENCRYPTION_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # --- bootstrap admin (created by the seeder on first run) ---
    SEED_ADMIN_EMAIL: str = ""
    SEED_ADMIN_PASSWORD: str = ""
    SEED_ADMIN_NAME: str = "Platform Administrator"
    SEED_ORG_NAME: str = "ProspectIQ"

    # --- llm providers (optional; features degrade gracefully when absent) ---
    ANTHROPIC_API_KEY: str = ""
    LLM_CHEAP_MODEL: str = "claude-haiku-4-5"
    LLM_SMART_MODEL: str = "claude-opus-5"
    LLM_MAX_OUTPUT_TOKENS: int = 4096
    LLM_ENABLED: bool = True

    # --- discovery connectors (optional) ---
    SERPER_API_KEY: str = ""
    GOOGLE_CSE_KEY: str = ""
    GOOGLE_CSE_CX: str = ""
    SEARXNG_URL: str = ""
    ENABLE_DUCKDUCKGO: bool = True
    ENABLE_OPENSTREETMAP: bool = True

    # --- crawling ---
    HTTP_USER_AGENT: str = "ProspectIQ-AI/1.0 (+https://prospectiq.ai/bot)"
    HTTP_TIMEOUT_SECONDS: float = 20.0
    CRAWL_MAX_PAGES_PER_SITE: int = 12
    CRAWL_DELAY_SECONDS: float = 1.0
    RESPECT_ROBOTS_TXT: bool = True
    ENABLE_PLAYWRIGHT: bool = False

    # --- cost guardrails ---
    MAX_COMPANIES_PER_JOB: int = 250
    DEFAULT_CAMPAIGN_BUDGET_USD: float = 25.0

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_driver(cls, v: str) -> str:
        # psycopg3 is the installed driver; accept plain postgres URLs too.
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @property
    def broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
