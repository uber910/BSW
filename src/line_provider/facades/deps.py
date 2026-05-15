from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from line_provider.facades.event_bus import EventBus
from line_provider.infrastructure.store.in_memory import InMemoryEventStore


def get_store(request: Request) -> InMemoryEventStore:
    return cast(InMemoryEventStore, request.app.state.event_store)


def get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)


StoreDep = Annotated[InMemoryEventStore, Depends(get_store)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
