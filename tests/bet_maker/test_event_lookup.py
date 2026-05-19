"""Unit tests for bet_maker.facades.event_lookup.

EventLookup Protocol satisfied by StubEventLookup structurally.
EventSnapshot is frozen (Pydantic v2 frozen=True) + extra='forbid'.
StubEventLookup.seed() / .seed_active() / .get_event() contract.
Per-test seeding works for tests that later call /bet — verified here
at the unit level.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from bet_maker.facades.event_lookup import (
    EventLookup,
    EventSnapshot,
    StubEventLookup,
)
from bet_maker.schemas.events import EventState


class TestEventSnapshot:
    """EventSnapshot is frozen and forbids extras."""

    def test_construction_happy(self) -> None:
        """Happy path — 3 required fields, no extras."""
        event_id = uuid4()
        deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        snap = EventSnapshot(event_id=event_id, deadline=deadline, state=EventState.NEW)
        assert snap.event_id == event_id
        assert snap.deadline == deadline
        assert snap.state == EventState.NEW

    def test_frozen_rejects_mutation(self) -> None:
        """frozen=True — attribute assignment raises ValidationError."""
        snap = EventSnapshot(
            event_id=uuid4(),
            deadline=datetime.now(timezone.utc),
            state=EventState.NEW,
        )
        with pytest.raises(ValidationError):
            snap.state = EventState.FINISHED_WIN  # type: ignore[misc]

    def test_extra_forbid(self) -> None:
        """extra='forbid' rejects unknown fields (e.g., coefficient drift)."""
        with pytest.raises(ValidationError) as exc:
            EventSnapshot(
                event_id=uuid4(),
                deadline=datetime.now(timezone.utc),
                state=EventState.NEW,
                coefficient="1.50",  # type: ignore[call-arg]
            )
        assert "extra_forbidden" in str(exc.value) or "Extra inputs" in str(exc.value)


class TestStubEventLookup:
    """StubEventLookup seed + get_event contract."""

    async def test_protocol_structural_typing(self) -> None:
        """StubEventLookup satisfies EventLookup Protocol structurally."""
        lookup: EventLookup = StubEventLookup()
        assert hasattr(lookup, "get_event")

    async def test_seed_then_get_event_returns_snapshot(self) -> None:
        """seed(snapshot) → get_event(id) returns the same snapshot."""
        lookup = StubEventLookup()
        event_id = uuid4()
        snap = EventSnapshot(
            event_id=event_id,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
            state=EventState.NEW,
        )
        lookup.seed(snap)
        got = await lookup.get_event(event_id)
        assert got == snap

    async def test_get_event_returns_none_for_unseeded(self) -> None:
        """Unseeded id → None (interactor maps to 422 EventNotBettable)."""
        lookup = StubEventLookup()
        got = await lookup.get_event(uuid4())
        assert got is None

    async def test_seed_active_default_deadline_future_state_new(self) -> None:
        """seed_active(id) defaults to deadline=now+1h, state=NEW."""
        lookup = StubEventLookup()
        event_id = uuid4()
        before = datetime.now(timezone.utc)
        lookup.seed_active(event_id)
        got = await lookup.get_event(event_id)
        assert got is not None
        assert got.state == EventState.NEW
        assert got.deadline > before
        assert got.deadline > before + timedelta(minutes=50)
        assert got.deadline < before + timedelta(minutes=70)

    async def test_seed_active_custom_deadline(self) -> None:
        """seed_active accepts custom deadline (boundary tests)."""
        lookup = StubEventLookup()
        event_id = uuid4()
        custom = datetime(2030, 1, 1, tzinfo=timezone.utc)
        lookup.seed_active(event_id, deadline=custom)
        got = await lookup.get_event(event_id)
        assert got is not None
        assert got.deadline == custom

    async def test_instance_isolation(self) -> None:
        """Each StubEventLookup instance has its own dict — no class
        attribute mutation leak (production safety + test isolation)."""
        lookup_a = StubEventLookup()
        lookup_b = StubEventLookup()
        event_id = uuid4()
        lookup_a.seed_active(event_id)
        assert await lookup_a.get_event(event_id) is not None
        assert await lookup_b.get_event(event_id) is None
