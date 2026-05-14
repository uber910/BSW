from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from config.logging import configure_structlog
from line_provider.settings.config import LineProviderSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = LineProviderSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("line_provider.startup", service=settings.service_name)
    app.state.settings = settings
    try:
        yield
    finally:
        log.info("line_provider.shutdown")
