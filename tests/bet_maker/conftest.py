from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _auto_truncate(truncate_bets: None) -> None:
    """Auto-use wrapper that activates truncate_bets for all bet_maker tests.

    D-23: per-test isolation. truncate_bets is defined in root conftest and
    performs TRUNCATE bets after each test. This fixture requests it with
    autouse=True so every test in tests/bet_maker/ gets the cleanup without
    explicit fixture declaration.
    """


@pytest.fixture(autouse=True)
def _clear_event_lookup(app: FastAPI) -> None:
    """Swap event_lookup with a fresh StubEventLookup before each test.

    After Plan 04-07 (D-14), production lifespan wires HttpEventLookup
    instead of StubEventLookup. To keep existing unit/integration tests
    (test_bet_routes.py POST /bet, GET /bets) working, every test in
    tests/bet_maker/ gets its own StubEventLookup pinned by autouse -
    the seed_event fixture seeds it, post-test the next test gets a
    fresh empty Stub. This restores per-test isolation without
    depending on HttpEventLookup-specific internals.

    Integration tests that need the real HttpEventLookup (Plan 04-08's
    test_events_routes.py against line_provider_app) explicitly override
    app.state.event_lookup AFTER this autouse fixture runs.
    """
    from bet_maker.facades.event_lookup import StubEventLookup  # noqa: PLC0415

    app.state.event_lookup = StubEventLookup()


@pytest_asyncio.fixture(scope="session")
async def app(pg_dsn: str, amqp_url: str) -> AsyncIterator[FastAPI]:
    """Session-scoped FastAPI bet_maker app with lifespan triggered.

    Session-scoped to avoid asyncpg event-loop mismatch: asyncpg connections
    are bound to the event loop they were created in; a function-scoped app
    fixture creates a new engine per test, causing 'Future attached to a
    different loop' on engine.dispose() in the next function-loop.

    Binds testcontainers pg_dsn + amqp_url into the process env before lifespan
    starts — lifespan reads BetMakerSettings() which picks up BET_MAKER_POSTGRES_DSN
    and BET_MAKER_RABBITMQ_URL. Plan 05-07: broker layer added to lifespan requires
    AMQP URL; also patches broker._connection_kwargs since router is module-level.
    Yielded separately so tests can poke app.state.event_lookup (StubEventLookup).
    """
    from bet_maker.app import build_app  # noqa: PLC0415
    from bet_maker.entrypoints.messaging import router as rabbit_router  # noqa: PLC0415

    os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
    os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
    rabbit_router.broker._connection_kwargs["url"] = amqp_url
    try:
        application = build_app()
        async with LifespanManager(application):
            yield application
    finally:
        os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
        os.environ.pop("BET_MAKER_RABBITMQ_URL", None)


@pytest_asyncio.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Session-scoped async HTTP client bound to lifespan-aware app.

    Session-scoped to match app scope — one client for all tests.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seed_event(app: FastAPI) -> Callable[..., UUID]:
    """Helper fixture for tests that need to seed StubEventLookup.

    Returns a callable: seed_event(event_id=None, deadline=None, state="NEW").
    D-11: StubEventLookup.seed_active / seed are the canonical helpers,
    exposed via app.state.event_lookup.
    """

    def _seed(
        event_id: UUID | None = None,
        deadline: datetime | None = None,
        state: str = "NEW",
    ) -> UUID:
        if event_id is None:
            event_id = uuid4()
        if deadline is None:
            deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        lookup = app.state.event_lookup
        if state == "NEW":
            lookup.seed_active(event_id, deadline=deadline)
        else:
            from bet_maker.facades.event_lookup import EventSnapshot  # noqa: PLC0415
            from bet_maker.schemas.events import EventState  # noqa: PLC0415

            lookup.seed(
                EventSnapshot(
                    event_id=event_id,
                    deadline=deadline,
                    state=EventState(state),
                )
            )
        return event_id

    return _seed


@pytest_asyncio.fixture(scope="session")
async def line_provider_app(amqp_url: str) -> AsyncIterator[FastAPI]:
    """Session-scoped line_provider FastAPI app with lifespan triggered.

    D-16 / Pitfall A2: same session-scope as bet_maker `app` fixture -
    they MUST share the same event loop so httpx.ASGITransport can
    proxy between them without 'Future attached to a different loop'.
    Plan 05-07: broker layer added to line-provider lifespan requires
    AMQP URL; patches broker._connection_kwargs since router is module-level.
    """
    from line_provider.app import build_app  # noqa: PLC0415
    from line_provider.entrypoints.messaging import router as lp_rabbit_router  # noqa: PLC0415

    os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
    lp_rabbit_router.broker._connection_kwargs["url"] = amqp_url
    try:
        application = build_app()
        async with LifespanManager(application):
            yield application
    finally:
        os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)
