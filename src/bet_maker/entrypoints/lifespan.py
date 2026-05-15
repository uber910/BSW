from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from bet_maker.facades.event_lookup import StubEventLookup
from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker
from bet_maker.infrastructure.db.pings import wait_for_postgres
from bet_maker.settings.config import BetMakerSettings
from config.logging import configure_structlog


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """bet_maker lifespan: configure logging, start DB engine, wait for PG.

    D-13: app.state.event_lookup = StubEventLookup() (Plan 04 swaps to
    HttpEventLookup without touching this function — same Protocol structurally).
    D-27: await wait_for_postgres(engine) — tenacity 10 attempts, exponential
    backoff; bad DSN crashes startup with clear log (Pitfall D2 mitigation).
    D-15/D-16: engine + sessionmaker created via create_engine_and_sessionmaker.

    Shutdown: await engine.dispose() in finally — release pool connections.
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

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.event_lookup = StubEventLookup()

    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
        await engine.dispose()
