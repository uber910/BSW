"""Root conftest. PG-backed fixtures for Phase 3+ (testcontainers + Alembic)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
from testcontainers.rabbitmq import RabbitMqContainer  # type: ignore[import-untyped]


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Session-scoped PostgreSQL 16 container.

    QA-07: real PostgreSQL via testcontainers (not SQLite — would miss
    FOR UPDATE SKIP LOCKED behaviour in P5).
    D-21: PostgresContainer('postgres:16-alpine', driver='asyncpg').
    Built-in ExecWaitStrategy (psql SELECT 1 inside the container) waits
    for readiness — no manual sleep needed.
    """
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    """Connection URL for testcontainers PG. Format: postgresql+asyncpg://..."""
    return str(postgres_container.get_connection_url())


@pytest.fixture(scope="session")
def apply_migrations(pg_dsn: str) -> None:
    """Run `alembic upgrade head` programmatically against testcontainers DSN.

    D-22: bootstrap schema via `alembic.command.upgrade` (no subprocess overhead).
    Success criterion #5: rerun must be idempotent — second call must be no-op.
    Pitfall 6: `set_main_option('sqlalchemy.url', ...)` overrides production
    DSN baked into env.py (alembic.ini has no sqlalchemy.url line, so the
    override is the single source of truth for test DSN).
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", pg_dsn)
    command.upgrade(alembic_cfg, "head")
    command.upgrade(alembic_cfg, "head")  # idempotency assertion


@pytest_asyncio.fixture(scope="session")
async def async_engine(pg_dsn: str, apply_migrations: None) -> AsyncIterator[AsyncEngine]:
    """Session-scoped AsyncEngine bound to migrated testcontainers PG.

    D-16: pool_pre_ping=True. pool_size and overflow not specified for tests
    (defaults suffice for ~30 sequential tests). Engine disposed at session end.
    """
    engine = create_async_engine(pg_dsn, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker:  # type: ignore[type-arg]
    """Session-scoped async_sessionmaker bound to async_engine.

    D-15: expire_on_commit=False — required to avoid MissingGreenlet on
    post-commit attribute access in tests that inspect bets after UoW exit.
    """
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def truncate_bets(async_engine: AsyncEngine) -> AsyncIterator[None]:
    """Per-test isolation via TRUNCATE — explicit, function-scoped.

    D-23: TRUNCATE bets RESTART IDENTITY CASCADE in teardown. NOT a savepoint
    rollback — tests exercising real COMMIT-based UoW (and P5 FOR UPDATE
    SKIP LOCKED) need actual transactions. Cost ~50-100ms per test, acceptable
    at test-task scale.

    autouse is declared in tests/bet_maker/conftest.py (scope-contained to
    bet_maker tests) to avoid pulling postgres_container for line_provider
    or health-check tests that do not touch the bets table.
    """
    yield
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("TRUNCATE bets RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    """Session-scoped RabbitMQ 4.2 container for e2e + lifespan integration tests.

    QA-06 / D-31: real RabbitMQ via testcontainers — TestRabbitBroker alone
    misses topology bugs (F6). Image matches docker-compose.yml line-provider
    and bet-maker production target.
    Built-in readiness probe uses pika.BlockingConnection (pika is dev-dep).
    """
    with RabbitMqContainer("rabbitmq:4.2-management-alpine") as rmq:
        yield rmq


@pytest.fixture(scope="session")
def amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    """AMQP URL of the running testcontainers RabbitMQ.

    Used by e2e tests and line_provider/bet_maker lifespan tests that
    env-poke BET_MAKER_RABBITMQ_URL / LINE_PROVIDER_RABBITMQ_URL.
    """
    host = rabbitmq_container.get_container_host_ip()
    port = rabbitmq_container.get_exposed_port(5672)
    user = rabbitmq_container.username
    password = rabbitmq_container.password
    vhost = rabbitmq_container.vhost
    return f"amqp://{user}:{password}@{host}:{port}/{vhost}"
