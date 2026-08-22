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
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    # The vendor is inferred from the model id (claude-* -> Anthropic, gpt-*/o* ->
    # OpenAI, gemini-* -> Google), so a tier can be pointed at any vendor without
    # code changes.
    LLM_CHEAP_MODEL: str = "gemini-3.5-flash-lite"
    LLM_SMART_MODEL: str = "gemini-3.5-flash"
    # Failover chains, tried left to right. Free quotas are metered per model per
    # day, so listing several multiplies the daily free capacity: when one refuses
    # work the facade moves to the next instead of abandoning the run. Blank falls
    # back to the single model above.
    LLM_CHEAP_MODEL_CHAIN: str = (
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-lite-latest"
    )
    LLM_SMART_MODEL_CHAIN: str = "gemini-3.5-flash,gemini-3.7-flash,gemini-flash-latest"
    # Local ceiling per model per UTC day. 0 means "spend until the provider says
    # no", which is right for a free tier with undocumented limits.
    LLM_DAILY_CAP_PER_MODEL: int = 0
    LLM_MAX_OUTPUT_TOKENS: int = 4096
    # Prompts are truncated to this many characters before being sent. Crawled page
    # text is the only unbounded input, and its tail is boilerplate, so trimming it
    # cuts token spend hard without changing what the model concludes.
    LLM_MAX_PROMPT_CHARS: int = 12000
    LLM_ENABLED: bool = True
    # Hard spend guard. While true the facade refuses every model that has no
    # free tier, even when a paid key is present, and reports zero cost. An
    # exhausted free quota therefore degrades to the rules engine rather than
    # quietly moving the work onto a billed vendor. Set false only after
    # deliberately deciding to pay.
    LLM_FREE_TIER_ONLY: bool = True

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

    @staticmethod
    def _chain(raw: str, fallback: str) -> list[str]:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if fallback and fallback not in models:
            # The explicitly configured single model always leads the chain, so
            # setting LLM_CHEAP_MODEL keeps working exactly as it reads.
            models.insert(0, fallback)
        return models or ([fallback] if fallback else [])

    @property
    def cheap_model_chain(self) -> list[str]:
        return self._chain(self.LLM_CHEAP_MODEL_CHAIN, self.LLM_CHEAP_MODEL)

    @property
    def smart_model_chain(self) -> list[str]:
        return self._chain(self.LLM_SMART_MODEL_CHAIN, self.LLM_SMART_MODEL)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
