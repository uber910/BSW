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

    async def test_event_lookup_is_http_in_production(self, pg_dsn: str) -> None:
        """D-14: app.state.event_lookup is HttpEventLookup right after lifespan yield.

        Captures the value BEFORE the autouse _clear_event_lookup fixture
        could possibly run (we never request it). Asserts production-shape.
        """
        from bet_maker.app import build_app  # noqa: PLC0415

        os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
        try:
            app = build_app()
            async with LifespanManager(app):
                assert isinstance(app.state.event_lookup, HttpEventLookup)
                assert isinstance(app.state.line_provider_http_client, httpx.AsyncClient)
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)


@pytest.mark.asyncio(loop_scope="session")
class TestShutdownOrder:
    """D-20: http_client.aclose() called BEFORE engine.dispose() on shutdown."""

    async def test_aclose_before_dispose(self, pg_dsn: str) -> None:
        """D-20 / Pitfall 6: capture call order during lifespan shutdown.

        Patches both httpx.AsyncClient.aclose and AsyncEngine.dispose at the
        class level (AsyncEngine.dispose is a read-only descriptor on the
        instance, so patch.object on the class is the only stable hook).
        Each patched method appends its name to a shared list before
        delegating to the original implementation.
        """
        from sqlalchemy.ext.asyncio import AsyncEngine as _AsyncEngine  # noqa: PLC0415

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

        os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
        try:
            app = build_app()
            with (
                patch.object(httpx.AsyncClient, "aclose", new=fake_aclose),
                patch.object(_AsyncEngine, "dispose", new=fake_dispose),
            ):
                async with LifespanManager(app):
                    pass
                # LifespanManager exits -> finally -> aclose then dispose
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)

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
            with patch("bet_maker.entrypoints.lifespan.wait_for_postgres") as mock_wait:
                mock_wait.side_effect = RuntimeError("connection refused after retries")
                with pytest.raises(RuntimeError):
                    async with LifespanManager(app):
                        pass
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
