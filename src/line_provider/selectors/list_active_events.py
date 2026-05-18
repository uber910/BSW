from __future__ import annotations

from datetime import datetime, timezone

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState


async def list_active_events(store: InMemoryEventStore) -> list[Event]:
    now = datetime.now(timezone.utc)
    return [e for e in await store.list_all() if e.state == EventState.NEW and e.deadline > now]
