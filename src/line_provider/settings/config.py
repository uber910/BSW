from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from config.settings_base import BaseAppSettings


class LineProviderSettings(BaseAppSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LINE_PROVIDER_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(default="line-provider")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    rabbitmq_url: str = Field(default="amqp://guest:guest@rabbitmq:5672/")
