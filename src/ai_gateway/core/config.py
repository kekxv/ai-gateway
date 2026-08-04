from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway"
    database_pool_size: int = Field(default=20, ge=1)
    database_max_overflow: int = Field(default=20, ge=0)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0)
    database_pool_recycle_seconds: int = Field(default=1800, ge=1)
    jwt_secret: SecretStr
    jwt_issuer: str = "ai-gateway"
    jwt_access_minutes: int = 60
    jwt_refresh_days: int = 30
    encryption_key: SecretStr
    http_proxy: str | None = Field(default=None, repr=False)
    https_proxy: str | None = Field(default=None, repr=False)
    no_proxy: str = "127.0.0.1,localhost"
    route_failure_threshold: int = Field(default=10, ge=1)
    route_cooldown_seconds: int = Field(default=60, ge=1)
    model_sync_interval_seconds: int = Field(default=3600, ge=1)
    audit_body_limit_bytes: int = 1_048_576
    billing_default_max_output_tokens: int = Field(default=4096, ge=1)
    billing_recovery_interval_seconds: int = Field(default=60, ge=1)
    billing_reservation_ttl_seconds: int = Field(default=300, ge=60)
    audit_log_retention_days: int = Field(default=30, ge=0)
    audit_log_cleanup_interval_seconds: int = Field(default=3600, ge=60)
    auth_rate_limit_max_requests: int = Field(default=5, ge=1)
    auth_rate_limit_window_seconds: int = Field(default=300, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
