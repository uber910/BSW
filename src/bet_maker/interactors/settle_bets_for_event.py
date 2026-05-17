"""settle_bets_for_event — idempotent settle interactor for Phase 5/6 (D-17).

Called by:
- Plan 05 RabbitMQ consumer handler (settled_via='consumer')
- Phase 6 reconciliation job (settled_via='reconciler')

Idempotency (R3 / D-12 / D-15):
- BetRepository.get_pending_locked() filters by status=PENDING + locks via
  FOR UPDATE SKIP LOCKED. Second caller on same event_id: 0 rows -> 0-row
  UPDATE -> structlog 'settle.noop' info -> SettleResult(settled_count=0).
- No 'consumed_events' table — status filter is the single source of truth.

Atomicity (R2 / F4):
- Whole operation inside `async with uow:`; UoW commits on clean exit,
  rolls back on exception. Caller acks ONLY after this returns successfully.

Server-side timestamp (D-14):
- settled_at value in UPDATE statement is PG func.now() — same clock as
  created_at/updated_at. Python-side SettleResult.settled_at is a freshly
  taken utc_now() snapshot for logging/return purposes; the canonical
  timestamp lives in PG.

Pitfalls guarded:
- R9/R12 / Anti-Pattern 2: no message dispatch from this function.
  Line-provider owns the outbound path; this interactor is settle-only.
- A1: bet_ids captured BEFORE the UPDATE; no lazy-load after UoW commit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import func, update

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.messages import EventTerminalState
from bet_maker.schemas.settle import SettleResult

_TERMINAL_TO_STATUS: dict[EventTerminalState, BetStatus] = {
    EventTerminalState.FINISHED_WIN: BetStatus.WON,
    EventTerminalState.FINISHED_LOSE: BetStatus.LOST,
}


async def settle_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    terminal_state: EventTerminalState,
    settled_via: Literal["consumer", "reconciler"],
) -> SettleResult:
    log = structlog.get_logger()
    new_status = _TERMINAL_TO_STATUS[terminal_state]
    async with uow:
        bets = await uow.bets.get_pending_locked(event_id)
        settled_at = datetime.now(timezone.utc)
        if not bets:
            log.info(
                "settle.noop",
                event_id=str(event_id),
                reason="no PENDING bets",
                settled_via=settled_via,
            )
            return SettleResult(
                event_id=event_id,
                terminal_state=terminal_state,
                settled_count=0,
                settled_bet_ids=[],
                settled_via=settled_via,
                settled_at=settled_at,
            )

        bet_ids = [b.id for b in bets]
        await uow.session.execute(
            update(Bet)
            .where(Bet.id.in_(bet_ids))
            .values(
                status=new_status,
                settled_at=func.now(),
                settled_via=settled_via,
            )
        )
        log.info(
            "settle.committed",
            event_id=str(event_id),
            settled_count=len(bet_ids),
            settled_bet_ids=[str(bid) for bid in bet_ids],
            settled_via=settled_via,
            new_status=new_status.value,
        )
        return SettleResult(
            event_id=event_id,
            terminal_state=terminal_state,
            settled_count=len(bet_ids),
            settled_bet_ids=bet_ids,
            settled_via=settled_via,
            settled_at=settled_at,
        )
