from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bet_maker.schemas.events import EventState


class EventSnapshot(BaseModel):
    """Frozen snapshot of an event as observed by line-provider.

    Returned by EventLookup.get_event. Interactor place_bet validates:
    snapshot is not None, deadline > now, state == NEW.
    frozen=True ensures the snapshot can't be mutated between validation
    steps. extra='forbid' guards against drift if line-provider adds new
    fields (HttpEventLookup must explicitly handle them).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    deadline: datetime
    state: EventState


class EventLookup(Protocol):
    """Service-boundary facade for resolving an event_id to a snapshot.

    Implementations: StubEventLookup (in-process dict) for tests, and
    HttpEventLookup (httpx -> line-provider GET /event/{id}) for production.
    Both satisfy the same Protocol structurally — no inheritance needed.
    """

    async def get_event(self, event_id: UUID) -> EventSnapshot | None: ...


class StubEventLookup:
    """In-process dict-backed EventLookup for tests + dev environments.

    Tests use `app.state.event_lookup.seed_active(event_id)` to register
    a bettable event before POSTing to /bet. seed_active is the
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

        Default deadline = now + 1 hour. Custom deadline allowed for
        boundary tests (e.g., deadline exactly now -> must be rejected by
        interactor with `deadline <= now()` check).
        """
        if deadline is None:
            deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        self._events[event_id] = EventSnapshot(
            event_id=event_id,
            deadline=deadline,
            state=EventState.NEW,
        )

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        """Return the seeded snapshot or None — interactor maps None to 422."""
        return self._events.get(event_id)
