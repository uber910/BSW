"""BetRepository.get_pending_event_ids assertions (Plan 06-05 / BM-12 / D-01)."""

from __future__ import annotations

import inspect
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.models.bet import Bet
from bet_maker.repositories.bets import BetRepository
from bet_maker.schemas.bets import BetStatus


@pytest.mark.asyncio(loop_scope="session")
class TestGetPendingEventIds:
    async def test_returns_distinct_event_ids_for_pending_bets(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_a, event_b = uuid4(), uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_a, amount=Decimal(amt)))
            for amt in ("5.00", "15.00"):
                session.add(Bet(event_id=event_b, amount=Decimal(amt)))
        async with AsyncUnitOfWork(session_factory) as uow:
            event_ids = await uow.bets.get_pending_event_ids()
        assert set(event_ids) == {event_a, event_b}
        assert len(event_ids) == 2

    async def test_excludes_won_lost_cancelled_bets(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        ev_pending, ev_won, ev_lost, ev_cancelled = uuid4(), uuid4(), uuid4(), uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=ev_pending, amount=Decimal("10.00"), status=BetStatus.PENDING))
            session.add(Bet(event_id=ev_won, amount=Decimal("10.00"), status=BetStatus.WON))
            session.add(Bet(event_id=ev_lost, amount=Decimal("10.00"), status=BetStatus.LOST))
            session.add(
                Bet(event_id=ev_cancelled, amount=Decimal("10.00"), status=BetStatus.CANCELLED)
            )
        async with AsyncUnitOfWork(session_factory) as uow:
            event_ids = await uow.bets.get_pending_event_ids()
        assert event_ids == [ev_pending]

    async def test_returns_empty_list_when_no_pending(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        async with AsyncUnitOfWork(session_factory) as uow:
            event_ids = await uow.bets.get_pending_event_ids()
        assert event_ids == []

    async def test_no_commit_no_flush(self) -> None:
        """Anti-Pattern 1: repository must not own transactions."""
        source = inspect.getsource(BetRepository.get_pending_event_ids)
        assert ".commit(" not in source
        assert ".flush(" not in source
        assert ".rollback(" not in source
        assert "select(" in source
        assert ".distinct()" in source
