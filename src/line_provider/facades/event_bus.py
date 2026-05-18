from __future__ import annotations

from typing import Protocol

import structlog
from faststream.rabbit import RabbitBroker
from faststream.rabbit.schemas import ExchangeType, RabbitExchange

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


class RabbitEventBus:
    """Publishes EventFinishedMessage to the bsw.events topic exchange.

    Implements the EventBus Protocol structurally — no inheritance.
    Constructed in lifespan with the FastStream RabbitBroker from
    line_provider.entrypoints.messaging.router.broker.

    correlation_id is propagated from EventFinishedMessage.correlation_id
    (set by the interactor from the HTTP request's request_id middleware
    binding) to broker.publish(correlation_id=...) so the AMQP property
    carries the same id end-to-end. Without this, FastStream would
    generate a random UUID for msg.correlation_id and structlog binding
    in the consumer would lose request traceability.

    persist=True ensures the message survives a broker restart
    (combined with durable=True on the queue declared by bet-maker).
    """

    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker
        self._exchange = RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)

    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None:
        await self._broker.publish(
            message,
            routing_key=routing_key,
            exchange=self._exchange,
            persist=True,
            correlation_id=message.correlation_id,
        )
        structlog.get_logger().info(
            "line_provider.publish",
            routing_key=routing_key,
            event_id=str(message.event_id),
            new_state=message.new_state.value,
            schema_version=message.schema_version,
            correlation_id=message.correlation_id,
        )
