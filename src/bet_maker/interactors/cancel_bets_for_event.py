"""cancel_bets_for_event — idempotent cancel interactor.

Called by:
- The reconciliation job, 404-branch (cancelled_via='reconciler').

Trigger:
- Reconciler observes that line-provider returned 404 for event_id —
  event deleted / LP recreated. Bet cannot be settled because the
  event no longer exists; CANCELLED is the recovery sink.

Idempotency (mirrors settle_bets_for_event):
- selectors.get_pending_locked() filters status='PENDING' and locks
  via FOR UPDATE SKIP LOCKED. Second caller on same event_id: 0 rows ->
  0-row UPDATE -> structlog 'cancel.noop' info -> CancelResult(count=0).

Concurrent with settle:
- cancel vs settle on the same event_id: SKIP LOCKED + status filter
  guarantee exactly one of the two interactors gets all rows; the
  other observes 0 rows. Verified by test_concurrent_with_settle_no_double_update.

Server-side timestamp:
- settled_at column filled with func.now() in the UPDATE — same column
  and clock as settle_bets_for_event. settled_via='reconciler' is the
  attribution.

Invariants:
- bet_ids captured BEFORE the UPDATE; no lazy-load after UoW commit.
- The interactor never calls uow.session.commit() — UoW owns the
  transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import func, update

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.settle import CancelResult
from bet_maker.selectors.get_pending_locked import get_pending_locked
from bet_maker.uow.abstract import AbstractUnitOfWork


async def cancel_bets_for_event(
    uow: AbstractUnitOfWork,
    *,
    event_id: UUID,
    cancelled_via: Literal["reconciler"],
) -> CancelResult:
    log = structlog.get_logger()
    cancelled_at = datetime.now(timezone.utc)
    async with uow:
        bets = await get_pending_locked(uow.session, event_id)
        if not bets:
            log.info(
                "cancel.noop",
                event_id=str(event_id),
                reason="no PENDING bets",
                cancelled_via=cancelled_via,
            )
            return CancelResult(
                event_id=event_id,
                cancelled_count=0,
                cancelled_bet_ids=[],
                cancelled_via=cancelled_via,
                cancelled_at=cancelled_at,
            )

        bet_ids = [b.id for b in bets]
        await uow.session.execute(
            update(Bet)
            .where(Bet.id.in_(bet_ids))
            .values(
                status=BetStatus.CANCELLED,
                settled_at=func.now(),
                settled_via=cancelled_via,
            )
        )
        log.info(
            "cancel.committed",
            event_id=str(event_id),
            cancelled_count=len(bet_ids),
            cancelled_bet_ids=[str(bid) for bid in bet_ids],
            cancelled_via=cancelled_via,
            reason="line_provider_404",
        )
        return CancelResult(
            event_id=event_id,
            cancelled_count=len(bet_ids),
            cancelled_bet_ids=bet_ids,
            cancelled_via=cancelled_via,
            cancelled_at=cancelled_at,
        )
