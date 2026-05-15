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
from line_provider.selectors.get_event_by_id import get_event_by_id
from line_provider.selectors.list_active_events import list_active_events

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState

_NOW = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _event(state: EventState, *, offset_hours: float) -> Event:
    return Event(
        event_id=uuid4(),
        coefficient=Decimal("1.50"),
        deadline=_NOW + timedelta(hours=offset_hours),
        state=state,
    )


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
