from __future__ import annotations

from typing import Protocol

import structlog

from line_provider.schemas.messages import EventFinishedMessage


class EventBus(Protocol):
    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None: ...


class NoopEventBus:
    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None:
        structlog.get_logger().info(
            "event_bus.publish.noop",
            routing_key=routing_key,
            event_id=str(message.event_id),
            new_state=message.new_state.value,
            schema_version=message.schema_version,
            correlation_id=message.correlation_id,
        )
