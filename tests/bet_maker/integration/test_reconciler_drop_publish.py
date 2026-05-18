"""Wave-0 stub — Plan 06-09. Target req: BM-12, SC#1.

Replace pytest.fail(...) with real assertions when Plan 06-09 implements
respx-mocked drop-publish reconciler scenario in tests/bet_maker/integration/.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerDropPublish:
    async def test_respx_mocked_lp_terminal_state_triggers_reconciler_settle(self) -> None:
        pytest.fail(
            "Wave-0 stub for Plan 06-09 — drop-publish reconciler integration not yet implemented"
        )

    async def test_respx_mocked_lp_404_triggers_reconciler_cancel(self) -> None:
        pytest.fail(
            "Wave-0 stub for Plan 06-09 — drop-publish reconciler integration not yet implemented"
        )

    async def test_reconciler_skip_when_lp_still_returns_new(self) -> None:
        pytest.fail(
            "Wave-0 stub for Plan 06-09 — drop-publish reconciler integration not yet implemented"
        )
