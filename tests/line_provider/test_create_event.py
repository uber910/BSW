"""Unit tests for line_provider.interactors.create_event.

LP-03: create accepts EventCreate body, stores Event(state=NEW).
LP-08: duplicate event_id propagates EventAlreadyExistsError up.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from line_provider.interactors.create_event import create_event

from line_provider.infrastructure.store.in_memory import (
    EventAlreadyExistsError,
    InMemoryEventStore,
)
from line_provider.schemas.events import EventCreate, EventState


def _body() -> EventCreate:
    return EventCreate(
        event_id=uuid4(),
        coefficient=Decimal("1.50"),
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )


async def test_creates_event_with_state_new() -> None:
    """LP-03: create_event produces Event with state=NEW regardless of body (state not in body)."""
    store = InMemoryEventStore()
    body = _body()
    event = await create_event(store, body=body)
    assert event.state == EventState.NEW
    assert event.event_id == body.event_id
    assert event.coefficient == body.coefficient


async def test_event_persists_in_store() -> None:
    """LP-03: created event is retrievable via store.get_by_id."""
    store = InMemoryEventStore()
    body = _body()
    event = await create_event(store, body=body)
    assert await store.get_by_id(body.event_id) == event


async def test_duplicate_event_id_raises() -> None:
    """LP-08: duplicate create raises EventAlreadyExistsError (route maps to 409)."""
    store = InMemoryEventStore()
    body = _body()
    await create_event(store, body=body)
    with pytest.raises(EventAlreadyExistsError):
        await create_event(store, body=body)
