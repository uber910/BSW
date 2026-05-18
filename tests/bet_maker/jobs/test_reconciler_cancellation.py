"""Wave-0 stub — Plan 06-07. Target req: BM-12.

Replace pytest.fail(...) with real assertions when Plan 06-07 implements
CancelledError propagation in src/bet_maker/jobs/reconciler.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerCancellation:
    async def test_cancelled_error_propagates_out_of_loop(self) -> None:
        pytest.fail(
            "Wave-0 stub for Plan 06-07 — reconciliation_loop CancelledError not yet implemented"
        )

    async def test_task_cancel_then_await_terminates_cleanly(self) -> None:
        pytest.fail(
            "Wave-0 stub for Plan 06-07 — reconciliation_loop CancelledError not yet implemented"
        )

    async def test_cancelled_error_logged_then_reraised(self) -> None:
        pytest.fail(
            "Wave-0 stub for Plan 06-07 — reconciliation_loop CancelledError not yet implemented"
        )
