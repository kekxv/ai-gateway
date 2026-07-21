from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "mysql+asyncmy://gateway:gateway@127.0.0.1:3306/gateway"
    jwt_secret: SecretStr
    jwt_issuer: str = "ai-gateway"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 30
    encryption_key: SecretStr
    http_proxy: str | None = Field(default=None, repr=False)
    https_proxy: str | None = Field(default=None, repr=False)
    no_proxy: str = "127.0.0.1,localhost"
    route_failure_threshold: int = 3
    route_cooldown_seconds: int = 60
    model_sync_interval_seconds: int = 3600
    audit_body_limit_bytes: int = 1_048_576


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
