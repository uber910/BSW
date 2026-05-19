"""Unit tests for bet_maker.models.bet.

Bet model: id UUID PK (``uuid.uuid4`` default), event_id UUID (no FK),
amount ``Numeric(12,2)``, status PG-ENUM bet_status (default PENDING),
``created_at``/``updated_at`` ``server_default=func.now()`` + ``onupdate``.
There is no coefficient column.

After flush, ``server_default`` fields are ``None`` until
``await session.refresh(bet)`` loads them. The ``place_bet`` interactor
relies on this — test guards the contract. ``Numeric(12,2)`` + asyncpg
preserve Decimal exactly (``asdecimal=True`` default).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Numeric
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.models import Base, Bet
from bet_maker.schemas.bets import BetStatus


class TestSchema:
    """Bet table schema invariants."""

    def test_tablename(self) -> None:
        """__tablename__ == 'bets'."""
        assert Bet.__tablename__ == "bets"

    def test_amount_numeric_12_2(self) -> None:
        """amount is NUMERIC(12,2), asdecimal=True."""
        amount_col = Bet.__table__.c.amount
        assert str(amount_col.type).upper() == "NUMERIC(12, 2)"
        numeric_type = amount_col.type
        assert isinstance(numeric_type, Numeric)
        assert numeric_type.precision == 12
        assert numeric_type.scale == 2
        assert numeric_type.asdecimal is True
        assert amount_col.nullable is False

    def test_status_is_pg_enum_bet_status(self) -> None:
        """status is PG-native ENUM 'bet_status'."""
        status_col = Bet.__table__.c.status
        enum_type = status_col.type
        assert isinstance(enum_type, SqlEnum)
        assert enum_type.name == "bet_status"
        assert status_col.nullable is False

    def test_event_id_has_no_fk(self) -> None:
        """event_id is UUID but NO FK -- events live in line-provider."""
        event_id_col = Bet.__table__.c.event_id
        assert event_id_col.foreign_keys == set()
        assert event_id_col.nullable is False

    def test_id_default_is_uuid4(self) -> None:
        """id default = uuid.uuid4 (Python-side, matches event_id pattern)."""
        default_fn = Bet.__table__.c.id.default.arg
        assert callable(default_fn)
        assert default_fn.__module__ == uuid.__name__
        assert default_fn.__qualname__ == "uuid4"
        assert Bet.__table__.c.id.primary_key is True

    def test_created_at_server_default(self) -> None:
        """created_at has server_default (DDL-level NOW())."""
        assert Bet.__table__.c.created_at.server_default is not None
        assert Bet.__table__.c.created_at.nullable is False

    def test_updated_at_server_default_and_onupdate(self) -> None:
        """updated_at has BOTH server_default AND onupdate."""
        assert Bet.__table__.c.updated_at.server_default is not None
        assert Bet.__table__.c.updated_at.onupdate is not None
        assert Bet.__table__.c.updated_at.nullable is False

    def test_no_coefficient_column(self) -> None:
        """coefficient is NOT a column on Bet (per TZ page 3)."""
        assert "coefficient" not in Bet.__table__.c

    def test_base_metadata_contains_only_bets(self) -> None:
        """Only one table in the bet_maker schema -- bets."""
        assert set(Base.metadata.tables) == {"bets"}


@pytest.mark.asyncio(loop_scope="session")
class TestRuntime:
    """Bet INSERT against testcontainers PG + refresh."""

    async def test_insert_and_refresh_loads_server_defaults(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """After flush, ``server_default`` fields are ``None`` until
        ``refresh()``. The ``place_bet`` interactor calls refresh — this
        test guards that contract.
        """
        event_id = uuid4()
        async with session_factory.begin() as session:
            bet = Bet(event_id=event_id, amount=Decimal("10.00"))
            session.add(bet)
            await session.flush()
            await session.refresh(bet)
            assert bet.created_at is not None
            assert bet.updated_at is not None
            assert bet.status == BetStatus.PENDING
            assert bet.amount == Decimal("10.00")
            assert isinstance(bet.id, UUID)
            assert bet.event_id == event_id

    async def test_decimal_roundtrip_exact(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Numeric(12,2) + asyncpg -> Decimal round-trip is exact.

        "10.00" -> DB -> "10.00" with two decimal places.
        """
        async with session_factory.begin() as session:
            bet = Bet(event_id=uuid4(), amount=Decimal("10.00"))
            session.add(bet)
            await session.flush()
            await session.refresh(bet)
            assert bet.amount == Decimal("10.00")
            assert str(bet.amount) == "10.00"

    async def test_default_status_pending(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """status default = BetStatus.PENDING (Python-side ORM default)."""
        async with session_factory.begin() as session:
            bet = Bet(event_id=uuid4(), amount=Decimal("5.50"))
            session.add(bet)
            await session.flush()
            await session.refresh(bet)
            assert bet.status == BetStatus.PENDING
