"""Migration idempotency tests.

`alembic upgrade head` applies the initial migration and rerun is idempotent.

Without `ENUM.create(checkfirst=True)` and `create_type=False` inside
`postgresql.ENUM(...)`, the second `upgrade head` would raise
`sqlalchemy.exc.ProgrammingError: type "bet_status" already exists`.

testcontainers PG is session-scoped; `apply_migrations` fixture already calls
`command.upgrade(cfg, "head")` TWICE inside its body. This test adds a third
call to assert robustness, plus inspects pg_type and information_schema.tables
to verify side effects.
"""

from __future__ import annotations

import asyncio
import functools

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio(loop_scope="session")
class TestMigration:
    """alembic upgrade head + idempotency rerun + side-effect verification."""

    async def test_bets_table_exists_after_migration(self, async_engine: AsyncEngine) -> None:
        """bets table is created by 0001_bets_initial migration."""
        async with async_engine.begin() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'bets'"
                )
            )
            assert result.scalar_one() == 1

    async def test_bet_status_enum_exists_after_migration(self, async_engine: AsyncEngine) -> None:
        """bet_status ENUM type is created by .create(checkfirst=True)."""
        async with async_engine.begin() as conn:
            result = await conn.execute(
                sa.text("SELECT typname FROM pg_type WHERE typname = 'bet_status'")
            )
            assert result.scalar_one() == "bet_status"

    async def test_bet_status_enum_has_four_values(self, async_engine: AsyncEngine) -> None:
        async with async_engine.begin() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT enumlabel FROM pg_enum "
                    "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                    "WHERE pg_type.typname = 'bet_status' "
                    "ORDER BY pg_enum.enumsortorder"
                )
            )
            labels = [row[0] for row in result.all()]
            assert labels == ["PENDING", "WON", "LOST", "CANCELLED"]

    def test_upgrade_head_third_run_idempotent(self, pg_dsn: str, apply_migrations: None) -> None:
        """Third invocation of `alembic upgrade head` is also a no-op.

        apply_migrations already calls upgrade head TWICE inside its body --
        this is a third call. If the recipe (`checkfirst=True` + `create_type=False`)
        were broken, this call would raise `type "bet_status" already exists`.
        """
        _ = apply_migrations
        cfg = Config("src/bet_maker/alembic.ini")
        cfg.set_main_option("sqlalchemy.url", pg_dsn)
        command.upgrade(cfg, "head")

    async def test_0002_upgrade_downgrade_upgrade_columns_present(
        self,
        async_engine: AsyncEngine,
        pg_dsn: str,
        apply_migrations: None,
    ) -> None:
        """Migration must round-trip: downgrade -1 -> upgrade head;
        after final upgrade, settled_at and settled_via columns are present in bets.

        Runs alembic commands in a thread executor to avoid the asyncio.run()
        clash with pytest-asyncio's running event loop (alembic env.py calls
        asyncio.run() for the async migration driver).
        """
        _ = apply_migrations
        alembic_cfg = Config("src/bet_maker/alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", pg_dsn)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(command.downgrade, alembic_cfg, "-1"))
        await loop.run_in_executor(None, functools.partial(command.upgrade, alembic_cfg, "head"))

        async with async_engine.connect() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'bets' "
                        "AND column_name IN ('settled_at', 'settled_via')"
                    )
                )
            ).all()
        names = {r[0] for r in rows}
        assert names == {"settled_at", "settled_via"}
