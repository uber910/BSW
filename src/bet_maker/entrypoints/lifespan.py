from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
import structlog
from fastapi import FastAPI
from faststream.rabbit.schemas import ExchangeType, RabbitExchange, RabbitQueue

from bet_maker.entrypoints.messaging import router as rabbit_router
from bet_maker.entrypoints.messaging import set_sessionmaker
from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker
from bet_maker.infrastructure.db.pings import wait_for_postgres
from bet_maker.jobs.reconciler import reconciliation_loop
from bet_maker.settings.config import BetMakerSettings
from config.logging import configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """bet_maker lifespan.

    Strict startup order (no asyncio.gather parallel steps):
      1. configure_structlog
      2. create engine + sessionmaker
      3. wait_for_postgres (tenacity)
      4. httpx.AsyncClient singleton
      5. router.broker.connect()  -- required because custom lifespan
      6. declare DLX exchange + DLQ queue + bind DLQ to DLX
      7. set_sessionmaker on messaging module (handler dependency)
      8. app.state pins
      9. yield

    Shutdown reverse order with nested try/finally:
      router.broker.close() -> http_client.aclose() -> engine.dispose()
      Each step runs even if the prior one raises.

    No intermediate "starting" state — uvicorn does not open the
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
    app.state.reconciler_event_lookup = HttpEventLookup(
        http_client=http_client,
        attempts=settings.line_provider_reconciler_attempts,
        max_backoff=settings.line_provider_reconciler_backoff_max_s,
    )

    reconciliation_task: asyncio.Task[None] = asyncio.create_task(
        reconciliation_loop(app, interval_s=settings.reconciliation_interval_s),
        name="reconciliation",
    )
    app.state.reconciliation_task = reconciliation_task

    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
        reconciliation_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconciliation_task
        try:
            await rabbit_router.broker.close()
        finally:
            try:
                await http_client.aclose()
            finally:
                await engine.dispose()
