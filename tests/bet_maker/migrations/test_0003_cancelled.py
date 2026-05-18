"""Wave-0 stub — Plan 06-03. Target req: BM-05.

Replace pytest.fail(...) with real assertions when Plan 06-03 implements
Alembic 0003 ALTER TYPE migration for BetStatus.CANCELLED.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestMigration0003:
    async def test_alter_type_adds_cancelled_value(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-03 — Alembic 0003 ALTER TYPE not yet implemented")

    async def test_migration_is_idempotent_on_rerun(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-03 — Alembic 0003 ALTER TYPE not yet implemented")

    async def test_autocommit_block_used(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-03 — Alembic 0003 ALTER TYPE not yet implemented")
