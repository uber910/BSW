from __future__ import annotations

from uuid import UUID

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event


async def get_event_by_id(
    store: InMemoryEventStore,
    *,
    event_id: UUID,
) -> Event | None:
    return await store.get_by_id(event_id)
