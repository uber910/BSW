"""Selector: proxy LP GET /events through httpx with retry.

BM-04 / D-10: bet-maker GET /events route delegates here. Always
fetches fresh from LP (D-01: no TTL cache in P4). Returns list[EventRead]
parsed via Pydantic v2 (extra="forbid", frozen=True -- surfaces LP schema
drift as ValidationError).

D-11: uses the shared make_retry_decorator from facades/line_provider_client
(same as HttpEventLookup). Different facade, same retry policy.
"""

from __future__ import annotations

from json import JSONDecodeError

import httpx
from pydantic import ValidationError

from bet_maker.facades.line_provider_client import (
    LineProviderUnavailable,
    make_retry_decorator,
)
from bet_maker.schemas.events import EventRead


async def list_active_events(
    http_client: httpx.AsyncClient,
    *,
    attempts: int = 3,
    max_backoff: float = 2.0,
) -> list[EventRead]:
    """Return the active-events list from line-provider.

    D-10 / BM-04: 200 -> list[EventRead] (possibly empty).
    D-05 / D-07: 5xx after retry exhaustion -> LineProviderUnavailable.
    4xx from LP: not expected (LP /events route has no 4xx response paths)
    but if it happens it falls through to LineProviderUnavailable too --
    Pitfall 5 inverted (no special-case branch needed for /events).
    """
    retry_decorator = make_retry_decorator(attempts, max_backoff)

    @retry_decorator
    async def _call() -> list[EventRead]:
        response = await http_client.get("/events")
        response.raise_for_status()
        return [EventRead.model_validate(item) for item in response.json()]

    try:
        return await _call()
    except httpx.HTTPStatusError as exc:
        raise LineProviderUnavailable(
            reason=f"HTTPStatusError: {exc.response.status_code}"
        ) from exc
    except httpx.TransportError as exc:
        raise LineProviderUnavailable(reason=type(exc).__name__) from exc
    except (JSONDecodeError, KeyError, ValueError, ValidationError) as exc:
        raise LineProviderUnavailable(reason="malformed payload from line-provider") from exc
