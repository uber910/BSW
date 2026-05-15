from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead


async def list_bets(session: AsyncSession) -> list[BetRead]:
    """Return all bets, newest first.

    D-07 / BM-07: ROADMAP P3 success criterion #3 -- GET /bets ordered by
    created_at DESC. No pagination, no filtering at test-task scale.
    Pure read -- no UoW (D-25), session is one-shot via get_session DI.

    Anti-Pattern 5 mitigation: BetRead.model_validate(row, from_attributes=True)
    inside the iteration -- caller receives DTOs, never ORM instances.
    """
    stmt = select(Bet).order_by(Bet.created_at.desc())
    result = await session.execute(stmt)
    return [BetRead.model_validate(row, from_attributes=True) for row in result.scalars()]
