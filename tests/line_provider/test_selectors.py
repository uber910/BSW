"""Unit tests for line_provider.selectors.

LP-04: get_event_by_id returns Event or None (route maps None to 404).
LP-05: list_active_events filters deadline > now AND state == NEW.
Open Question 4: utc_now is monkey-patched at module level for deterministic timing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState
from line_provider.selectors.get_event_by_id import get_event_by_id
from line_provider.selectors.list_active_events import list_active_events

_NOW = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _event(state: EventState, *, offset_hours: float) -> Event:
    return Event(
        event_id=uuid4(),
        coefficient=Decimal("1.50"),
        deadline=_NOW + timedelta(hours=offset_hours),
        state=state,
    )


async def test_get_event_by_id_returns_event() -> None:
    """LP-04: get_event_by_id returns the stored Event."""
    store = InMemoryEventStore()
    event = _event(EventState.NEW, offset_hours=1)
    await store.add(event)
    assert await get_event_by_id(store, event_id=event.event_id) == event


async def test_get_event_by_id_returns_none_when_missing() -> None:
    """LP-04: get_event_by_id returns None when event absent (route maps to 404)."""
    store = InMemoryEventStore()
    assert await get_event_by_id(store, event_id=uuid4()) is None


async def test_list_active_events_excludes_finished_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LP-05: list_active_events filters out FINISHED_WIN and FINISHED_LOSE."""
    monkeypatch.setattr(
        "line_provider.selectors.list_active_events.utc_now",
        lambda: _NOW,
    )
    store = InMemoryEventStore()
    active = _event(EventState.NEW, offset_hours=1)
    finished_win = _event(EventState.FINISHED_WIN, offset_hours=1)
    finished_lose = _event(EventState.FINISHED_LOSE, offset_hours=1)
    await store.add(active)
    await store.add(finished_win)
    await store.add(finished_lose)

    result = await list_active_events(store)
    ids = {e.event_id for e in result}
    assert ids == {active.event_id}


async def test_list_active_events_excludes_past_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LP-05: list_active_events filters out events with deadline <= now."""
    monkeypatch.setattr(
        "line_provider.selectors.list_active_events.utc_now",
        lambda: _NOW,
    )
    store = InMemoryEventStore()
    future = _event(EventState.NEW, offset_hours=1)
    past = _event(EventState.NEW, offset_hours=-1)
    await store.add(future)
    await store.add(past)

    result = await list_active_events(store)
    ids = {e.event_id for e in result}
    assert ids == {future.event_id}


async def test_list_active_events_excludes_deadline_equal_to_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LP-05: deadline == now is NOT considered active (strict `>` comparison)."""
    monkeypatch.setattr(
        "line_provider.selectors.list_active_events.utc_now",
        lambda: _NOW,
    )
    store = InMemoryEventStore()
    boundary = _event(EventState.NEW, offset_hours=0)
    await store.add(boundary)

    assert await list_active_events(store) == []


async def test_list_active_events_returns_only_new_and_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LP-05: combined filter — 1 NEW+future, 1 NEW+past, 1 FINISHED+future -> only NEW+future."""
    monkeypatch.setattr(
        "line_provider.selectors.list_active_events.utc_now",
        lambda: _NOW,
    )
    store = InMemoryEventStore()
    active = _event(EventState.NEW, offset_hours=2)
    new_past = _event(EventState.NEW, offset_hours=-2)
    finished_future = _event(EventState.FINISHED_WIN, offset_hours=2)
    await store.add(active)
    await store.add(new_past)
    await store.add(finished_future)

    result = await list_active_events(store)
    ids = {e.event_id for e in result}
    assert ids == {active.event_id}


async def test_smoke_get_and_list_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """LP-04/LP-05 (W-2 revision): smoke replaces inline python -c verify from Task 1.

    Seeds 1 NEW+future event; asserts get_by_id positive/negative + list len == 1.
    """
    monkeypatch.setattr(
        "line_provider.selectors.list_active_events.utc_now",
        lambda: _NOW,
    )
    store = InMemoryEventStore()
    seeded = _event(EventState.NEW, offset_hours=1)
    await store.add(seeded)
    assert await get_event_by_id(store, event_id=seeded.event_id) is not None
    assert await get_event_by_id(store, event_id=uuid4()) is None
    assert len(await list_active_events(store)) == 1


async def test_list_active_events_empty_store() -> None:
    """LP-05: empty store yields empty list."""
    store = InMemoryEventStore()
    assert await list_active_events(store) == []
