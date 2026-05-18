from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus


async def get_pending_event_ids(session: AsyncSession) -> list[UUID]:
    """Return distinct event_ids that still have at least one PENDING bet.

    Issues ``SELECT DISTINCT event_id FROM bets WHERE status = 'PENDING'``.
    Used by the reconciliation job (``jobs/reconciler.py::_run_tick``) to
    obtain the work-list of events that need their terminal state checked
    against line-provider.

    Read-only -- no ``FOR UPDATE``, no ``flush()``, no ``commit()``.
    """
    result = await session.execute(
        select(Bet.event_id).where(Bet.status == BetStatus.PENDING).distinct()
    )
    return list(result.scalars().all())
