from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus


class BetRepository:
    """Repository for Bet entity. UoW owns transactions — no commit here.

    Repositories MUST NOT commit or rollback. Only `.add()` (queue an
    INSERT) and `.get_by_id()` (issue a SELECT). The enclosing UoW calls
    commit on clean exit and rollback on exception.

    `add()` does NOT flush — the caller (place_bet interactor) controls
    flush timing because it needs `session.refresh(bet)` immediately
    after to load server_default created_at/updated_at. The interactor
    calls `uow.bets.add(bet); await uow.session.flush()` explicitly.
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

    async def get_pending_locked(self, event_id: UUID) -> list[Bet]:
        """Lock and return all PENDING bets for an event_id.

        SELECT * FROM bets
        WHERE event_id = :event_id AND status = 'PENDING'
        FOR UPDATE SKIP LOCKED

        This is the idempotency mechanism for both the consumer and the
        reconciler. Two concurrent callers against the same event_id:
        SKIP LOCKED ensures exactly one acquires the rows; the other
        observes 0 rows and takes the settle.noop path. Status filter
        ensures redelivery after a prior successful settle is also a
        0-row no-op.

        Row locks are released when the enclosing UoW commits (async
        with uow exits). PG default READ COMMITTED isolation is
        sufficient -- the row lock plus status filter provide all needed
        serialisability without raising isolation.

        Method only SELECTs; no flush, no commit.
        """
        result = await self._session.execute(
            select(Bet)
            .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def get_pending_event_ids(self) -> list[UUID]:
        """Distinct event_ids with at least one PENDING bet.

        SELECT DISTINCT event_id FROM bets WHERE status = 'PENDING'

        Used by the reconciler tick (_run_tick) to discover which events
        still need a state poll from line-provider. Read-only — no
        FOR UPDATE, no commit, no flush.

        `.scalars().all()` returns the raw UUID column values; plain
        `.all()` would return SQLAlchemy `Row` objects.
        """
        result = await self._session.execute(
            select(Bet.event_id).where(Bet.status == BetStatus.PENDING).distinct()
        )
        return list(result.scalars().all())
