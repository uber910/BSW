from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from line_provider.app import build_app


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    """FastAPI instance with lifespan triggered.

    Yielded separately so integration tests in plan 02-07 can seed
    app.state.event_store directly without touching client._transport.
    """
    application = build_app()
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client bound to the lifespan-aware app fixture."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
