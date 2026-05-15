from __future__ import annotations

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventCreate, EventState


async def create_event(store: InMemoryEventStore, *, body: EventCreate) -> Event:
    event = Event(
        event_id=body.event_id,
        coefficient=body.coefficient,
        deadline=body.deadline,
        state=EventState.NEW,
    )
    return await store.add(event)
