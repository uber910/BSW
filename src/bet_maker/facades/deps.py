from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, cast

import httpx
from fastapi import Depends, Request
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bet_maker.facades.event_lookup import EventLookup
from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.settings.config import BetMakerSettings


def get_settings(request: Request) -> BetMakerSettings:
    """Read settings — pinned to app.state by lifespan."""
    return cast(BetMakerSettings, request.app.state.settings)


def get_engine(request: Request) -> AsyncEngine:
    """Read the AsyncEngine — pinned to app.state by lifespan."""
    return cast(AsyncEngine, request.app.state.engine)


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    """Read the async_sessionmaker — pinned to app.state by lifespan."""
    return cast(async_sessionmaker[AsyncSession], request.app.state.sessionmaker)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a one-shot AsyncSession for read-only selectors (no UoW).

    GET /bets and GET /bet/{id} are pure reads — selectors take a
    session directly. Session is auto-closed when the request exits.
    """
    sessionmaker = get_sessionmaker(request)
    async with sessionmaker() as session:
        yield session


def get_uow(request: Request) -> AsyncUnitOfWork:
    """Construct a fresh UoW for the current request.

    Each request gets its own UoW -> its own AsyncSession -> its own
    transaction. Sessions are NEVER shared across requests.
    """
    sessionmaker = get_sessionmaker(request)
    return AsyncUnitOfWork(sessionmaker)


def get_event_lookup(request: Request) -> EventLookup:
    """Read the EventLookup — pinned to app.state by lifespan.

    The HttpEventLookup implementation satisfies the EventLookup Protocol
    structurally — no inheritance needed.
    """
    return cast(EventLookup, request.app.state.event_lookup)


def get_line_provider_http_client(request: Request) -> httpx.AsyncClient:
    """Read the singleton httpx.AsyncClient — pinned by lifespan.

    Used by:
    - LineProviderHttpClientDependency alias below (for routes).
    - HttpEventLookup constructor (read indirectly through app.state.event_lookup).

    NO module-level httpx singleton; every long-lived object goes through
    app.state + cast() provider.
    """
    return cast(httpx.AsyncClient, request.app.state.line_provider_http_client)


def get_rabbit_broker(request: Request) -> RabbitBroker:
    """Read the RabbitBroker singleton from FastStream router.

    There is exactly ONE RabbitRouter (declared in
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


SettingsDependency = Annotated[BetMakerSettings, Depends(get_settings)]
EngineDependency = Annotated[AsyncEngine, Depends(get_engine)]
SessionmakerDependency = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
UoWDependency = Annotated[AsyncUnitOfWork, Depends(get_uow)]
EventLookupDependency = Annotated[EventLookup, Depends(get_event_lookup)]
LineProviderHttpClientDependency = Annotated[
    httpx.AsyncClient, Depends(get_line_provider_http_client)
]
RabbitBrokerDependency = Annotated[RabbitBroker, Depends(get_rabbit_broker)]


def get_reconciler_event_lookup(request: Request) -> HttpEventLookup:
    """HttpEventLookup configured with reconciler retry profile.

    Distinct from `get_event_lookup` (route-layer profile, 3 attempts /
    2s backoff); reconciler profile is 5 attempts / 10s max backoff.
    Shares the singleton `line_provider_http_client` — no second pool.
    """
    return cast(HttpEventLookup, request.app.state.reconciler_event_lookup)


def get_reconciliation_task(request: Request) -> asyncio.Task[None]:
    """The background reconciler task pinned by lifespan.

    Used by /health to check `not task.done()`. Forward-string
    ref because asyncio.Task is generic and Python 3.10 mypy strict
    requires explicit parameterisation.
    """
    return cast("asyncio.Task[None]", request.app.state.reconciliation_task)


ReconcilerEventLookupDependency = Annotated[HttpEventLookup, Depends(get_reconciler_event_lookup)]
ReconciliationTaskDependency = Annotated["asyncio.Task[None]", Depends(get_reconciliation_task)]
