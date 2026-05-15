from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bet_maker.schemas.events import EventState
from config.time import utc_now


class EventSnapshot(BaseModel):
    """Frozen snapshot of an event as observed by line-provider.

    D-11: Returned by EventLookup.get_event. Interactor place_bet (D-14)
    validates: snapshot is not None, deadline > now, state == NEW.
    frozen=True ensures the snapshot can't be mutated between validation
    steps. extra='forbid' guards against drift if line-provider adds new
    fields (Plan 04 HttpEventLookup must explicitly handle them).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    deadline: datetime
    state: EventState


class EventLookup(Protocol):
    """Service-boundary facade for resolving an event_id to a snapshot.

    D-11 / D-13: P3 implementation = StubEventLookup (in-process dict).
    Plan 04 implementation = HttpEventLookup (httpx -> line-provider GET /event/{id}).
    Both satisfy the same Protocol structurally — no inheritance needed.
    """

    async def get_event(self, event_id: UUID) -> EventSnapshot | None: ...


class StubEventLookup:
    """In-process dict-backed EventLookup for P3 tests + dev environments.

    D-11: Tests use `app.state.event_lookup.seed_active(event_id)` to
    register a bettable event before POSTing to /bet. seed_active is the
    common-case convenience method (state=NEW + deadline=now+1h); seed()
    accepts a full EventSnapshot for edge cases (past deadline / finished
    state).
    """

    def __init__(self) -> None:
        self._events: dict[UUID, EventSnapshot] = {}

    def seed(self, snapshot: EventSnapshot) -> None:
        """Register an arbitrary snapshot — used by tests for edge cases."""
        self._events[snapshot.event_id] = snapshot

    def seed_active(
        self,
        event_id: UUID,
        *,
        deadline: datetime | None = None,
    ) -> None:
        """Register an active (state=NEW, deadline in future) event.

        Default deadline = utc_now() + 1 hour. Custom deadline allowed for
        boundary tests (e.g., deadline exactly now -> must be rejected by
        interactor with `deadline <= now()` check, D-14).
        """
        if deadline is None:
            deadline = utc_now() + timedelta(hours=1)
        self._events[event_id] = EventSnapshot(
            event_id=event_id,
            deadline=deadline,
            state=EventState.NEW,
        )

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        """Return the seeded snapshot or None — interactor maps None to 422."""
        return self._events.get(event_id)
