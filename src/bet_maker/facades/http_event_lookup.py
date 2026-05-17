"""HTTP implementation of EventLookup Protocol — production EventLookup.

D-11 / D-14: replaces StubEventLookup in production lifespan. Same Protocol,
different backend (httpx -> line-provider). StubEventLookup is retained for
unit tests of place_bet interactor (P3 D-23 truncate-fixture pattern).

D-05 / D-07 / D-09: response mapping --
    200            -> EventSnapshot
    404            -> None (interactor maps to 422 "event not found")
    4xx other      -> HTTPStatusError -> LineProviderUnavailable (route -> 503)
    5xx (retried)  -> after retry exhaustion -> LineProviderUnavailable
    TransportError -> after retry exhaustion -> LineProviderUnavailable

Pitfall 5 (RESEARCH line 627): the 404 short-circuit MUST come BEFORE
the raise_for_status call -- otherwise tenacity would never see 5xx as
its own exception class.
"""

from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

import httpx
from pydantic import ValidationError

from bet_maker.facades.event_lookup import EventSnapshot
from bet_maker.facades.line_provider_client import (
    LineProviderUnavailable,
    make_retry_decorator,
)


class HttpEventLookup:
    """D-11 / D-14: production EventLookup over LP GET /event/{id}.

    Constructor binds a shared retry-factory (D-03 params from BetMakerSettings).
    The underlying httpx.AsyncClient is a singleton owned by lifespan (D-12).
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        attempts: int = 3,
        max_backoff: float = 2.0,
    ) -> None:
        self._http_client = http_client
        self._retry = make_retry_decorator(attempts, max_backoff)

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        """D-09: 404 -> None; 5xx after retry -> LineProviderUnavailable.

        EventLookup Protocol method -- same signature as StubEventLookup.get_event.
        """

        @self._retry
        async def _call() -> EventSnapshot | None:
            response = await self._http_client.get(f"/event/{event_id}")
            if response.status_code == 404:  # noqa: PLR2004
                return None
            response.raise_for_status()
            payload = response.json()
            return EventSnapshot(
                event_id=UUID(payload["event_id"]),
                deadline=payload["deadline"],
                state=payload["state"],
            )

        try:
            return await _call()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            raise LineProviderUnavailable(reason=str(exc)) from exc
        except (JSONDecodeError, KeyError, ValueError, ValidationError) as exc:
            raise LineProviderUnavailable(reason="malformed payload from line-provider") from exc
