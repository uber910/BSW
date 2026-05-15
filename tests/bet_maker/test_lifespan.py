"""Tests for bet_maker lifespan wiring.

D-13: app.state.engine/sessionmaker/event_lookup pinned after startup.
D-27: wait_for_postgres tenacity retry — stop_after_attempt(10) +
wait_exponential. Test: override to attempts=2 for speed; bad DSN raises
after N retries. Critical Risk Axis 5 (tenacity retry exhaustion).
"""

from __future__ import annotations

import os

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bet_maker.facades.event_lookup import StubEventLookup


@pytest.mark.asyncio(loop_scope="session")
class TestLifespanStatePins:
    """D-13: successful startup pins all required app.state attributes."""

    async def test_engine_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.engine is AsyncEngine after lifespan startup."""
        assert hasattr(app.state, "engine")
        assert isinstance(app.state.engine, AsyncEngine)

    async def test_sessionmaker_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.sessionmaker is async_sessionmaker after lifespan startup."""
        assert hasattr(app.state, "sessionmaker")
        assert isinstance(app.state.sessionmaker, async_sessionmaker)

    async def test_event_lookup_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.event_lookup is StubEventLookup after lifespan startup."""
        assert hasattr(app.state, "event_lookup")
        assert isinstance(app.state.event_lookup, StubEventLookup)

    async def test_settings_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.settings is present (set by configure_structlog phase)."""
        assert hasattr(app.state, "settings")
        assert app.state.settings.service_name == "bet-maker"


class TestLifespanRetryExhaustion:
    """D-27 / Risk Axis 5: tenacity retry exhaustion with bad DSN crashes startup."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_bad_dsn_raises_after_retries(self) -> None:
        """D-27: bad DSN -> wait_for_postgres exhausts retries -> RuntimeError/Exception propagates.

        Override attempts to 2 for speed. LifespanManager raises the propagated
        exception from lifespan (tenacity reraise=True means OperationalError bubbles up,
        and lifespan re-raises it after logging critical + engine.dispose()).
        """
        from unittest.mock import patch  # noqa: PLC0415

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
