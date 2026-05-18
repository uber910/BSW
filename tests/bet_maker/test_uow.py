"""Unit tests for bet_maker.uow.PostgresUnitOfWork.

BM-02 / D-17 / Phase 9 D-01..D-04: PostgresUnitOfWork over
async_sessionmaker.begin(). Commit on clean __aexit__; rollback on
exception. ``uow.session`` raises ``UnitOfWorkNotStartedError`` outside
the ``async with`` context (regression of a silent stale-session bug).

Critical Risk Axis 3 (RESEARCH §Validation): per-request UoW isolation
under concurrency -- verified via asyncio.gather over 5 UoWs.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.models.bet import Bet
from bet_maker.uow.abstract import AbstractUnitOfWork
from bet_maker.uow.postgres import PostgresUnitOfWork, UnitOfWorkNotStartedError


@pytest.mark.asyncio(loop_scope="session")
class TestShape:
    """PostgresUnitOfWork exposes session, no manual commit/rollback method."""

    async def test_aenter_exposes_session(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """async with uow: -> uow.session is a live AsyncSession."""
        async with PostgresUnitOfWork(session_factory) as uow:
            assert uow.session is not None

    async def test_session_raises_outside_context(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """uow.session access before __aenter__ -> UnitOfWorkNotStartedError."""
        uow = PostgresUnitOfWork(session_factory)
        with pytest.raises(UnitOfWorkNotStartedError):
            _ = uow.session

    async def test_session_raises_after_exit(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """uow.session access after __aexit__ -> UnitOfWorkNotStartedError.

        Was a silent stale-session bug under the old class; now an explicit
        runtime guard via the ``session`` property over ``_session: AsyncSession | None``.
        """
        async with PostgresUnitOfWork(session_factory) as uow:
            _ = uow.session  # valid inside context
        with pytest.raises(UnitOfWorkNotStartedError):
            _ = uow.session

    def test_uow_has_no_public_commit_or_rollback(self) -> None:
        """D-17 / Anti-Pattern 1: no manual commit/rollback on abstract or concrete."""
        for cls in (AbstractUnitOfWork, PostgresUnitOfWork):
            for forbidden in ("commit", "rollback"):
                assert not hasattr(cls, forbidden), f"{cls.__name__}.{forbidden}"


@pytest.mark.asyncio(loop_scope="session")
class TestTransactionSemantics:
    """BM-02 / D-17: commit on clean exit, rollback on exception."""

    async def test_commit_on_clean_exit(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Clean exit -> INSERT committed -> second UoW sees the bet."""
        event_id = uuid4()
        async with PostgresUnitOfWork(session_factory) as uow:
            bet = Bet(event_id=event_id, amount=Decimal("10.00"))
            uow.session.add(bet)
            await uow.session.flush()
            bet_id = bet.id

        async with PostgresUnitOfWork(session_factory) as uow2:
            result = await uow2.session.execute(select(Bet).where(Bet.id == bet_id))
            fetched = result.scalar_one_or_none()
            assert fetched is not None
            assert fetched.event_id == event_id

    async def test_rollback_on_exception(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Exception inside `async with uow:` -> rollback -> second UoW sees nothing."""
        event_id = uuid4()
        captured_id = None
        with pytest.raises(RuntimeError, match="forced rollback"):
            async with PostgresUnitOfWork(session_factory) as uow:
                bet = Bet(event_id=event_id, amount=Decimal("10.00"))
                uow.session.add(bet)
                await uow.session.flush()
                captured_id = bet.id
                raise RuntimeError("forced rollback")

        assert captured_id is not None
        async with PostgresUnitOfWork(session_factory) as uow2:
            result = await uow2.session.execute(select(Bet).where(Bet.id == captured_id))
            fetched = result.scalar_one_or_none()
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
            async with PostgresUnitOfWork(session_factory) as uow:
                bet = Bet(event_id=uuid4(), amount=Decimal(value))
                uow.session.add(bet)
                await uow.session.flush()
                await uow.session.refresh(bet)
                return bet

        results = await asyncio.gather(*[place_one(f"{i + 1}.00") for i in range(5)])
        assert len({b.id for b in results}) == 5, "all UoWs must produce distinct bets"
        assert {str(b.amount) for b in results} == {"1.00", "2.00", "3.00", "4.00", "5.00"}
