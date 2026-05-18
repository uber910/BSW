from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from faststream.rabbit.schemas import ExchangeType, RabbitExchange

from config.logging import configure_structlog
from line_provider.api.messaging import router as rabbit_router
from line_provider.facades.event_bus import RabbitEventBus
from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.settings.config import LineProviderSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """line-provider lifespan.

    Startup:
      1. configure_structlog
      2. router.broker.connect() (required with custom lifespan)
      3. declare bsw.events exchange (topic, durable) — bet-maker subscriber binds to this
      4. app.state.event_store = InMemoryEventStore()
      5. app.state.event_bus = RabbitEventBus(router.broker)
      6. yield

    Shutdown: router.broker.close().
    """
    settings = LineProviderSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("line_provider.startup", service=settings.service_name)

    await rabbit_router.broker.connect()
    await rabbit_router.broker.declare_exchange(
        RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
    )

    app.state.settings = settings
    app.state.event_store = InMemoryEventStore()
    app.state.event_bus = RabbitEventBus(rabbit_router.broker)

    try:
        yield
    finally:
        log.info("line_provider.shutdown")
        await rabbit_router.broker.close()
