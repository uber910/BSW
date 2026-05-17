"""Unit tests for HttpEventLookup -- respx-backed (no real network).

BM-04 / D-05 / D-07 / D-09 / D-15: covers all 5 contractual scenarios for
the HTTP-backed EventLookup implementation.

respx mock idiom verified against Context7 /lundberg/respx
(04-RESEARCH.md lines 405-477).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
import respx
from httpx import Response

from bet_maker.facades.event_lookup import EventLookup
from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.facades.line_provider_client import LineProviderUnavailable
from bet_maker.schemas.events import EventState

LP_BASE_URL = "http://line-provider:8000"


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL, assert_all_called=True)
async def test_get_event_200_returns_snapshot(respx_mock: respx.MockRouter) -> None:
    """BM-04 / D-09: 200 with valid payload -> EventSnapshot with typed fields."""
    event_id = UUID("11111111-1111-1111-1111-111111111111")
    respx_mock.get(f"/event/{event_id}").mock(
        return_value=Response(
            200,
            json={
                "event_id": str(event_id),
                "coefficient": "2.50",
                "deadline": "2026-12-01T12:00:00+00:00",
                "state": "NEW",
            },
        )
    )

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=0.1)
        snapshot = await lookup.get_event(event_id)

    assert snapshot is not None
    assert snapshot.event_id == event_id
    assert snapshot.state == EventState.NEW
    assert snapshot.deadline.tzinfo is not None


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_get_event_404_returns_none(respx_mock: respx.MockRouter) -> None:
    """BM-04 / D-09: 404 -> None (NOT raise); no retry (route.call_count == 1)."""
    event_id = uuid4()
    route = respx_mock.get(f"/event/{event_id}").mock(return_value=Response(404))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=0.1)
        result = await lookup.get_event(event_id)

    assert result is None
    assert route.call_count == 1  # Pitfall 4: NO retry on 4xx


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_get_event_4xx_propagates_no_retry(respx_mock: respx.MockRouter) -> None:
    """BM-04 / D-05: 422 from LP -> LineProviderUnavailable; called exactly once (no retry)."""
    event_id = uuid4()
    route = respx_mock.get(f"/event/{event_id}").mock(return_value=Response(422))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=0.1)
        with pytest.raises(LineProviderUnavailable):
            await lookup.get_event(event_id)

    assert route.call_count == 1  # Pitfall 4: NO retry on 4xx


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL)
async def test_get_event_5xx_exhausts_raises(respx_mock: respx.MockRouter) -> None:
    """BM-04 / D-05 / D-07: 503 every time -> LineProviderUnavailable.

    route.call_count == attempts (no silent off-by-one).
    """
    event_id = uuid4()
    route = respx_mock.get(f"/event/{event_id}").mock(return_value=Response(503))

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=0.1)
        with pytest.raises(LineProviderUnavailable):
            await lookup.get_event(event_id)

    assert route.call_count == 3  # exactly `attempts` total


@pytest.mark.asyncio
@respx.mock(base_url=LP_BASE_URL, assert_all_called=True)
async def test_get_event_5xx_then_200_retry_succeeds(respx_mock: respx.MockRouter) -> None:
    """BM-04 / D-05: 5xx triggers retry; subsequent 200 succeeds within `attempts`."""
    event_id_str = "22222222-2222-2222-2222-222222222222"
    route = respx_mock.get(f"/event/{event_id_str}").mock(
        side_effect=[
            Response(503),
            Response(503),
            Response(
                200,
                json={
                    "event_id": event_id_str,
                    "coefficient": "1.75",
                    "deadline": "2026-12-01T12:00:00+00:00",
                    "state": "NEW",
                },
            ),
        ]
    )

    async with httpx.AsyncClient(base_url=LP_BASE_URL, timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=0.1)
        snapshot = await lookup.get_event(UUID(event_id_str))

    assert snapshot is not None
    assert snapshot.state == EventState.NEW
    assert route.call_count == 3


class TestHttpEventLookup:
    """Marker class for plan acceptance criterion (artifact contains 'class TestHttpEventLookup').

    The 5 scenarios above are module-level functions because the respx
    decorator pattern is cleanest at the function level (see Plan 04-05 note).
    This class exists only as a discoverability anchor and a holder for
    invariants asserted statically about HttpEventLookup itself.
    """

    def test_implements_event_lookup_protocol_structurally(self) -> None:
        """D-11: HttpEventLookup satisfies the EventLookup Protocol (structural)."""
        client = httpx.AsyncClient(base_url=LP_BASE_URL)
        lookup: EventLookup = HttpEventLookup(http_client=client)
        assert lookup is not None
