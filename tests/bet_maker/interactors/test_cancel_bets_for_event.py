"""cancel_bets_for_event interactor tests."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.messages import EventTerminalState
from bet_maker.uow.postgres import PostgresUnitOfWork


@pytest.mark.asyncio(loop_scope="session")
class TestCancelHappyPath:
    async def test_cancels_two_pending_bets_to_cancelled_status(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))
        result = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory),
            event_id=event_id,
            cancelled_via="reconciler",
        )
        assert result.cancelled_count == 2
        async with session_factory() as session:
            rows = (
                (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalars().all()
            )
        assert all(b.status == BetStatus.CANCELLED for b in rows)

    async def test_settled_via_is_reconciler(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory),
            event_id=event_id,
            cancelled_via="reconciler",
        )
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.settled_via == "reconciler"

    async def test_settled_at_is_filled(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory),
            event_id=event_id,
            cancelled_via="reconciler",
        )
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.settled_at is not None


@pytest.mark.asyncio(loop_scope="session")
class TestCancelNoop:
    async def test_idempotent_second_call_returns_zero(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        first = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory), event_id=event_id, cancelled_via="reconciler"
        )
        second = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory), event_id=event_id, cancelled_via="reconciler"
        )
        assert first.cancelled_count == 1
        assert second.cancelled_count == 0
        assert second.cancelled_bet_ids == []

    async def test_noop_when_no_pending_for_event(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        result = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory), event_id=uuid4(), cancelled_via="reconciler"
        )
        assert result.cancelled_count == 0

    async def test_noop_when_only_already_cancelled_exist(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00"), status=BetStatus.CANCELLED))
        result = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory), event_id=event_id, cancelled_via="reconciler"
        )
        assert result.cancelled_count == 0


@pytest.mark.asyncio(loop_scope="session")
class TestCancelConcurrent:
    async def test_concurrent_with_settle_no_double_update(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Settle vs cancel on same event_id — exactly one wins."""
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))
        r_settle, r_cancel = await asyncio.gather(
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
        counts = sorted([r_settle.settled_count, r_cancel.cancelled_count])
        assert counts == [0, 3], f"expected exactly one winner, got {counts}"


@pytest.mark.asyncio(loop_scope="session")
class TestCancelResultShape:
    async def test_cancel_result_is_frozen(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        result = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory), event_id=uuid4(), cancelled_via="reconciler"
        )
        with pytest.raises(ValidationError):
            result.cancelled_count = 999  # type: ignore[misc]

    async def test_cancel_result_cancelled_at_is_utc_aware(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        result = await cancel_bets_for_event(
            PostgresUnitOfWork(session_factory), event_id=uuid4(), cancelled_via="reconciler"
        )
        assert result.cancelled_at.tzinfo is not None
