from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from bet_maker.settings.config import BetMakerSettings
from config.logging import configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = BetMakerSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("bet_maker.startup", service=settings.service_name)
    app.state.settings = settings
    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
