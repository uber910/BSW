from __future__ import annotations

import logging

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger()
_stdlib_log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before_sleep=before_sleep_log(_stdlib_log, logging.WARNING),
)
async def wait_for_postgres(engine: AsyncEngine) -> None:
    """Block until PG accepts SELECT 1, or give up after 10 attempts.

    tenacity @retry automatically uses AsyncRetrying for coroutines.
    Cumulative wait ~1+2+4+8+10+10+10+10+10+10 = ~75s worst case before
    reraise. Lifespan calls this — if all 10 attempts fail, startup
    crashes with a clear OperationalError and structlog log.

    Surfaces bad DSN at startup, not at first request.
    """
    async with engine.connect() as conn:
        await conn.scalar(text("SELECT 1"))


async def ping_postgres(engine: AsyncEngine) -> bool:
    """Single SELECT 1 ping for /health — no retry, returns True/False.

    Per-request check (no caching at test-task scale). ~5ms overhead
    is fine; live 503 is critical for docker-compose healthcheck.
    SQLAlchemyError caught -> return False -> route emits 503.
    Bare Exception is NOT caught — non-SQLAlchemy errors should propagate
    and cause 500 (info disclosure risk to swallow them silently).
    """
    try:
        async with engine.connect() as conn:
            await conn.scalar(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        log.warning("health.check.failed", check="postgres", error=str(exc))
        return False
