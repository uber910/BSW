"""Smoke tests for events router + lifespan wiring (TDD RED phase, Tasks 1-2).

Will be replaced by full integration matrix in Task 3.
"""

from __future__ import annotations

from fastapi import FastAPI

from line_provider.entrypoints.api import events
from line_provider.facades.event_bus import NoopEventBus
from line_provider.infrastructure.store.in_memory import InMemoryEventStore


def test_events_router_module_exists() -> None:
    """LP-03/LP-04/LP-05: events router module must exist with 4 routes."""
    api_routes = [r for r in events.router.routes if hasattr(r, "methods")]
    pairs = sorted({(tuple(sorted(r.methods)), r.path) for r in api_routes})
    expected = sorted(
        {
            (("POST",), "/event"),
            (("GET",), "/event/{event_id}"),
            (("PUT",), "/event/{event_id}"),
            (("GET",), "/events"),
        }
    )
    assert pairs == expected, f"unexpected routes: {pairs}"


async def test_lifespan_wires_event_store_and_bus(app: FastAPI) -> None:
    """D-14: lifespan creates InMemoryEventStore + NoopEventBus in app.state."""
    assert isinstance(app.state.event_store, InMemoryEventStore)
    assert isinstance(app.state.event_bus, NoopEventBus)


async def test_app_registers_events_router(app: FastAPI) -> None:
    """LP-03: build_app() includes events.router alongside health.router."""
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/health" in paths
    assert "/event" in paths
    assert "/event/{event_id}" in paths
    assert "/events" in paths
