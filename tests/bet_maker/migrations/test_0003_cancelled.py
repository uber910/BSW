"""Alembic migration 0003 -- bet_status CANCELLED ADD VALUE assertions.

Phase 6 / Plan 06-03 / BM-12.

apply_migrations (tests/conftest.py) runs `alembic upgrade head` twice;
by the time `async_engine` yields, revision 0003 is applied AND the
rerun-idempotency has been verified at fixture setup. These tests assert
the post-conditions visible to bet_maker code.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio(loop_scope="session")
class TestMigration0003:
    async def test_alter_type_adds_cancelled_value(self, async_engine: AsyncEngine) -> None:
        """The PG bet_status ENUM contains 'cancelled' after migration."""
        query = sa.text(
            "SELECT enumlabel FROM pg_enum "
            "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'bet_status' "
            "ORDER BY enumsortorder"
        )
        async with async_engine.connect() as conn:
            rows = (await conn.execute(query)).scalars().all()
        assert "cancelled" in rows
        assert set(rows) == {"PENDING", "WON", "LOST", "cancelled"}

    async def test_migration_is_idempotent_on_rerun(self, async_engine: AsyncEngine) -> None:
        """apply_migrations fixture runs upgrade head twice (tests/conftest.py).

        If the migration were not idempotent, fixture setup would have
        already raised. Reaching this test body is the proof -- assert
        schema state is the post-migration shape.
        """
        query = sa.text(
            "SELECT count(*) FROM pg_enum "
            "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'bet_status'"
        )
        async with async_engine.connect() as conn:
            count = (await conn.execute(query)).scalar_one()
        assert count == 4

    async def test_autocommit_block_used(self) -> None:
        """RESEARCH Pitfall 1: autocommit_block is REQUIRED for ALTER TYPE
        ADD VALUE; otherwise psycopg2/asyncpg raises ActiveSqlTransaction.

        Static-introspect the migration source -- the public API
        `op.get_context().autocommit_block()` MUST appear inside upgrade().
        """
        migration_path = (
            Path(__file__).parents[3]
            / "alembic"
            / "versions"
            / "20260518_0003_bet_status_cancelled.py"
        )
        source = migration_path.read_text(encoding="utf-8")
        assert "autocommit_block" in source, (
            "Plan 06-03: migration 0003 must use op.get_context().autocommit_block()"
        )
        assert "ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'" in source
