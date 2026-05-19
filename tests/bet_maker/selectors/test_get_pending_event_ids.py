from __future__ import annotations

import inspect
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.selectors.get_pending_event_ids import get_pending_event_ids


@pytest.mark.asyncio(loop_scope="session")
class TestGetPendingEventIds:
    """get_pending_event_ids -- DISTINCT event_ids with at least one PENDING bet."""

    async def test_returns_distinct_event_ids_for_pending_only(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_a, event_b, event_c = uuid4(), uuid4(), uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_a, amount=Decimal("10.00"), status=BetStatus.PENDING))
            session.add(Bet(event_id=event_a, amount=Decimal("20.00"), status=BetStatus.PENDING))
            session.add(Bet(event_id=event_b, amount=Decimal("30.00"), status=BetStatus.PENDING))
            session.add(Bet(event_id=event_c, amount=Decimal("40.00"), status=BetStatus.WON))
        async with session_factory() as session:
            event_ids = await get_pending_event_ids(session)
        assert sorted(map(str, event_ids)) == sorted(map(str, [event_a, event_b]))

    async def test_returns_empty_when_no_pending(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        async with session_factory.begin() as session:
            session.add(Bet(event_id=uuid4(), amount=Decimal("5.00"), status=BetStatus.WON))
            session.add(Bet(event_id=uuid4(), amount=Decimal("7.00"), status=BetStatus.LOST))
        async with session_factory() as session:
            event_ids = await get_pending_event_ids(session)
        assert event_ids == []

    async def test_skips_won_lost_cancelled(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_pending = uuid4()
        async with session_factory.begin() as session:
            session.add(
                Bet(event_id=event_pending, amount=Decimal("1.00"), status=BetStatus.PENDING)
            )
            session.add(Bet(event_id=uuid4(), amount=Decimal("2.00"), status=BetStatus.WON))
            session.add(Bet(event_id=uuid4(), amount=Decimal("3.00"), status=BetStatus.LOST))
            session.add(Bet(event_id=uuid4(), amount=Decimal("4.00"), status=BetStatus.CANCELLED))
        async with session_factory() as session:
            event_ids = await get_pending_event_ids(session)
        assert list(map(str, event_ids)) == [str(event_pending)]

    def test_no_commit_no_flush(self) -> None:
        """Anti-Pattern 1: selector must not own transactions."""
        source = inspect.getsource(get_pending_event_ids)
        assert ".commit(" not in source
        assert ".flush(" not in source
        assert ".rollback(" not in source
        assert "select(" in source
        assert ".distinct()" in source
