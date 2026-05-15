from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from line_provider.schemas.events import Event, EventState


class EventAlreadyExistsError(Exception):
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        super().__init__(f"event {event_id} already exists")


class EventNotFoundError(Exception):
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        super().__init__(f"event {event_id} not found")


class InMemoryEventStore:
    def __init__(self) -> None:
        self._data: dict[UUID, Event] = {}
        self._lock = asyncio.Lock()

    async def add(self, event: Event) -> Event:
        async with self._lock:
            if event.event_id in self._data:
                raise EventAlreadyExistsError(str(event.event_id))
            self._data[event.event_id] = event
            return event

    async def update(
        self,
        event_id: UUID,
        *,
        coefficient: Decimal,
        deadline: datetime,
        state: EventState,
    ) -> tuple[Event, EventState]:
        async with self._lock:
            current = self._data.get(event_id)
            if current is None:
                raise EventNotFoundError(str(event_id))
            previous_state = current.state
            new_event = current.model_copy(
                update={
                    "coefficient": coefficient,
                    "deadline": deadline,
                    "state": state,
                }
            )
            self._data[event_id] = new_event
            return new_event, previous_state

    async def get_by_id(self, event_id: UUID) -> Event | None:
        return self._data.get(event_id)

    async def list_all(self) -> list[Event]:
        return list(self._data.values())
