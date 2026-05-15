from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import structlog

from bet_maker.facades.event_lookup import EventLookup
from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.helpers.money import quantize_amount
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead
from bet_maker.schemas.events import EventState
from config.time import utc_now

log = structlog.get_logger()


class EventNotBettable(Exception):  # noqa: N818
    """Raised by place_bet when event_id is not bettable.

    Route layer (Plan 03-08) catches and maps to HTTPException(422,
    detail=f"event {event_id} is not bettable: {e.reason}").

    D-06: three exact reason strings -- "event not found", "deadline passed",
    "event not active" -- so tests can assert on .reason without coupling
    to the full HTTP detail string.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def place_bet(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    amount: Decimal,
    event_lookup: EventLookup,
) -> BetRead:
    """Place a single bet on an event.

    D-14 / BM-05 / BM-06: validate (event_lookup snapshot exists, deadline
    in future, state == NEW) THEN insert. Validation MUST happen BEFORE
    entering the UoW context -- failed validation must not trigger any
    DB transaction (verified by test_no_db_write_on_validation_fail).

    Anti-Pattern 5 / Pitfall A1 mitigation: BetRead.model_validate(bet,
    from_attributes=True) is called INSIDE `async with uow:` -- after
    flush+refresh, before commit. This loads server_default fields
    (created_at, updated_at) under an open session, eliminating
    MissingGreenlet on attribute access from the route.
    """
    snapshot = await event_lookup.get_event(event_id)
    if snapshot is None:
        log.info("place_bet.rejected", event_id=str(event_id), reason="event not found")
        raise EventNotBettable("event not found")
    if snapshot.deadline <= utc_now():
        log.info(
            "place_bet.rejected",
            event_id=str(event_id),
            reason="deadline passed",
            deadline=snapshot.deadline.isoformat(),
        )
        raise EventNotBettable("deadline passed")
    if snapshot.state != EventState.NEW:
        log.info(
            "place_bet.rejected",
            event_id=str(event_id),
            reason="event not active",
            state=snapshot.state.value,
        )
        raise EventNotBettable("event not active")

    async with uow:
        bet = Bet(event_id=event_id, amount=quantize_amount(amount))
        uow.bets.add(bet)
        await uow.session.flush()
        await uow.session.refresh(bet)
        log.info(
            "place_bet.created",
            bet_id=str(bet.id),
            event_id=str(event_id),
            amount=str(bet.amount),
        )
        return BetRead.model_validate(bet, from_attributes=True)
