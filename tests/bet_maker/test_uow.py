"""Unit tests for bet_maker.facades.uow.AsyncUnitOfWork.

BM-02 / D-17: AsyncUnitOfWork over async_sessionmaker.begin().
Commit on clean __aexit__; rollback on exception.
Critical Risk Axis 3 (RESEARCH §Validation): per-request UoW isolation
under concurrency — verified via asyncio.gather over 5 UoWs.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.models.bet import Bet


@pytest.mark.asyncio(loop_scope="session")
class TestShape:
    """D-17: UoW exposes session + bets, no manual commit method."""

    async def test_aenter_exposes_session_and_bets(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """D-17: `async with uow:` → uow.session + uow.bets available."""
        async with AsyncUnitOfWork(session_factory) as uow:
            assert uow.session is not None
            assert uow.bets is not None
            assert uow.bets._session is uow.session

    async def test_uow_has_no_public_commit_or_rollback(self) -> None:
        """D-17 / Anti-Pattern 1: no manual commit/rollback methods exposed."""
        for forbidden in ("commit", "rollback"):
            assert not hasattr(AsyncUnitOfWork, forbidden), forbidden


@pytest.mark.asyncio(loop_scope="session")
class TestTransactionSemantics:
    """BM-02 / D-17: commit on clean exit, rollback on exception."""

    async def test_commit_on_clean_exit(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Clean exit → INSERT committed → second UoW sees the bet."""
        event_id = uuid4()
        async with AsyncUnitOfWork(session_factory) as uow:
            bet = Bet(event_id=event_id, amount=Decimal("10.00"))
            uow.bets.add(bet)
            await uow.session.flush()
            bet_id = bet.id

        async with AsyncUnitOfWork(session_factory) as uow2:
            fetched = await uow2.bets.get_by_id(bet_id)
            assert fetched is not None
            assert fetched.event_id == event_id

    async def test_rollback_on_exception(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Exception inside `async with uow:` → rollback → second UoW sees nothing."""
        event_id = uuid4()
        captured_id = None
        with pytest.raises(RuntimeError, match="forced rollback"):
            async with AsyncUnitOfWork(session_factory) as uow:
                bet = Bet(event_id=event_id, amount=Decimal("10.00"))
                uow.bets.add(bet)
                await uow.session.flush()
                captured_id = bet.id
                raise RuntimeError("forced rollback")

        assert captured_id is not None
        async with AsyncUnitOfWork(session_factory) as uow2:
            fetched = await uow2.bets.get_by_id(captured_id)
            assert fetched is None


@pytest.mark.asyncio(loop_scope="session")
class TestConcurrency:
    """Critical Risk Axis 3: per-request UoW isolation."""

    async def test_concurrent_uows_isolated(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Pitfall A2: 5 parallel UoWs each commit their own session
        independently. asyncio.gather over independent UoWs must not
        interfere or deadlock."""

        async def place_one(value: str) -> Bet:
            async with AsyncUnitOfWork(session_factory) as uow:
                bet = Bet(event_id=uuid4(), amount=Decimal(value))
                uow.bets.add(bet)
                await uow.session.flush()
                await uow.session.refresh(bet)
                return bet

        results = await asyncio.gather(*[place_one(f"{i + 1}.00") for i in range(5)])
        assert len({b.id for b in results}) == 5, "all UoWs must produce distinct bets"
        assert {str(b.amount) for b in results} == {"1.00", "2.00", "3.00", "4.00", "5.00"}
