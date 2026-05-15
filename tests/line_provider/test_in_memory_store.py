"""Unit tests for line_provider.infrastructure.store.in_memory.

LP-01: in-memory storage guarded by asyncio.Lock.
LP-08: update() returns (new, previous_state) for publish-decision-without-rtrip.
Anti-Pattern 6 (PITFALLS.md): concurrent dict access mitigated by single asyncio.Lock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from line_provider.infrastructure.store.in_memory import (
    EventAlreadyExistsError,
    EventNotFoundError,
    InMemoryEventStore,
)

from line_provider.schemas.events import Event, EventState


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


async def test_smoke_crud_lifecycle() -> None:
    """W-2 revision: smoke replaces inline python -c verify from Task 1.

    Covers: add -> duplicate -> update (new, prev) -> not-found -> get_by_id -> list_all.
    """
    store = InMemoryEventStore()
    eid = uuid4()
    ev = Event(
        event_id=eid,
        coefficient=Decimal("1.50"),
        deadline=_future(),
        state=EventState.NEW,
    )
    assert (await store.add(ev)).event_id == eid
    with pytest.raises(EventAlreadyExistsError):
        await store.add(ev)
    new_ev, prev = await store.update(
        eid,
        coefficient=Decimal("2.00"),
        deadline=ev.deadline,
        state=EventState.FINISHED_WIN,
    )
    assert prev == EventState.NEW
    assert new_ev.state == EventState.FINISHED_WIN
    with pytest.raises(EventNotFoundError):
        await store.update(
            uuid4(),
            coefficient=Decimal("1.00"),
            deadline=ev.deadline,
            state=EventState.NEW,
        )
    retrieved = await store.get_by_id(eid)
    assert retrieved is not None
    assert retrieved.state == EventState.FINISHED_WIN
    assert len(await store.list_all()) == 1
