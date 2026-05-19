"""Integration: reconciler + consumer concurrent settle."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.facades.event_lookup import EventSnapshot
from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
from bet_maker.jobs.reconciler import _reconcile_event
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.events import EventState
from bet_maker.schemas.messages import EventTerminalState
from bet_maker.uow.postgres import PostgresUnitOfWork


class _FakeLookup:
    def __init__(self, snapshot: EventSnapshot | None) -> None:
        self._snapshot = snapshot

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        return self._snapshot


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerConsumerRace:
    async def test_concurrent_settle_consumer_and_reconciler_no_double_update(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Consumer settle + reconciler tick on same event_id ->
        exactly 3 bets in WON, zero PENDING."""
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))

        lookup = _FakeLookup(
            EventSnapshot(
                event_id=event_id,
                deadline=datetime.now(timezone.utc) + timedelta(hours=1),
                state=EventState.FINISHED_WIN,
            )
        )

        await asyncio.gather(
            settle_bets_for_event(
                PostgresUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            ),
            _reconcile_event(session_factory, lookup, event_id),  # type: ignore[arg-type]
        )

        async with session_factory() as session:
            rows = (
                (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalars().all()
            )
        assert len(rows) == 3
        assert all(b.status == BetStatus.WON for b in rows)
        assert all(b.settled_at is not None for b in rows)

    async def test_for_update_skip_locked_one_winner_one_noop(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Settle vs cancel on same event_id -> exactly one returns
        count=3, the other count=0 (SKIP LOCKED + status filter)."""
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))

        settle_r, cancel_r = await asyncio.gather(
            settle_bets_for_event(
                PostgresUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            ),
            cancel_bets_for_event(
                PostgresUnitOfWork(session_factory),
                event_id=event_id,
                cancelled_via="reconciler",
            ),
        )

        counts = sorted([settle_r.settled_count, cancel_r.cancelled_count])
        assert counts == [0, 3], (
            f"expected exactly one of settle/cancel to take all 3 rows, got {counts}"
        )
