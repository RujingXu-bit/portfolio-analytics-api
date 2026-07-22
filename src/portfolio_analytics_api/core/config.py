from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = (
        "postgresql+asyncpg://portfolio:portfolio_local_only@localhost:55432/portfolio"
    )
    test_database_url: str = (
        "postgresql+asyncpg://portfolio_test:portfolio_test_local_only"
        "@localhost:55433/portfolio_test"
    )
    redis_url: str = "redis://localhost:6379/0"
    test_redis_url: str = "redis://localhost:56379/0"
    redis_connect_timeout_seconds: float = Field(default=1.0, gt=0)
    redis_read_timeout_seconds: float = Field(default=1.0, gt=0)
    market_data_request_timeout_seconds: float = Field(default=10.0, gt=0)
    market_data_operation_timeout_seconds: float = Field(default=12.0, gt=0)
    market_data_max_attempts: int = Field(default=3, ge=1)
    market_data_retry_backoff_seconds: float = Field(default=0.25, ge=0)
    market_data_mutable_ttl_seconds: int = Field(default=300, gt=0)
    market_data_historical_ttl_seconds: int = Field(default=86400, gt=0)
    market_data_stale_ttl_seconds: int = Field(default=604800, gt=0)
    default_base_currency: str = Field(default="USD", min_length=3, max_length=3)
    jwt_secret_key: SecretStr | None = Field(default=None, min_length=32)
    access_token_expire_minutes: int = Field(default=30, gt=0)
    rate_limit_enabled: bool = True
    rate_limit_trust_proxy_headers: bool = False
    rate_limit_hash_key: SecretStr | None = Field(default=None, min_length=32)
    rate_limit_namespace: str = Field(default="portfolio-analytics", min_length=1)
    rate_limit_registration_ip_limit: int = Field(default=5, gt=0)
    rate_limit_registration_window_seconds: int = Field(default=600, gt=0)
    rate_limit_login_ip_limit: int = Field(default=10, gt=0)
    rate_limit_login_email_limit: int = Field(default=5, gt=0)
    rate_limit_login_window_seconds: int = Field(default=600, gt=0)
    rate_limit_analytics_user_limit: int = Field(default=20, gt=0)
    rate_limit_insights_user_limit: int = Field(default=10, gt=0)
    rate_limit_authenticated_user_limit: int = Field(default=120, gt=0)
    rate_limit_authenticated_window_seconds: int = Field(default=60, gt=0)
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = Field(default="deepseek-v4-flash", min_length=1)
    deepseek_timeout_seconds: float = Field(default=8.0, gt=0)
    insight_cache_ttl_seconds: int = Field(default=86400, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
