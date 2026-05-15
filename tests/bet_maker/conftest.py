from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    """FastAPI bet_maker app with lifespan triggered.

    Yielded separately so tests can poke `app.state.event_lookup`
    (StubEventLookup.seed) without going through HTTP. Mirror of
    tests/line_provider/conftest.py shape established in P2 Plan 02-01.
    """
    from bet_maker.app import build_app  # noqa: PLC0415

    application = build_app()
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client bound to lifespan-aware app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seed_event(app: FastAPI) -> Callable[..., UUID]:
    """Helper fixture for tests that need to seed StubEventLookup.

    Returns a callable: `seed_event(event_id, deadline=None, state="NEW")`.
    D-11: StubEventLookup.seed_active is the canonical helper, exposed via
    app.state.event_lookup. Until Plan 03-06 lands the real StubEventLookup,
    this fixture is a placeholder that raises AttributeError — Wave 0 stubs
    in test_*.py are pytest.skip'd, so this is never invoked yet.
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
            lookup.seed(
                event_id=event_id,
                deadline=deadline,
                state=state,
            )
        return event_id

    return _seed
