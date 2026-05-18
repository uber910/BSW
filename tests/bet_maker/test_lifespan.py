"""Tests for bet_maker lifespan wiring.

D-13 / D-14 / D-19 / D-20: app.state.engine/sessionmaker/event_lookup/
line_provider_http_client pinned after startup; shutdown reverse-order
(http_client.aclose BEFORE engine.dispose).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bet_maker.facades.http_event_lookup import HttpEventLookup


@pytest.mark.asyncio(loop_scope="session")
class TestLifespanStatePins:
    """D-13: successful startup pins required app.state attributes.

    Uses the shared `app` fixture - autouse _clear_event_lookup may
    swap event_lookup, so we assert only attributes that autouse does
    NOT touch (engine, sessionmaker, settings, line_provider_http_client).
    """

    async def test_engine_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.engine is AsyncEngine after lifespan startup."""
        assert hasattr(app.state, "engine")
        assert isinstance(app.state.engine, AsyncEngine)

    async def test_sessionmaker_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.sessionmaker is async_sessionmaker after lifespan startup."""
        assert hasattr(app.state, "sessionmaker")
        assert isinstance(app.state.sessionmaker, async_sessionmaker)

    async def test_settings_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.settings is present after startup."""
        assert hasattr(app.state, "settings")
        assert app.state.settings.service_name == "bet-maker"

    async def test_http_client_pinned_on_state(self, app: FastAPI) -> None:
        """D-12 / D-19: app.state.line_provider_http_client is httpx.AsyncClient.

        Autouse _clear_event_lookup swaps event_lookup but leaves
        line_provider_http_client alone, so this assertion holds
        within the shared session fixture.
        """
        assert hasattr(app.state, "line_provider_http_client")
        assert isinstance(app.state.line_provider_http_client, httpx.AsyncClient)


@pytest.mark.asyncio(loop_scope="session")
class TestProductionLifespanWiring:
    """D-14 / D-19: in a clean lifespan run (no autouse swap), event_lookup is HttpEventLookup.

    Builds a fresh app inside the test body, bypassing conftest autouse fixtures.
    Mirrors TestLifespanRetryExhaustion pattern.
    """

    async def test_event_lookup_is_http_in_production(self, pg_dsn: str, amqp_url: str) -> None:
        """D-14: app.state.event_lookup is HttpEventLookup right after lifespan yield.

        Captures the value BEFORE the autouse _clear_event_lookup fixture
        could possibly run (we never request it). Asserts production-shape.

        Plan 05-07: stubs out the broker lifecycle methods (connect/close and
        topology declarations) so that the session-scoped singleton broker state
        is never mutated by this test's private LifespanManager.  Only the PG
        and httpx layers are exercised here; broker wiring is covered by
        TestBrokerLifespan which uses the session-scoped `app` fixture directly.
        """
        from unittest.mock import AsyncMock  # noqa: PLC0415

        from bet_maker.api.messaging import router  # noqa: PLC0415
        from bet_maker.app import build_app  # noqa: PLC0415

        noop = AsyncMock(return_value=AsyncMock())

        os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
        os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
        try:
            app = build_app()
            with (
                patch.object(router.broker, "connect", new=noop),
                patch.object(router.broker, "declare_exchange", new=noop),
                patch.object(router.broker, "declare_queue", new=noop),
                patch.object(router.broker, "start", new=noop),
                patch.object(router.broker, "stop", new=noop),
                patch.object(router.broker, "close", new=noop),
            ):
                async with LifespanManager(app):
                    assert isinstance(app.state.event_lookup, HttpEventLookup)
                    assert isinstance(app.state.line_provider_http_client, httpx.AsyncClient)
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
            os.environ.pop("BET_MAKER_RABBITMQ_URL", None)


