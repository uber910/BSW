"""Wave-0 stub — Plan 06-08. Target req: BM-12, SC#3.

Replace pytest.fail(...) with real assertions when Plan 06-08 implements
reconciler task health check in src/bet_maker/entrypoints/api/health.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestHealthReconciler:
    async def test_health_200_when_reconciler_task_alive(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciler health check not yet implemented")

    async def test_health_503_when_reconciler_task_done(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciler health check not yet implemented")

    async def test_health_body_reports_reconciler_check_key(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-08 — reconciler health check not yet implemented")
