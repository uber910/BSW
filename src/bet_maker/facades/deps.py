from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

import httpx
from fastapi import Depends, Request
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bet_maker.facades.event_lookup import EventLookup
from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.settings.config import BetMakerSettings


def get_settings(request: Request) -> BetMakerSettings:
    """Read settings — pinned to app.state by lifespan (Plan 03-08)."""
    return cast(BetMakerSettings, request.app.state.settings)


def get_engine(request: Request) -> AsyncEngine:
    """Read the AsyncEngine — pinned to app.state by lifespan."""
    return cast(AsyncEngine, request.app.state.engine)


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    """Read the async_sessionmaker — pinned to app.state by lifespan."""
    return cast(async_sessionmaker[AsyncSession], request.app.state.sessionmaker)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a one-shot AsyncSession for read-only selectors (no UoW).

    D-25: GET /bets and GET /bet/{id} are pure reads — selectors take a
    session directly. Session is auto-closed when the request exits.
    """
    sessionmaker = get_sessionmaker(request)
    async with sessionmaker() as session:
        yield session


def get_uow(request: Request) -> AsyncUnitOfWork:
    """Construct a fresh UoW for the current request (Pitfall A2 mitigation).

    Each request gets its own UoW -> its own AsyncSession -> its own
    transaction. Sessions are NEVER shared across requests.
    """
    sessionmaker = get_sessionmaker(request)
    return AsyncUnitOfWork(sessionmaker)


def get_event_lookup(request: Request) -> EventLookup:
    """Read the EventLookup — pinned to app.state by lifespan.

    D-13: P3 StubEventLookup; Plan 04 swaps to HttpEventLookup without touching
    this provider — same Protocol satisfied structurally.
    """
    return cast(EventLookup, request.app.state.event_lookup)


def get_line_provider_http_client(request: Request) -> httpx.AsyncClient:
    """D-12: read the singleton httpx.AsyncClient — pinned by lifespan.

    Used by:
    - LineProviderHttpClientDep alias below (for routes).
    - HttpEventLookup constructor (read indirectly through app.state.event_lookup).

    Anti-Pattern A2 mitigation: NO module-level httpx singleton; every
    long-lived object goes through app.state + cast() provider.
    """
    return cast(httpx.AsyncClient, request.app.state.line_provider_http_client)


def get_rabbit_broker(request: Request) -> RabbitBroker:
    """Read the RabbitBroker singleton from FastStream router.

    F5 / Anti-Pattern 5: there is exactly ONE RabbitRouter (declared in
    bet_maker.entrypoints.messaging) -- its `broker` attribute is the
    sole broker instance. Lifespan does `await router.broker.connect()`
    on startup, so by the time /health or any DI consumer reads this,
    the broker is connected.

    Late import (inside the function) avoids a circular import: messaging.py
    imports settle_bets_for_event from interactors, which imports from
    schemas/repositories -- none of which need deps.py. Late import keeps
    deps.py independent of the FastStream wiring module.
    """
    from bet_maker.entrypoints.messaging import router  # noqa: PLC0415

    return router.broker


SettingsDep = Annotated[BetMakerSettings, Depends(get_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
EventLookupDep = Annotated[EventLookup, Depends(get_event_lookup)]
LineProviderHttpClientDep = Annotated[httpx.AsyncClient, Depends(get_line_provider_http_client)]
RabbitBrokerDep = Annotated[RabbitBroker, Depends(get_rabbit_broker)]
