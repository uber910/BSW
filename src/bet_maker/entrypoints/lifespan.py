from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI

from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker
from bet_maker.infrastructure.db.pings import wait_for_postgres
from bet_maker.settings.config import BetMakerSettings
from config.logging import configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """bet_maker lifespan: configure logging, start DB engine, wait for PG,
    create singleton httpx client, wire HttpEventLookup, then yield.

    D-13 / D-14: app.state.event_lookup = HttpEventLookup (replaces P3
    StubEventLookup). Tests override per-test via the autouse
    _clear_event_lookup fixture in tests/bet_maker/conftest.py.
    D-19 startup order: structlog -> engine+sessionmaker -> wait_for_postgres
    -> httpx.AsyncClient(Timeout(5.0)) -> app.state pins.
    D-20 shutdown order: http_client.aclose() BEFORE engine.dispose()
    (reverse of startup; Pitfall 6 mitigation).
    D-27: wait_for_postgres -- tenacity 10 attempts, exponential backoff;
    bad DSN crashes startup with clear log (Pitfall D2 mitigation).
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
        timeout=httpx.Timeout(5.0),  # D-02: explicit total timeout, Pitfall 1
    )

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
        # D-20 reverse-order shutdown: close httpx pool BEFORE disposing
        # the DB engine. try/finally ensures dispose runs even if aclose
        # raises (Pitfall 6 mitigation).
        try:
            await http_client.aclose()
        finally:
            await engine.dispose()
