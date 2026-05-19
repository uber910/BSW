"""Unit tests for bet_maker.selectors.list_bets + get_bet.

``list_bets`` returns ``list[BetRead]`` sorted by ``created_at`` DESC.
``get_bet_by_id`` returns ``BetRead`` or ``None`` (router maps ``None``
to 404). Selectors return DTOs (``BetRead``), never ORM instances.

``GET /bets`` ordering under ``server_default created_at`` is verified
via 3 bets inserted in known order; ``list_bets`` returns them in
DESC order.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead, BetStatus
from bet_maker.selectors.get_bet import get_bet_by_id
from bet_maker.selectors.list_bets import list_bets


@pytest.mark.asyncio(loop_scope="session")
class TestListBets:
    """list_bets ordering and shape invariants."""

    async def test_returns_empty_list_when_no_bets(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Empty table -> []."""
        async with session_factory() as session:
            bets = await list_bets(session)
            assert bets == []

    async def test_orders_by_created_at_desc(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Newest first.

        Insert 3 bets with small sleeps between flushes -- ``server_default
        func.now()`` assigns increasing timestamps. ``list_bets`` returns
        them with the newest (last inserted) first.
        """
        inserted_ids = []
        for i in range(3):
            async with session_factory.begin() as session:
                bet = Bet(event_id=uuid4(), amount=Decimal(f"{i + 1}.00"))
                session.add(bet)
                await session.flush()
                await session.refresh(bet)
                inserted_ids.append(bet.id)
            await asyncio.sleep(0.01)

        async with session_factory() as session:
            bets = await list_bets(session)

        assert len(bets) == 3
        assert [b.id for b in bets] == list(reversed(inserted_ids))

    async def test_returns_betread_dto_not_orm(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """list_bets returns BetRead, not ORM Bet instances."""
        async with session_factory.begin() as session:
            bet = Bet(event_id=uuid4(), amount=Decimal("1.00"))
            session.add(bet)
            await session.flush()

        async with session_factory() as session:
            bets = await list_bets(session)
            assert all(isinstance(b, BetRead) for b in bets)
            assert not any(isinstance(b, Bet) for b in bets)


@pytest.mark.asyncio(loop_scope="session")
class TestGetBetById:
    """get_bet_by_id happy / miss / DTO-shape."""

    async def test_returns_betread_for_existing(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Existing bet -> BetRead with correct fields."""
        event_id = uuid4()
        async with session_factory.begin() as session:
            bet = Bet(event_id=event_id, amount=Decimal("5.50"))
            session.add(bet)
            await session.flush()
            await session.refresh(bet)
            bet_id = bet.id

        async with session_factory() as session:
            read = await get_bet_by_id(session, bet_id)

        assert read is not None
        assert isinstance(read, BetRead)
        assert read.id == bet_id
        assert read.event_id == event_id
        assert read.amount == Decimal("5.50")
        assert read.status == BetStatus.PENDING

    async def test_returns_none_for_missing(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Unknown id -> None (router maps to 404)."""
        async with session_factory() as session:
            read = await get_bet_by_id(session, uuid4())
            assert read is None

    async def test_amount_is_decimal_with_two_places(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """BetRead.amount preserves '10.00' string form."""
        async with session_factory.begin() as session:
            bet = Bet(event_id=uuid4(), amount=Decimal("10.00"))
            session.add(bet)
            await session.flush()
            bet_id = bet.id

        async with session_factory() as session:
            read = await get_bet_by_id(session, bet_id)

        assert read is not None
        assert str(read.amount) == "10.00"
