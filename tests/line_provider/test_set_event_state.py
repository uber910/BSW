"""Unit tests for line_provider.interactors.set_event_state.

State transitions through the interactor. A no-op state mutates
coefficient/deadline but does NOT publish. ``commit`` (``store.update``)
happens BEFORE ``publish``. Concurrent ``set_event_state`` on the same
id results in exactly one publish.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from line_provider.helpers.state_machine import TransitionForbiddenError
from line_provider.infrastructure.store.in_memory import (
    EventNotFoundError,
    InMemoryEventStore,
)
from line_provider.interactors.set_event_state import set_event_state
from line_provider.messaging.routing import EVENT_FINISHED_LOSE, EVENT_FINISHED_WIN
from line_provider.schemas.events import Event, EventState
from tests.line_provider._fakes import FakeEventBus


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


async def _seed(store: InMemoryEventStore, state: EventState = EventState.NEW) -> Event:
    event = Event(
        event_id=uuid4(),
        coefficient=Decimal("1.50"),
        deadline=_future(),
        state=state,
    )
    await store.add(event)
    return event


async def test_happy_path_new_to_finished_win_publishes() -> None:
    """NEW->FINISHED_WIN commits then publishes with routing key event.finished.win."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store)

    result = await set_event_state(
        store,
        bus,
        event_id=seeded.event_id,
        coefficient=Decimal("2.00"),
        deadline=seeded.deadline,
        new_state=EventState.FINISHED_WIN,
        correlation_id="req-1",
    )

    assert result.state == EventState.FINISHED_WIN
    assert len(bus.calls) == 1
    message, routing_key = bus.calls[0]
    assert routing_key == "event.finished.win"
    assert message.event_id == seeded.event_id


async def test_happy_path_new_to_finished_lose_publishes() -> None:
    """NEW->FINISHED_LOSE publishes with routing key event.finished.lose."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store)

    await set_event_state(
        store,
        bus,
        event_id=seeded.event_id,
        coefficient=Decimal("2.00"),
        deadline=seeded.deadline,
        new_state=EventState.FINISHED_LOSE,
        correlation_id="req-2",
    )

    assert len(bus.calls) == 1
    assert bus.calls[0][1] == "event.finished.lose"


async def test_no_op_finished_state_mutates_but_does_not_publish() -> None:
    """PUT with state == current_state mutates coefficient/deadline but skips publish."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store, state=EventState.FINISHED_WIN)

    result = await set_event_state(
        store,
        bus,
        event_id=seeded.event_id,
        coefficient=Decimal("9.99"),
        deadline=seeded.deadline,
        new_state=EventState.FINISHED_WIN,
        correlation_id="req-3",
    )

    assert result.coefficient == Decimal("9.99")
    assert bus.calls == []


async def test_no_op_new_state_does_not_publish() -> None:
    """PUT NEW->NEW (no-op) does not publish."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store, state=EventState.NEW)

    await set_event_state(
        store,
        bus,
        event_id=seeded.event_id,
        coefficient=Decimal("2.00"),
        deadline=seeded.deadline,
        new_state=EventState.NEW,
        correlation_id="req-noop",
    )

    assert bus.calls == []


async def test_reverse_transition_aborts_without_mutate_or_publish() -> None:
    """FINISHED_WIN->NEW raises TransitionForbiddenError; store untouched; no publish."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store, state=EventState.FINISHED_WIN)
    snapshot = await store.get_by_id(seeded.event_id)

    with pytest.raises(TransitionForbiddenError):
        await set_event_state(
            store,
            bus,
            event_id=seeded.event_id,
            coefficient=Decimal("9.99"),
            deadline=seeded.deadline,
            new_state=EventState.NEW,
            correlation_id="req-4",
        )

    assert await store.get_by_id(seeded.event_id) == snapshot
    assert bus.calls == []


