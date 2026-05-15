"""Smoke test for events router (TDD RED phase, Task 1).

Will be replaced by full integration matrix in Task 3.
"""

from __future__ import annotations

from line_provider.entrypoints.api import events


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
