from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cerebras_api_key: str = ""
    groq_api_key: str = ""
    sambanova_api_key: str = ""
    gemini_api_key: str = ""
    huggingface_api_key: str = ""
    mistral_api_key: str = ""
    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""

    cerebras_daily_requests: int = 5000
    cerebras_daily_tokens: int = 1_000_000
    groq_daily_requests: int = 14400
    groq_daily_tokens: int = 500_000
    sambanova_daily_requests: int = 1000
    sambanova_daily_tokens: int = 1_000_000
    gemini_daily_requests: int = 1500
    gemini_daily_tokens: int = 1_000_000
    huggingface_daily_requests: int = 1000
    huggingface_daily_tokens: int = 500_000
    mistral_daily_requests: int = 100
    mistral_daily_tokens: int = 200_000

    db_path: str = "data/freeai.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
