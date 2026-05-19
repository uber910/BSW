"""Unit tests for line_provider.infrastructure.store.in_memory.

In-memory storage guarded by ``asyncio.Lock``. ``update()`` returns
``(new, previous_state)`` so callers can decide whether to publish
without a re-read. Concurrent dict access is mitigated by a single
``asyncio.Lock``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from line_provider.infrastructure.store.in_memory import (
    EventAlreadyExistsError,
    EventNotFoundError,
    InMemoryEventStore,
)
from line_provider.schemas.events import Event, EventState


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


def _event(state: EventState = EventState.NEW, event_id: UUID | None = None) -> Event:
    return Event(
        event_id=event_id or uuid4(),
        coefficient=Decimal("1.50"),
        deadline=_future(),
        state=state,
    )


async def test_add_returns_event() -> None:
    """add returns the stored event."""
    store = InMemoryEventStore()
    event = _event()
    result = await store.add(event)
    assert result == event


async def test_add_persists_event() -> None:
    """Stored event is retrievable via get_by_id."""
    store = InMemoryEventStore()
    event = _event()
    await store.add(event)
    assert await store.get_by_id(event.event_id) == event


async def test_add_duplicate_raises() -> None:
    """Duplicate event_id raises EventAlreadyExistsError."""
    store = InMemoryEventStore()
    event = _event()
    await store.add(event)
    with pytest.raises(EventAlreadyExistsError) as exc:
        await store.add(event)
    assert str(event.event_id) in str(exc.value)


async def test_update_returns_new_and_previous() -> None:
    """update returns (new_event, previous_state)."""
    store = InMemoryEventStore()
    event = _event(state=EventState.NEW)
    await store.add(event)
    new_event, previous = await store.update(
        event.event_id,
        coefficient=Decimal("3.00"),
        deadline=event.deadline,
        state=EventState.FINISHED_WIN,
    )
    assert previous == EventState.NEW
    assert new_event.state == EventState.FINISHED_WIN
    assert new_event.coefficient == Decimal("3.00")
    assert new_event.event_id == event.event_id


async def test_update_creates_new_object_not_mutating_current() -> None:
    """update produces a new frozen object; original references stay intact."""
    store = InMemoryEventStore()
    event = _event(state=EventState.NEW)
    await store.add(event)
    snapshot = await store.get_by_id(event.event_id)
    assert snapshot is not None
    await store.update(
        event.event_id,
        coefficient=Decimal("9.00"),
        deadline=event.deadline,
        state=EventState.FINISHED_LOSE,
    )
    assert snapshot.coefficient == Decimal("1.50")
    assert snapshot.state == EventState.NEW


async def test_update_no_op_state_preserves_previous_marker() -> None:
    """previous_state reports the state BEFORE update, even on no-op."""
    store = InMemoryEventStore()
    event = _event(state=EventState.FINISHED_WIN)
    await store.add(event)
    new_event, previous = await store.update(
        event.event_id,
        coefficient=Decimal("4.00"),
        deadline=event.deadline,
        state=EventState.FINISHED_WIN,
    )
    assert previous == EventState.FINISHED_WIN
    assert new_event.state == EventState.FINISHED_WIN
    assert new_event.coefficient == Decimal("4.00")


async def test_update_missing_raises() -> None:
    """update on absent id raises EventNotFoundError."""
    store = InMemoryEventStore()
    with pytest.raises(EventNotFoundError):
        await store.update(
            uuid4(),
            coefficient=Decimal("1.00"),
            deadline=_future(),
            state=EventState.NEW,
        )


async def test_get_by_id_returns_none_for_missing() -> None:
    """get_by_id returns None when event absent (caller decides 404)."""
    store = InMemoryEventStore()
    assert await store.get_by_id(uuid4()) is None


async def test_list_all_returns_snapshot() -> None:
    """list_all returns a snapshot; later add does not retroactively appear."""
    store = InMemoryEventStore()
    await store.add(_event())
    snapshot = await store.list_all()
    await store.add(_event())
    assert len(snapshot) == 1
    assert len(await store.list_all()) == 2


async def test_concurrent_add_distinct_ids_all_succeed() -> None:
    """asyncio.gather of 100 add() with distinct ids — all stored."""
    store = InMemoryEventStore()
    events = [_event() for _ in range(100)]
    await asyncio.gather(*[store.add(e) for e in events])
    assert len(await store.list_all()) == 100


async def test_concurrent_add_same_id_exactly_one_succeeds() -> None:
    """20 concurrent add() of same event_id — exactly 1 succeeds."""
    store = InMemoryEventStore()
    event = _event()
    results = await asyncio.gather(
        *[store.add(event) for _ in range(20)],
        return_exceptions=True,
    )
    successes = [r for r in results if isinstance(r, Event)]
    failures = [r for r in results if isinstance(r, EventAlreadyExistsError)]
    assert len(successes) == 1
    assert len(failures) == 19


async def test_smoke_crud_lifecycle() -> None:
    """Smoke test covering the full store lifecycle.

    add -> duplicate -> update (new, prev) -> not-found -> get_by_id -> list_all.
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


async def test_concurrent_update_serialised_under_lock() -> None:
    """Two concurrent update() calls on the same id are serialised — the
    second observes previous_state set by the first, not the original state.
    """
    store = InMemoryEventStore()
    event = _event(state=EventState.NEW)
    await store.add(event)

    async def do(new_state: EventState) -> tuple[Event, EventState]:
        return await store.update(
            event.event_id,
            coefficient=Decimal("2.00"),
            deadline=event.deadline,
            state=new_state,
        )

    results = await asyncio.gather(
        do(EventState.FINISHED_WIN),
        do(EventState.FINISHED_LOSE),
    )
    previous_states = [prev for (_, prev) in results]
    assert EventState.NEW in previous_states
    assert any(p != EventState.NEW for p in previous_states)
