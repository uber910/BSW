"""Unit tests for bet_maker.infrastructure.db.engine + pings.

``create_engine_and_sessionmaker`` returns engine + sessionmaker with
locked params (pool_size=10, max_overflow=20, pool_pre_ping=True,
pool_recycle=1800, expire_on_commit=False). ``ping_postgres`` returns
True on healthy PG, False on ``SQLAlchemyError``; never raises.

Note on asyncpg + OSError: a real connection-refused attempt against a
non-routable port raises asyncpg's ConnectionRefusedError (an OSError subclass)
which is NOT wrapped by SQLAlchemy into OperationalError in SQLAlchemy 2.0.49.
To cleanly test the SQLAlchemyError->False contract without relying on
asyncpg wrapping behaviour, we use ``unittest.mock`` to inject
``SQLAlchemyError`` directly into the connect path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from pydantic import PostgresDsn
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
)
from sqlalchemy.pool.impl import QueuePool

from bet_maker.infrastructure.db.engine import create_engine_and_sessionmaker
from bet_maker.infrastructure.db.pings import ping_postgres
from bet_maker.settings.config import BetMakerSettings


class TestCreateEngineAndSessionmaker:
    """Engine + sessionmaker built with locked params."""

    def test_returns_engine_and_sessionmaker_tuple(self, pg_dsn: str) -> None:
        """Factory returns 2-tuple (AsyncEngine, async_sessionmaker)."""
        settings = BetMakerSettings(postgres_dsn=PostgresDsn(pg_dsn))
        engine, maker = create_engine_and_sessionmaker(settings)
        try:
            assert isinstance(engine, AsyncEngine)
            assert isinstance(maker, async_sessionmaker)
        finally:
            pass

    async def test_sessionmaker_has_expire_on_commit_false(self, pg_dsn: str) -> None:
        """Sessionmaker MUST be expire_on_commit=False."""
        settings = BetMakerSettings(postgres_dsn=PostgresDsn(pg_dsn))
        engine, maker = create_engine_and_sessionmaker(settings)
        try:
            async with maker() as session:
                assert session.sync_session.expire_on_commit is False
        finally:
            await engine.dispose()

    async def test_engine_pool_params_locked(self, pg_dsn: str) -> None:
        """pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800."""
        settings = BetMakerSettings(postgres_dsn=PostgresDsn(pg_dsn))
        engine, _ = create_engine_and_sessionmaker(settings)
        try:
            pool = engine.pool
            assert isinstance(pool, QueuePool)
            assert pool.size() == 10, f"expected pool_size=10, got {pool.size()}"
            assert pool._max_overflow == 20, pool._max_overflow
            assert pool._recycle == 1800, pool._recycle
            assert pool._pre_ping is True
        finally:
            await engine.dispose()


class TestPingPostgres:
    """ping_postgres contract."""

    async def test_ping_returns_true_on_healthy_engine(self, pg_dsn: str) -> None:
        """Healthy PG (testcontainers) — SELECT 1 succeeds -> True.

        Uses a function-scoped engine to avoid loop-mismatch with the
        session-scoped async_engine fixture (asyncio_default_test_loop_scope=function
        means each test gets its own loop; a session-scoped asyncpg connection
        created in the session loop cannot be reused across loop boundaries).
        """
        settings = BetMakerSettings(postgres_dsn=PostgresDsn(pg_dsn))
        engine, _ = create_engine_and_sessionmaker(settings)
        try:
            result = await ping_postgres(engine)
            assert result is True
        finally:
            await engine.dispose()

    async def test_ping_returns_false_on_sqlalchemy_error(self, async_engine: AsyncEngine) -> None:
        """SQLAlchemyError from connect -> False (NOT raise).

        Injects OperationalError via mock so the test is independent of
        asyncpg's error-wrapping behaviour across SQLAlchemy patch versions.
        ping_postgres catches SQLAlchemyError -> returns False without raising.

        Uses AsyncMock engine stub — AsyncEngine.connect is read-only on the
        instance, so we build a minimal mock rather than patching the instance.
        """
        exc = OperationalError("statement", {}, Exception("pg down"))

        @asynccontextmanager
        async def _fail_connect() -> AsyncIterator[AsyncConnection]:
            raise exc
            yield  # pragma: no cover — unreachable, satisfies type checker

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_engine.connect.side_effect = _fail_connect

        result = await ping_postgres(mock_engine)
        assert result is False
