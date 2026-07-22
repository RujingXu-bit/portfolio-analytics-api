from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = (
        "postgresql+asyncpg://portfolio:portfolio_local_only@localhost:55432/portfolio"
    )
    test_database_url: str = (
        "postgresql+asyncpg://portfolio_test:portfolio_test_local_only"
        "@localhost:55433/portfolio_test"
    )
    redis_url: str = "redis://localhost:6379/0"
    default_base_currency: str = Field(default="USD", min_length=3, max_length=3)


@lru_cache
def get_settings() -> Settings:
    return Settings()
