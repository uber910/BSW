"""Wave-0 stub — Plan 06-09. Target req: BM-12, SC#4.

Replace pytest.fail(...) with real assertions when Plan 06-09 implements
FOR UPDATE SKIP LOCKED concurrent-settle logic in src/bet_maker/interactors/.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerConsumerRace:
    async def test_concurrent_settle_consumer_and_reconciler_no_double_update(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-09 — FOR UPDATE SKIP LOCKED not yet implemented")

    async def test_for_update_skip_locked_one_winner_one_noop(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-09 — FOR UPDATE SKIP LOCKED not yet implemented")
