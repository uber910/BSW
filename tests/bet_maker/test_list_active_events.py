"""Unit tests for list_active_events selector -- respx-backed.

Covers all four contractual scenarios. Mirrors the respx idiom in
``test_http_event_lookup.py``.
"""

from __future__ import annotations

import inspect
from uuid import uuid4

import httpx
import pytest
import respx
from httpx import Response

from bet_maker.facades.line_provider_client import LineProviderUnavailable
from bet_maker.schemas.events import EventRead, EventState
from bet_maker.selectors.list_active_events import list_active_events

LP_BASE_URL = "http://line-provider:8000"


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL, assert_all_called=True)
async def test_returns_empty_list_when_lp_empty(respx_mock: respx.MockRouter) -> None:
    """Empty LP active list -> empty bet-maker list."""
    respx_mock.get("/events").mock(return_value=Response(200, json=[]))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        result = await list_active_events(client, attempts=3, max_backoff=0.1)

    assert result == []


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL, assert_all_called=True)
async def test_returns_event_read_list_when_lp_has_events(
    respx_mock: respx.MockRouter,
) -> None:
    """200 + payload of 2 events -> list[EventRead] with typed fields."""
    e1_id = str(uuid4())
    e2_id = str(uuid4())
    respx_mock.get("/events").mock(
        return_value=Response(
            200,
            json=[
                {
                    "event_id": e1_id,
                    "coefficient": "2.50",
                    "deadline": "2026-12-01T12:00:00+00:00",
                    "state": "NEW",
                },
                {
                    "event_id": e2_id,
                    "coefficient": "1.75",
                    "deadline": "2026-12-02T12:00:00+00:00",
                    "state": "NEW",
                },
            ],
        )
    )

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        result = await list_active_events(client, attempts=3, max_backoff=0.1)

    assert len(result) == 2
    assert all(isinstance(item, EventRead) for item in result)
    assert {str(item.event_id) for item in result} == {e1_id, e2_id}
    assert all(item.state == EventState.NEW for item in result)


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL, assert_all_called=True)
async def test_5xx_then_200_retry_succeeds(respx_mock: respx.MockRouter) -> None:
    """5xx triggers retry; 200 succeeds within `attempts`."""
    event_id = str(uuid4())
    route = respx_mock.get("/events").mock(
        side_effect=[
            Response(503),
            Response(503),
            Response(
                200,
                json=[
                    {
                        "event_id": event_id,
                        "coefficient": "3.00",
                        "deadline": "2026-12-01T12:00:00+00:00",
                        "state": "NEW",
                    }
                ],
            ),
        ]
    )

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        result = await list_active_events(client, attempts=3, max_backoff=0.1)

    assert len(result) == 1
    assert str(result[0].event_id) == event_id
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_5xx_exhausts_raises_unavailable(respx_mock: respx.MockRouter) -> None:
    """Persistent 5xx -> LineProviderUnavailable.

    route.call_count == attempts (exact, no off-by-one).
    """
    route = respx_mock.get("/events").mock(return_value=Response(503))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        with pytest.raises(LineProviderUnavailable):
            await list_active_events(client, attempts=3, max_backoff=0.1)

    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_malformed_json_raises_unavailable(respx_mock: respx.MockRouter) -> None:
    """WR-01: 200 with non-JSON body -> LineProviderUnavailable.

    A malformed payload on LP must not escape as 500 at the bet-maker
    boundary — it surfaces through the same 503 channel as transport
    errors and 5xx exhaustion.
    """
    respx_mock.get("/events").mock(return_value=Response(200, content=b"not-json"))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        with pytest.raises(LineProviderUnavailable) as exc_info:
            await list_active_events(client, attempts=3, max_backoff=0.1)

    assert exc_info.value.reason == "malformed payload from line-provider"


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_schema_drift_raises_unavailable(respx_mock: respx.MockRouter) -> None:
    """WR-01: 200 with item missing required field -> LineProviderUnavailable.

    EventRead has extra='forbid'; a stray field (or missing required field)
    causes ValidationError which must be mapped to 503, not 500.
    """
    respx_mock.get("/events").mock(return_value=Response(200, json=[{"unexpected": "shape"}]))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        with pytest.raises(LineProviderUnavailable) as exc_info:
            await list_active_events(client, attempts=3, max_backoff=0.1)

    assert exc_info.value.reason == "malformed payload from line-provider"


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_5xx_reason_is_redacted(respx_mock: respx.MockRouter) -> None:
    """WR-02: HTTPStatusError reason is a fixed-shape summary, not raw exc text."""
    respx_mock.get("/events").mock(return_value=Response(503))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        with pytest.raises(LineProviderUnavailable) as exc_info:
            await list_active_events(client, attempts=3, max_backoff=0.1)

    assert exc_info.value.reason == "HTTPStatusError: 503"
    assert LP_BASE_URL not in exc_info.value.reason


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_transport_error_reason_is_redacted(respx_mock: respx.MockRouter) -> None:
    """WR-02: TransportError reason is only the class name, no URL leakage."""
    respx_mock.get("/events").mock(side_effect=httpx.ConnectError("boom"))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        with pytest.raises(LineProviderUnavailable) as exc_info:
            await list_active_events(client, attempts=3, max_backoff=0.1)

    assert exc_info.value.reason == "ConnectError"
    assert "boom" not in exc_info.value.reason


class TestListActiveEvents:
    """Marker class for discoverability.

    The four scenarios above are module-level functions because the
    respx decorator pattern is cleanest at the function level (mirrors
    ``test_http_event_lookup.py``). This class exists as a
    discoverability anchor and a holder for an invariant asserted
    statically about the selector function itself.
    """

    def test_list_active_events_is_async_callable(self) -> None:
        """list_active_events is the bet-maker-side selector callable."""
        assert inspect.iscoroutinefunction(list_active_events)
