"""Unit tests for bet_maker.repositories.bets.

BM-02 / D-18: BetRepository.add(bet) — session.add only (no flush, no commit).
BM-02 / D-18: BetRepository.get_by_id(bet_id) — select + scalar_one_or_none.
Anti-Pattern 1: repository MUST NOT commit/rollback (UoW owns transactions).
"""

from __future__ import annotations

import inspect
import re
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.models.bet import Bet
from bet_maker.repositories.bets import BetRepository


class TestAntiPattern1:
    """Anti-Pattern 1: repository MUST NOT commit/rollback.

    Grep-level guard plus introspection — if a future contributor adds
    `await session.commit()` to add/get_by_id, this catches it.
    """

    def test_source_has_no_commit(self) -> None:
        """No `session.commit()` / `session.rollback()` calls in repository source."""
        source = inspect.getsource(BetRepository)
        assert not re.search(r"session\s*\.\s*commit\s*\(", source), source
        assert not re.search(r"session\s*\.\s*rollback\s*\(", source), source


@pytest.mark.asyncio(loop_scope="session")
class TestRuntime:
    """BM-02: BetRepository against testcontainers PG via session_factory."""

    async def test_add_stages_bet_in_session(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """D-18: .add() calls session.add — does NOT flush. The bet is
        in `session.new` but not yet persisted."""
        async with session_factory() as session:
            repo = BetRepository(session)
            bet = Bet(event_id=uuid4(), amount=Decimal("10.00"))
            repo.add(bet)
            assert bet in session.new

    async def test_add_then_flush_then_get_by_id_roundtrip(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """BM-02: add → flush → get_by_id returns the same bet inside session."""
        async with session_factory.begin() as session:
            repo = BetRepository(session)
            bet = Bet(event_id=uuid4(), amount=Decimal("5.50"))
            repo.add(bet)
            await session.flush()
            fetched = await repo.get_by_id(bet.id)
            assert fetched is not None
            assert fetched.id == bet.id

    async def test_get_by_id_returns_none_for_unknown(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """D-18: missing bet → None (not exception)."""
        async with session_factory() as session:
            repo = BetRepository(session)
            fetched = await repo.get_by_id(uuid4())
            assert fetched is None

    async def test_add_does_not_flush_implicitly(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """D-18 / PATTERNS.md: .add() does NOT flush; caller controls flush
        timing. Verified by checking the bet is still in session.new (not
        session.persistent) after .add() but before .flush()."""
        async with session_factory() as session:
            repo = BetRepository(session)
            bet = Bet(event_id=uuid4(), amount=Decimal("1.00"))
            repo.add(bet)
            assert bet in session.new
            assert bet not in session.identity_map.values()
