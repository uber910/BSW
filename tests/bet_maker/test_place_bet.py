"""Unit tests for bet_maker.interactors.place_bet.

BM-05: happy path inserts Bet, returns BetRead with PENDING status.
BM-06 / D-14: three EventNotBettable branches (event not found / deadline /
state != NEW).
BM-05 / D-04 / D-19: amount quantization round-trip (e.g., '10' -> '10.00').
D-14 / Anti-Pattern 5: model_validate inside session (A1 mitigation --
no MissingGreenlet on returned BetRead).
Critical Risk Axis 1 (Decimal precision) + Axis 9 (ordering -- verified in test_selectors).
Validation MUST happen BEFORE UoW open -- test_no_db_write_on_validation_fail
verifies failed validation produces zero DB writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bet_maker.facades.event_lookup import EventSnapshot, StubEventLookup
from bet_maker.interactors.place_bet import EventNotBettable, place_bet
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead, BetStatus
from bet_maker.schemas.events import EventState
from bet_maker.uow.postgres import PostgresUnitOfWork


@pytest.mark.asyncio(loop_scope="session")
class TestHappyPath:
    """BM-05: happy path inserts bet with PENDING status."""

    async def test_returns_betread_with_pending_status(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """BM-05 / D-14: place_bet returns BetRead, status=PENDING, server_default
        created_at populated via refresh."""
        event_id = uuid4()
        lookup = StubEventLookup()
        lookup.seed_active(event_id)
        uow = PostgresUnitOfWork(session_factory)

        read = await place_bet(
            uow,
            event_id=event_id,
            amount=Decimal("10.00"),
            event_lookup=lookup,
        )

        assert isinstance(read, BetRead)
        assert read.event_id == event_id
        assert read.status == BetStatus.PENDING
        assert read.amount == Decimal("10.00")
        assert isinstance(read.id, UUID)
        assert read.created_at is not None

    async def test_amount_quantized_to_two_places(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """D-04 / D-19: input Decimal('10') stored as '10.00' (quantize_amount)."""
        event_id = uuid4()
        lookup = StubEventLookup()
        lookup.seed_active(event_id)
        uow = PostgresUnitOfWork(session_factory)

        read = await place_bet(
            uow,
            event_id=event_id,
            amount=Decimal("10"),
            event_lookup=lookup,
        )

        assert read.amount == Decimal("10.00")
        assert str(read.amount) == "10.00"

    async def test_persists_to_db(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """BM-05: UoW commits on clean exit -- second session sees the bet."""
        event_id = uuid4()
        lookup = StubEventLookup()
        lookup.seed_active(event_id)
        uow = PostgresUnitOfWork(session_factory)

        read = await place_bet(
            uow,
            event_id=event_id,
            amount=Decimal("5.00"),
            event_lookup=lookup,
        )

        async with session_factory() as session:
            fetched = (
                await session.execute(select(Bet).where(Bet.id == read.id))
            ).scalar_one_or_none()
            assert fetched is not None
            assert fetched.event_id == event_id


@pytest.mark.asyncio(loop_scope="session")
class TestRejections:
    """BM-06 / D-14: three EventNotBettable branches."""

    async def test_event_not_found_raises(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """D-06: event_lookup.get_event returns None -> 'event not found'."""
        lookup = StubEventLookup()
        uow = PostgresUnitOfWork(session_factory)

        with pytest.raises(EventNotBettable) as exc:
            await place_bet(
                uow,
                event_id=uuid4(),
                amount=Decimal("10.00"),
                event_lookup=lookup,
            )
        assert exc.value.reason == "event not found"

    async def test_deadline_passed_raises(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """deadline <= now -> 'deadline passed'."""
        event_id = uuid4()
        lookup = StubEventLookup()
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        lookup.seed(EventSnapshot(event_id=event_id, deadline=past, state=EventState.NEW))
        uow = PostgresUnitOfWork(session_factory)

        with pytest.raises(EventNotBettable) as exc:
            await place_bet(
                uow,
                event_id=event_id,
                amount=Decimal("10.00"),
                event_lookup=lookup,
            )
        assert exc.value.reason == "deadline passed"

    async def test_state_not_new_raises(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """D-14: state != NEW (FINISHED_WIN/FINISHED_LOSE) -> 'event not active'."""
        event_id = uuid4()
        lookup = StubEventLookup()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        lookup.seed(
            EventSnapshot(event_id=event_id, deadline=future, state=EventState.FINISHED_WIN)
        )
        uow = PostgresUnitOfWork(session_factory)

        with pytest.raises(EventNotBettable) as exc:
            await place_bet(
                uow,
                event_id=event_id,
                amount=Decimal("10.00"),
                event_lookup=lookup,
            )
        assert exc.value.reason == "event not active"

    async def test_no_db_write_on_validation_fail(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """D-14: validation raises BEFORE UoW open -- DB stays empty.

        If validation were INSIDE async with uow:, async_sessionmaker.begin()
        would auto-rollback on exception -- same observable end-state, but
        the begin/rollback cycle would still acquire a connection from the
        pool. The test guards: no row appeared even transiently.
        """
        lookup = StubEventLookup()
        uow = PostgresUnitOfWork(session_factory)

        with pytest.raises(EventNotBettable):
            await place_bet(
                uow,
                event_id=uuid4(),
                amount=Decimal("10.00"),
                event_lookup=lookup,
            )

        async with session_factory() as session:
            count = (await session.execute(select(func.count()).select_from(Bet))).scalar_one()
            assert count == 0
