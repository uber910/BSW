"""Wave-0 stub — Plan 06-08. Target req: BM-12, SC#3.

Replace pytest.fail(...) with real assertions when Plan 06-08 implements
reconciliation task lifecycle wiring in src/bet_maker/entrypoints/lifespan.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestLifespanReconciler:
    async def test_reconciler_event_lookup_pinned_on_state(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciliation_task lifespan not yet implemented")

    async def test_reconciliation_task_pinned_on_state(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciliation_task lifespan not yet implemented")

    async def test_task_name_is_reconciliation(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciliation_task lifespan not yet implemented")

    async def test_task_started_after_broker_connect(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciliation_task lifespan not yet implemented")

    async def test_task_cancelled_first_in_shutdown_finally(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciliation_task lifespan not yet implemented")
