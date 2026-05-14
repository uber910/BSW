from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(
        ...,
        description="Logical service name for logs and OpenAPI title",
    )
    log_level: str = Field(
        default="INFO",
        description="Root log level: DEBUG / INFO / WARNING / ERROR",
    )