async def test_missing_event_raises_not_found() -> None:
    """set_event_state on missing id raises EventNotFoundError (route maps to 404)."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    with pytest.raises(EventNotFoundError):
        await set_event_state(
            store,
            bus,
            event_id=uuid4(),
            coefficient=Decimal("1.00"),
            deadline=_future(),
            new_state=EventState.FINISHED_WIN,
            correlation_id="req-5",
        )
    assert bus.calls == []


async def test_commit_happens_before_publish_failing_bus() -> None:
    """If publish fails, the store mutation has already been committed."""
    store = InMemoryEventStore()
    bus = FakeEventBus(fail=True)
    seeded = await _seed(store, state=EventState.NEW)

    with pytest.raises(RuntimeError):
        await set_event_state(
            store,
            bus,
            event_id=seeded.event_id,
            coefficient=Decimal("9.99"),
            deadline=seeded.deadline,
            new_state=EventState.FINISHED_WIN,
            correlation_id="req-6",
        )

    stored = await store.get_by_id(seeded.event_id)
    assert stored is not None
    assert stored.state == EventState.FINISHED_WIN
    assert stored.coefficient == Decimal("9.99")


async def test_published_message_carries_uuid_event_id() -> None:
    """EventFinishedMessage.event_id is the same UUID."""
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store)

    await set_event_state(
        store,
        bus,
        event_id=seeded.event_id,
        coefficient=Decimal("2.00"),
        deadline=seeded.deadline,
        new_state=EventState.FINISHED_WIN,
        correlation_id="req-uuid",
    )

    message, _ = bus.calls[0]
    assert str(message.event_id) == str(seeded.event_id)
    assert message.correlation_id == "req-uuid"


@pytest.mark.asyncio(loop_scope="session")
class TestRoutingConstantsWiring:
    """set_event_state.py must use messaging/routing.py constants,
    not inline string literals."""

    async def test_publish_uses_event_finished_win_constant(self) -> None:
        store = InMemoryEventStore()
        bus = FakeEventBus()
        seeded = await _seed(store)

        await set_event_state(
            store,
            bus,
            event_id=seeded.event_id,
            coefficient=Decimal("1.50"),
            deadline=seeded.deadline,
            new_state=EventState.FINISHED_WIN,
            correlation_id="cid-1",
        )

        assert len(bus.calls) == 1
        _, routing_key = bus.calls[0]
        assert routing_key == EVENT_FINISHED_WIN

    async def test_publish_uses_event_finished_lose_constant(self) -> None:
        store = InMemoryEventStore()
        bus = FakeEventBus()
        seeded = await _seed(store)

        await set_event_state(
            store,
            bus,
            event_id=seeded.event_id,
            coefficient=Decimal("1.50"),
            deadline=seeded.deadline,
            new_state=EventState.FINISHED_LOSE,
            correlation_id="cid-2",
        )

        assert len(bus.calls) == 1
        _, routing_key = bus.calls[0]
        assert routing_key == EVENT_FINISHED_LOSE


async def test_concurrent_set_state_same_id_publishes_exactly_once() -> None:
    """Two concurrent set_event_state on the same NEW event publish ONCE.

    The store's ``update()`` is serialised under ``asyncio.Lock`` and
    returns previous_state; only the call that observes
    ``previous_state == NEW`` publishes. The other call sees
    ``previous_state == FINISHED_*`` (set by the first) and skips publish.
    """
    store = InMemoryEventStore()
    bus = FakeEventBus()
    seeded = await _seed(store, state=EventState.NEW)

    async def do(new_state: EventState) -> None:
        with contextlib.suppress(TransitionForbiddenError):
            await set_event_state(
                store,
                bus,
                event_id=seeded.event_id,
                coefficient=Decimal("2.00"),
                deadline=seeded.deadline,
                new_state=new_state,
                correlation_id="req-conc",
            )

    await asyncio.gather(
        do(EventState.FINISHED_WIN),
        do(EventState.FINISHED_LOSE),
    )

    assert len(bus.calls) == 1
