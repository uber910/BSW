from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet


class BetRepository:
    """Repository for Bet entity. UoW owns transactions — no commit here.

    D-18 / Anti-Pattern 1 (ARCHITECTURE.md): repositories MUST NOT commit
    or rollback. Only `.add()` (queue an INSERT) and `.get_by_id()`
    (issue a SELECT). The enclosing UoW calls commit on clean exit and
    rollback on exception.

    `add()` does NOT flush — the caller (interactor place_bet) controls
    flush timing because it needs `session.refresh(bet)` immediately
    after to load server_default created_at/updated_at (RESEARCH §Pitfall 1).
    Plan 03-07 interactor calls `uow.bets.add(bet); await uow.session.flush()`
    explicitly.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, bet: Bet) -> None:
        """Stage the bet for INSERT in the next flush."""
        self._session.add(bet)

    async def get_by_id(self, bet_id: UUID) -> Bet | None:
        """SELECT * FROM bets WHERE id = :bet_id."""
        result = await self._session.execute(select(Bet).where(Bet.id == bet_id))
        return result.scalar_one_or_none()
