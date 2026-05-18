from __future__ import annotations

import inspect
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.selectors.get_pending_locked import get_pending_locked


@pytest.mark.asyncio(loop_scope="session")
class TestGetPendingLocked:
    """R3: get_pending_locked must lock only PENDING rows for the requested event_id."""

    async def test_returns_only_pending_for_matching_event_id(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_a, event_b = uuid4(), uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_a, amount=Decimal("10.00"), status=BetStatus.PENDING))
            session.add(Bet(event_id=event_a, amount=Decimal("20.00"), status=BetStatus.PENDING))
            session.add(Bet(event_id=event_a, amount=Decimal("30.00"), status=BetStatus.WON))
            session.add(Bet(event_id=event_b, amount=Decimal("40.00"), status=BetStatus.PENDING))
        async with session_factory() as session:
            rows = await get_pending_locked(session, event_a)
        assert len(rows) == 2
        assert all(b.event_id == event_a and b.status == BetStatus.PENDING for b in rows)

    async def test_returns_empty_when_no_pending(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("5.00"), status=BetStatus.WON))
            session.add(Bet(event_id=event_id, amount=Decimal("7.00"), status=BetStatus.LOST))
        async with session_factory() as session:
            rows = await get_pending_locked(session, event_id)
        assert rows == []

    def test_with_for_update_skip_locked_present(self) -> None:
        """Source-level guard duplicating the static audit at the unit-test level."""
        source = inspect.getsource(get_pending_locked)
        assert "with_for_update(skip_locked=True)" in source
        assert "BetStatus.PENDING" in source
