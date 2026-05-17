from __future__ import annotations
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Gateway auth (optional — empty = disabled)
    freeai_api_key: str = ""

    cerebras_api_key: str = ""
    groq_api_key: str = ""
    sambanova_api_key: str = ""
    gemini_api_key: str = ""
    huggingface_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""
    nvidia_nim_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""

    cerebras_daily_requests: int = Field(default=5000, gt=0)
    cerebras_daily_tokens: int = Field(default=1_000_000, gt=0)
    groq_daily_requests: int = Field(default=14400, gt=0)
    groq_daily_tokens: int = Field(default=500_000, gt=0)
    sambanova_daily_requests: int = Field(default=1000, gt=0)
    sambanova_daily_tokens: int = Field(default=1_000_000, gt=0)
    gemini_daily_requests: int = Field(default=1500, gt=0)
    gemini_daily_tokens: int = Field(default=1_000_000, gt=0)
    huggingface_daily_requests: int = Field(default=1000, gt=0)
    huggingface_daily_tokens: int = Field(default=500_000, gt=0)
    mistral_daily_requests: int = Field(default=100, gt=0)
    mistral_daily_tokens: int = Field(default=200_000, gt=0)
    openrouter_daily_requests: int = Field(default=200, gt=0)
    openrouter_daily_tokens: int = Field(default=500_000, gt=0)
    # NVIDIA NIM: 40 RPM, no hard daily cap → soft limit to protect quota tracking
    nvidia_nim_daily_requests: int = Field(default=10_000, gt=0)
    nvidia_nim_daily_tokens: int = Field(default=1_000_000, gt=0)
    # Cloudflare Workers AI: 10 000 req/j confirmed
    cloudflare_daily_requests: int = Field(default=10_000, gt=0)
    cloudflare_daily_tokens: int = Field(default=1_000_000, gt=0)

    # Ollama — local, no API key required
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_daily_requests: int = Field(default=10_000, gt=0)
    ollama_daily_tokens: int = Field(default=10_000_000, gt=0)

    # Provider order override (comma-separated names, e.g. "groq,gemini,ollama")
    provider_order: str = ""

    # Circuit breaker thresholds
    cb_failure_threshold: int = Field(default=3, gt=0)
    cb_timeout_seconds: int = Field(default=600, gt=0)
    cb_half_open_after: int = Field(default=300, gt=0)

    # providers.json remote URL (GitHub raw)
    providers_json_url: str = "https://raw.githubusercontent.com/MAXIAWORLD/freeiaforge/main/providers.json"

    db_path: str = "data/quota.db"
    stats_db_path: str = "data/stats.db"

    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=3600, gt=0)
    cache_similarity_threshold: float = Field(default=0.90, gt=0.0, le=1.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
