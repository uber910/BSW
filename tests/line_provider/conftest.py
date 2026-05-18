from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="session")
async def app(amqp_url: str) -> AsyncIterator[FastAPI]:
    """Session-scoped FastAPI instance with lifespan triggered.

    Plan 05-07: line-provider lifespan now connects to RabbitMQ broker,
    so amqp_url from the session-scoped testcontainers RabbitMQ is required.
    Session-scoped to avoid 'Future attached to a different loop' errors when
    broker connects in session event loop (asyncio_default_fixture_loop_scope=session).
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


@pytest.fixture(autouse=True)
def _reset_event_store(app: FastAPI) -> None:
    """Clear InMemoryEventStore before each test for isolation.

    Session-scoped `app` shares state across tests. This autouse fixture
    resets the event store and replaces the event_bus with a FakeEventBus
    so tests don't require a live AMQP connection for HTTP-level assertions.
    Tests that need real event_bus behaviour can override app.state.event_bus.
    """
    from line_provider.infrastructure.store.in_memory import (  # noqa: PLC0415
        InMemoryEventStore,
    )
    from tests.line_provider._fakes import FakeEventBus  # noqa: PLC0415

    app.state.event_store = InMemoryEventStore()
    app.state.event_bus = FakeEventBus()


@pytest_asyncio.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Session-scoped async HTTP client bound to the lifespan-aware app fixture.

    Session-scoped to match `app` scope — one client per session.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
