"""Unit tests for line_provider.facades.

EventBus Protocol contract with ``publish(message, *, routing_key)``
plus the NoopEventBus log signature. NoopEventBus is the default and is
swapped to RabbitEventBus when the AMQP layer is wired in.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import structlog
from structlog.testing import capture_logs

from line_provider.facades.event_bus import EventBus, NoopEventBus
from line_provider.schemas.messages import EventFinishedMessage, EventTerminalState


def _message() -> EventFinishedMessage:
    return EventFinishedMessage(
        event_id=uuid4(),
        new_state=EventTerminalState.FINISHED_WIN,
        coefficient=Decimal("2.00"),
        occurred_at=datetime.now(timezone.utc) + timedelta(hours=1),
        correlation_id="req-abc",
    )


async def test_noop_event_bus_implements_protocol() -> None:
    """NoopEventBus satisfies EventBus structural typing."""
    bus: EventBus = NoopEventBus()
    assert hasattr(bus, "publish")


async def test_noop_event_bus_publish_returns_none() -> None:
    """NoopEventBus.publish is a no-op (returns None)."""
    bus = NoopEventBus()
    await bus.publish(_message(), routing_key="event.finished.win")


@pytest.fixture(autouse=True)
def _preserve_structlog_config() -> Iterator[None]:
    """Snapshot + restore structlog global config so tests in this module
    never leak processor mutations to other test files.
    """
    snapshot = structlog.get_config()
    try:
        yield
    finally:
        structlog.configure(**snapshot)


async def test_noop_event_bus_emits_log_event() -> None:
    """publish.noop emits a structlog event with key fields.

    Uses ``structlog.testing.capture_logs()`` as the sole context manager.
    No ``structlog.configure(...)`` inside the test body — ``capture_logs()``
    installs a temporary processor on entry and removes it on exit, so the
    global config is not mutated.
    """
    with capture_logs() as cap:
        await NoopEventBus().publish(_message(), routing_key="event.finished.win")
    assert any(
        entry.get("event") == "event_bus.publish.noop"
        and entry.get("routing_key") == "event.finished.win"
        for entry in cap
    )
