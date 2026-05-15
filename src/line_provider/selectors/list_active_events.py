from __future__ import annotations

from config.time import utc_now
from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState


async def list_active_events(store: InMemoryEventStore) -> list[Event]:
    now = utc_now()
    return [e for e in await store.list_all() if e.state == EventState.NEW and e.deadline > now]