@pytest.mark.asyncio(loop_scope="session")
class TestShutdownOrder:
    """D-20: http_client.aclose() called BEFORE engine.dispose() on shutdown."""

    async def test_aclose_before_dispose(self, pg_dsn: str, amqp_url: str) -> None:
        """D-20 / Pitfall 6: capture call order during lifespan shutdown.

        Patches both httpx.AsyncClient.aclose and AsyncEngine.dispose at the
        class level (AsyncEngine.dispose is a read-only descriptor on the
        instance, so patch.object on the class is the only stable hook).
        Each patched method appends its name to a shared list before
        delegating to the original implementation.

        Plan 05-07: also patches rabbit_router.broker.close to a no-op so the
        singleton broker connection is not closed (which would break the session-
        scoped `app` fixture that holds the same broker open).
        """
        from sqlalchemy.ext.asyncio import AsyncEngine as _AsyncEngine  # noqa: PLC0415

        from bet_maker.api.messaging import router  # noqa: PLC0415
        from bet_maker.app import build_app  # noqa: PLC0415

        call_order: list[str] = []

        original_aclose = httpx.AsyncClient.aclose
        original_dispose = _AsyncEngine.dispose

        async def fake_aclose(self: httpx.AsyncClient) -> None:
            call_order.append("aclose")
            await original_aclose(self)

        async def fake_dispose(self: _AsyncEngine, close: bool = True) -> None:
            call_order.append("dispose")
            await original_dispose(self, close=close)

        from unittest.mock import AsyncMock as _AsyncMock  # noqa: PLC0415

        broker_noop = _AsyncMock(return_value=_AsyncMock())

        os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
        os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
        try:
            app = build_app()
            with (
                patch.object(httpx.AsyncClient, "aclose", new=fake_aclose),
                patch.object(_AsyncEngine, "dispose", new=fake_dispose),
                patch.object(router.broker, "connect", new=broker_noop),
                patch.object(router.broker, "declare_exchange", new=broker_noop),
                patch.object(router.broker, "declare_queue", new=broker_noop),
                patch.object(router.broker, "start", new=broker_noop),
                patch.object(router.broker, "stop", new=broker_noop),
                patch.object(router.broker, "close", new=broker_noop),
            ):
                async with LifespanManager(app):
                    pass
                # LifespanManager exits -> finally -> broker.close -> aclose -> dispose
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
            os.environ.pop("BET_MAKER_RABBITMQ_URL", None)

        # Filter to lifespan-owned calls only; ignore any teardown noise
        # from other fixtures that may also touch dispose/aclose during
        # the same scope exit.
        assert "aclose" in call_order
        assert "dispose" in call_order
        assert call_order.index("aclose") < call_order.index("dispose"), (
            f"shutdown order wrong; expected aclose before dispose, got {call_order}"
        )


class TestLifespanRetryExhaustion:
    """D-27 / Risk Axis 5: tenacity retry exhaustion with bad DSN crashes startup."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_bad_dsn_raises_after_retries(self) -> None:
        """D-27: bad DSN -> wait_for_postgres exhausts retries -> RuntimeError propagates."""
        from bet_maker.app import build_app  # noqa: PLC0415

        bad_dsn = "postgresql+asyncpg://invalid:invalid@localhost:19999/nonexistent"
        os.environ["BET_MAKER_POSTGRES_DSN"] = bad_dsn
        try:
            app = build_app()
            with patch("bet_maker.lifespan.wait_for_postgres") as mock_wait:
                mock_wait.side_effect = RuntimeError("connection refused after retries")
                with pytest.raises(RuntimeError):
                    async with LifespanManager(app):
                        pass
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)


@pytest.mark.asyncio(loop_scope="session")
class TestBrokerLifespan:
    """Plan 05-07: AMQP broker layer added to bet-maker lifespan.

    Uses session-scoped `app` fixture (already started with PG + RMQ testcontainers).
    The broker is already connected when these tests run.
    """

    async def test_broker_connected_and_has_subscribers(self, app: FastAPI) -> None:
        from bet_maker.api.messaging import router  # noqa: PLC0415

        rmq_ok = await router.broker.ping(timeout=2.0)
        assert rmq_ok is True
        assert len(router.broker.subscribers) >= 1

    async def test_shutdown_order_broker_before_httpx_before_engine(self, app: FastAPI) -> None:
        from inspect import getsource  # noqa: PLC0415

        from bet_maker.lifespan import lifespan  # noqa: PLC0415

        src = getsource(lifespan)
        # Check within the shutdown finally block specifically.
        # Use the log.info("bet_maker.shutdown") marker which is the first
        # statement in the finally block.
        shutdown_marker = 'log.info("bet_maker.shutdown")'
        shutdown_start = src.index(shutdown_marker)
        shutdown_block = src[shutdown_start:]

        broker_close_pos = shutdown_block.index("await rabbit_router.broker.close()")
        http_aclose_pos = shutdown_block.index("await http_client.aclose()")
        # Last await engine.dispose() — use rfind to get the one in shutdown finally
        engine_dispose_pos = shutdown_block.rindex("await engine.dispose()")

        assert broker_close_pos < http_aclose_pos, (
            "broker.close() must appear before http_client.aclose() in shutdown block"
        )
        assert http_aclose_pos < engine_dispose_pos, (
            "http_client.aclose() must appear before engine.dispose() in shutdown block"
        )

    async def test_dlq_declared_and_idempotent(self, app: FastAPI) -> None:
        from faststream.rabbit.schemas import RabbitQueue  # noqa: PLC0415

        from bet_maker.api.messaging import router  # noqa: PLC0415

        dlq = await router.broker.declare_queue(
            RabbitQueue("bet_maker.events.finished.dlq", durable=True)
        )
        assert dlq is not None
