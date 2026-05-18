"""Unit tests for RabbitEventBus.publish (Plan 05-06 / LP-06).

Pitfall 6: correlation_id propagation from message into broker.publish kwarg.
Tests use AsyncMock(spec=RabbitBroker) — no real broker required for unit-level
assertion of "broker received the right call".
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from faststream.rabbit import RabbitBroker
from faststream.rabbit.schemas import ExchangeType

from line_provider.facades.event_bus import RabbitEventBus
from line_provider.schemas.messages import EventFinishedMessage, EventTerminalState


def _message(correlation_id: str = "test-corr") -> EventFinishedMessage:
    return EventFinishedMessage(
        schema_version=1,
        event_id=uuid4(),
        new_state=EventTerminalState.FINISHED_WIN,
        coefficient=Decimal("1.50"),
        occurred_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        correlation_id=correlation_id,
    )


@pytest.mark.asyncio(loop_scope="session")
class TestPublish:
    async def test_publish_calls_broker_publish_with_correct_kwargs(self) -> None:
        broker = AsyncMock(spec=RabbitBroker)
        bus = RabbitEventBus(broker)
        msg = _message("abc-123")

        await bus.publish(msg, routing_key="event.finished.win")

        broker.publish.assert_awaited_once()
        args, kwargs = broker.publish.call_args
        assert args[0] is msg or kwargs.get("message") is msg
        assert kwargs.get("routing_key") == "event.finished.win"
        assert kwargs.get("persist") is True
        assert kwargs.get("correlation_id") == "abc-123"
        exchange = kwargs.get("exchange")
        assert exchange is not None
        assert exchange.name == "bsw.events"
        assert exchange.type == ExchangeType.TOPIC
        assert exchange.durable is True

    async def test_publish_propagates_correlation_id_from_message(self) -> None:
        """Pitfall 6: two messages, two correlation_ids — both forwarded as-is."""
        broker = AsyncMock(spec=RabbitBroker)
        bus = RabbitEventBus(broker)

        await bus.publish(_message("corr-1"), routing_key="event.finished.win")
        await bus.publish(_message("corr-2"), routing_key="event.finished.lose")

        assert broker.publish.await_count == 2
        corrs = [c.kwargs.get("correlation_id") for c in broker.publish.call_args_list]
        assert corrs == ["corr-1", "corr-2"]

    async def test_persist_is_always_true(self) -> None:
        broker = AsyncMock(spec=RabbitBroker)
        bus = RabbitEventBus(broker)
        await bus.publish(_message(), routing_key="event.finished.win")
        assert broker.publish.call_args.kwargs.get("persist") is True
