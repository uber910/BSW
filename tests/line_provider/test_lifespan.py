"""Lifespan tests for line-provider.

Asserts: broker connect on startup, bsw.events exchange declared,
RabbitEventBus pinned to app.state, broker.close on shutdown.
"""

from __future__ import annotations

import os
from types import TracebackType
from unittest.mock import patch

import pytest
from asgi_lifespan import LifespanManager


@pytest.mark.asyncio(loop_scope="session")
class TestLineProviderLifespan:
    async def test_event_bus_is_rabbit_in_production(self, amqp_url: str) -> None:
        os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
        try:
            from line_provider.api.messaging import (  # noqa: PLC0415
                router as lp_router,
            )
            from line_provider.app import build_app  # noqa: PLC0415
            from line_provider.facades.event_bus import RabbitEventBus  # noqa: PLC0415

            lp_router.broker._connection_kwargs["url"] = amqp_url
            application = build_app()
            async with LifespanManager(application):
                bus = application.state.event_bus
                assert isinstance(bus, RabbitEventBus)
        finally:
            os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)

    async def test_broker_connected_after_startup(self, amqp_url: str) -> None:
        os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
        try:
            from line_provider.api.messaging import (  # noqa: PLC0415
                router as lp_router,
            )
            from line_provider.app import build_app  # noqa: PLC0415

            lp_router.broker._connection_kwargs["url"] = amqp_url
            application = build_app()
            async with LifespanManager(application):
                rmq_ok = await lp_router.broker.ping(timeout=2.0)
                assert rmq_ok is True
        finally:
            os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)

    async def test_bsw_events_exchange_declared_idempotent(self, amqp_url: str) -> None:
        os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
        try:
            from faststream.rabbit.schemas import ExchangeType, RabbitExchange  # noqa: PLC0415

            from line_provider.api.messaging import (  # noqa: PLC0415
                router as lp_router,
            )
            from line_provider.app import build_app  # noqa: PLC0415

            lp_router.broker._connection_kwargs["url"] = amqp_url
            application = build_app()
            async with LifespanManager(application):
                ex = await lp_router.broker.declare_exchange(
                    RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
                )
                assert ex is not None
        finally:
            os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)

    async def test_shutdown_calls_broker_close(self, amqp_url: str) -> None:
        os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
        try:
            from line_provider.api.messaging import (  # noqa: PLC0415
                router as lp_router,
            )
            from line_provider.app import build_app  # noqa: PLC0415

            lp_router.broker._connection_kwargs["url"] = amqp_url
            orig_close = lp_router.broker.close
            call_count = {"n": 0}

            async def counted_close(
                exc_type: type[BaseException] | None = None,
                exc_val: BaseException | None = None,
                exc_tb: TracebackType | None = None,
            ) -> None:
                call_count["n"] += 1
                await orig_close(exc_type, exc_val, exc_tb)

            with patch.object(lp_router.broker, "close", new=counted_close):
                application = build_app()
                async with LifespanManager(application):
                    pass

            assert call_count["n"] == 1
        finally:
            os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)
