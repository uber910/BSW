"""GET /events — proxy active events from line-provider.

BM-04 / D-10: bet-maker /events delegates to list_active_events selector
(Plan 04-06) which calls LP via the singleton httpx.AsyncClient (Plan 04-07).
On LineProviderUnavailable → 503 with static detail string. No TTL cache
(D-01). Empty list → 200 + [].
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from bet_maker.facades.deps import LineProviderHttpClientDep
from bet_maker.facades.line_provider_client import LineProviderUnavailable
from bet_maker.schemas.events import EventRead
from bet_maker.selectors.list_active_events import list_active_events

router = APIRouter(tags=["events"])


@router.get(
    "/events",
    response_model=list[EventRead],
)
async def get_events(http_client: LineProviderHttpClientDep) -> list[EventRead]:
    """GET /events — list active events from line-provider.

    BM-04 / D-10: 200 + list[EventRead] on success; 503 + static detail
    on LineProviderUnavailable (upstream LP unreachable after retry).
    D-01: no caching — fresh fetch every request.
    """
    try:
        return await list_active_events(http_client)
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="line-provider unreachable",
        ) from exc
