from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from faststream.rabbit.schemas import ExchangeType, RabbitExchange, RabbitQueue

from bet_maker.entrypoints.messaging import router as rabbit_router
from bet_maker.entrypoints.messaging import set_sessionmaker
from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker
from bet_maker.infrastructure.db.pings import wait_for_postgres
from bet_maker.settings.config import BetMakerSettings
from config.logging import configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """bet_maker lifespan (Plan 05-07 / D-21).

    Strict startup order (F3 — no asyncio.gather parallel steps):
      1. configure_structlog
      2. create engine + sessionmaker
      3. wait_for_postgres (tenacity)
      4. httpx.AsyncClient singleton
      5. router.broker.connect()  -- Pitfall 2: required because custom lifespan
      6. declare DLX exchange + DLQ queue + bind DLQ to DLX (Pitfall 4)
      7. set_sessionmaker on messaging module (handler dependency)
      8. app.state pins
      9. yield

    Shutdown reverse order with nested try/finally (D-20 Pitfall 6):
      router.broker.close() -> http_client.aclose() -> engine.dispose()
      Each step runs even if the prior one raises.

    D-22: no intermediate "starting" state — uvicorn does not open the
    listening socket until this startup completes.
    """
    settings = BetMakerSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("bet_maker.startup", service=settings.service_name)

    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    try:
        await wait_for_postgres(engine)
    except Exception as exc:
        log.critical("bet_maker.startup.failed", reason=str(exc))
        await engine.dispose()
        raise

    http_client = httpx.AsyncClient(
        base_url=str(settings.line_provider_base_url),
        timeout=httpx.Timeout(5.0),
    )

    await rabbit_router.broker.connect()

    await rabbit_router.broker.declare_exchange(
        RabbitExchange("bsw.events.dlx", type=ExchangeType.DIRECT, durable=True)
    )
    dlq = await rabbit_router.broker.declare_queue(
        RabbitQueue("bet_maker.events.finished.dlq", durable=True)
    )
    await dlq.bind(
        exchange="bsw.events.dlx",
        routing_key="bet_maker.events.finished",
    )

    set_sessionmaker(sessionmaker)

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.line_provider_http_client = http_client
    app.state.event_lookup = HttpEventLookup(
        http_client=http_client,
        attempts=settings.line_provider_http_attempts,
        max_backoff=settings.line_provider_http_backoff_max_s,
    )

    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
        try:
            await rabbit_router.broker.close()
        finally:
            try:
                await http_client.aclose()
            finally:
                await engine.dispose()
