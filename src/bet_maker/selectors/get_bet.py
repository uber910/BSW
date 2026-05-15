from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead


async def get_bet_by_id(session: AsyncSession, bet_id: UUID) -> BetRead | None:
    """SELECT bet by id; return BetRead or None.

    D-08 / BM-13: GET /bet/{bet_id} route maps None -> HTTPException(404).
    Anti-Pattern 5 mitigation: returns DTO (BetRead), never raw Bet ORM.
    """
    result = await session.execute(select(Bet).where(Bet.id == bet_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return BetRead.model_validate(row, from_attributes=True)
