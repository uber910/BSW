"""Unit tests for line_provider.facades.

LP-01 (lifespan-ready EventBus): Protocol contract + NoopEventBus log signature.
D-11: EventBus Protocol with publish(message, *, routing_key).
D-14: NoopEventBus is the P2 default; P5 will swap to RabbitEventBus.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import structlog
from line_provider.facades.event_bus import EventBus, NoopEventBus
from structlog.testing import capture_logs

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
    """D-11: NoopEventBus satisfies EventBus structural typing."""
    bus: EventBus = NoopEventBus()
    assert hasattr(bus, "publish")


async def test_noop_event_bus_publish_returns_none() -> None:
    """D-14: NoopEventBus.publish is a no-op (returns None)."""
    bus = NoopEventBus()
    result = await bus.publish(_message(), routing_key="event.finished.win")
    assert result is None


@pytest.fixture(autouse=True)
def _preserve_structlog_config() -> Iterator[None]:
    """W-1 revision: snapshot + restore structlog global config so tests in this module
    never leak processor mutations to other test files.
    """
    snapshot = structlog.get_config()
    try:
        yield
    finally:
        structlog.configure(**snapshot)


async def test_noop_event_bus_emits_log_event() -> None:
    """D-14: publish.noop emits structlog event with key fields.

    W-1 revision: uses structlog.testing.capture_logs() as the sole context manager.
    No structlog.configure(...) inside the test body — capture_logs() installs a temporary
    processor on entry and removes it on exit, so global config is not mutated.
    """
    with capture_logs() as cap:
        await NoopEventBus().publish(_message(), routing_key="event.finished.win")
    assert any(
        entry.get("event") == "event_bus.publish.noop"
        and entry.get("routing_key") == "event.finished.win"
        for entry in cap
    )
