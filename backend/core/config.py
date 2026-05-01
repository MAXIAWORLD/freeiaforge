from __future__ import annotations
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    cerebras_api_key: str = ""
    groq_api_key: str = ""
    sambanova_api_key: str = ""
    gemini_api_key: str = ""
    huggingface_api_key: str = ""
    mistral_api_key: str = ""
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

    db_path: str = "data/freeai.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
