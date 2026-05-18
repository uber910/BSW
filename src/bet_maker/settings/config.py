from __future__ import annotations

from pydantic import AmqpDsn, Field, HttpUrl, PostgresDsn
from pydantic_settings import SettingsConfigDict

from config.settings_base import BaseAppSettings


class BetMakerSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BET_MAKER_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(default="bet-maker")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001, ge=1, le=65535)

    postgres_dsn: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://bsw:bsw@postgres:5432/bsw"),
    )
    rabbitmq_url: AmqpDsn = Field(
        default=AmqpDsn("amqp://guest:guest@rabbitmq:5672/"),
    )
    line_provider_base_url: HttpUrl = Field(
        default=HttpUrl("http://line-provider:8000"),
    )
    line_provider_http_attempts: int = Field(default=3, ge=1, le=10)
    line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)
    line_provider_reconciler_attempts: int = Field(default=5, ge=1, le=10)
    line_provider_reconciler_backoff_max_s: float = Field(default=10.0, gt=0)
    reconciliation_interval_s: float = Field(default=30.0, gt=0)
