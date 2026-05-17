"""settle_bets_for_event interactor tests — Plan 05-04 (D-12 .. D-18).

Covers (per VALIDATION.md task IDs 05-04-01, 05-04-02):
- Happy path (settle_count == row count)
- Idempotency (second call on same event_id is 0-row noop)
- Concurrent settle (R3 / consumer-vs-reconciler race)
- SettleResult shape (frozen, UTC-aware settled_at)

All tests run against real PG testcontainer (QA-07). SQLite would not
support FOR UPDATE SKIP LOCKED — this entire file's coverage would be
fictional under SQLite.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.messages import EventTerminalState


@pytest.mark.asyncio(loop_scope="session")
class TestSettleHappyPath:
    async def test_settles_three_pending_bets_to_won_when_terminal_win(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))
        result = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        assert result.settled_count == 3
        assert len(result.settled_bet_ids) == 3
        assert result.settled_via == "consumer"

        async with session_factory() as session:
            rows = (
                (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalars().all()
            )
        assert len(rows) == 3
        assert all(b.status == BetStatus.WON for b in rows)
        assert all(b.settled_at is not None for b in rows)
        assert all(b.settled_via == "consumer" for b in rows)

    async def test_settles_to_lost_when_terminal_lose(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        result = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_LOSE,
            settled_via="consumer",
        )
        assert result.settled_count == 1
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.LOST


@pytest.mark.asyncio(loop_scope="session")
class TestSettleNoop:
    async def test_idempotent_second_call_returns_zero(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
            session.add(Bet(event_id=event_id, amount=Decimal("20.00")))

        first = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        second = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        assert first.settled_count == 2
        assert second.settled_count == 0
        assert second.settled_bet_ids == []

    async def test_noop_when_no_pending_for_event(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00"), status=BetStatus.WON))
        result = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        assert result.settled_count == 0
        assert result.settled_bet_ids == []

    async def test_noop_when_event_has_only_other_events_bets(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_a, event_b = uuid4(), uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_a, amount=Decimal("10.00")))
        result = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_b,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        assert result.settled_count == 0
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_a))).scalar_one()
        assert bet.status == BetStatus.PENDING


@pytest.mark.asyncio(loop_scope="session")
class TestSettleConcurrent:
    async def test_concurrent_no_double_update(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """R3 / D-12: consumer + reconciler against same event_id together
        settle exactly once. SKIP LOCKED -> one task gets all rows, the
        other gets 0 rows."""
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))

        r1, r2 = await asyncio.gather(
            settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            ),
            settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="reconciler",
            ),
        )
        assert r1.settled_count + r2.settled_count == 3
        async with session_factory() as session:
            pending = (
                (
                    await session.execute(
                        select(Bet).where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
                    )
                )
                .scalars()
                .all()
            )
            settled = (
                (
                    await session.execute(
                        select(Bet).where(Bet.event_id == event_id, Bet.status == BetStatus.WON)
                    )
                )
                .scalars()
                .all()
            )
        assert len(pending) == 0
        assert len(settled) == 3

    async def test_concurrent_settled_via_attribution_is_single_pass(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Strong R3 form: exactly ONE task settled rows, the other got 0."""
        event_id = uuid4()
        async with session_factory.begin() as session:
            for amt in ("10.00", "20.00", "30.00"):
                session.add(Bet(event_id=event_id, amount=Decimal(amt)))

        r1, r2 = await asyncio.gather(
            settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="consumer",
            ),
            settle_bets_for_event(
                AsyncUnitOfWork(session_factory),
                event_id=event_id,
                terminal_state=EventTerminalState.FINISHED_WIN,
                settled_via="reconciler",
            ),
        )
        counts = sorted([r1.settled_count, r2.settled_count])
        assert counts == [0, 3], f"expected exactly one task to settle all 3 rows, got {counts}"


@pytest.mark.asyncio(loop_scope="session")
class TestSettleResultShape:
    async def test_settle_result_is_frozen(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        result = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        with pytest.raises(ValidationError):
            result.settled_count = 999  # type: ignore[misc]

    async def test_settle_result_settled_at_is_utc_aware(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        result = await settle_bets_for_event(
            AsyncUnitOfWork(session_factory),
            event_id=event_id,
            terminal_state=EventTerminalState.FINISHED_WIN,
            settled_via="consumer",
        )
        assert result.settled_at.tzinfo is not None
