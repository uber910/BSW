from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus


async def get_pending_locked(session: AsyncSession, event_id: UUID) -> list[Bet]:
    """Lock and return all PENDING bets for ``event_id``.

    Issues ``SELECT ... WHERE event_id = :event_id AND status = 'PENDING'
    FOR UPDATE SKIP LOCKED`` so that consumer and reconciler can settle the
    same event_id concurrently without deadlocks and without double-settle.

    R3 invariant: the FOR UPDATE SKIP LOCKED row lock MUST remain here --
    enforced by ``tests/audit/test_static.py::
    test_pending_locked_selector_uses_for_update_skip_locked``.

    Returns ``list[Bet]`` (ORM objects, not DTOs) because the caller
    (settle / cancel interactor) needs ``bet.id`` to build the
    ``WHERE Bet.id.in_(bet_ids)`` UPDATE clause.

    No ``flush()``, no ``commit()``, no ``rollback()`` -- selectors are
    pure read wrappers; the calling interactor owns the transaction
    through ``async with uow:``.
    """
    result = await session.execute(
        select(Bet)
        .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())
