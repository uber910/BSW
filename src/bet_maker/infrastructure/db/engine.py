from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bet_maker.settings.config import BetMakerSettings


def create_engine_and_sessionmaker(
    settings: BetMakerSettings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build the AsyncEngine + async_sessionmaker singletons for bet_maker.

    pool_size=10, max_overflow=20 — enough headroom for the test-task
    workload without exhausting PG.
    pool_pre_ping=True — issues SELECT 1 on checkout, kills stale connections
    in idle pools (avoids "connection closed" after PG restart).
    pool_recycle=1800 — refresh connections every 30 min (defensive against
    cloud PG forcing disconnects on long-idle clients).

    expire_on_commit=False — without this, any access to ORM attributes
    after commit raises MissingGreenlet (the async session would try to
    lazy-reload, which requires greenlet). Tests + place_bet interactor
    rely on this contract.
    """
    engine = create_async_engine(
        str(settings.postgres_dsn),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return engine, sessionmaker
