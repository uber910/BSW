"""Wave-0 stub — Plan 06-07. Target req: BM-12.

Replace pytest.fail(...) with real assertions when Plan 06-07 implements
src/bet_maker/jobs/reconciler.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerTick:
    async def test_run_tick_settles_finished_win_events(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

    async def test_run_tick_cancels_404_events(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

    async def test_run_tick_skips_new_state_events(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

    async def test_run_tick_noop_when_no_pending(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

    async def test_per_event_exception_isolation(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

    async def test_sleep_before_first_tick(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerErrorIsolation:
    async def test_loop_continues_after_tick_exception(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — reconciliation_loop not yet implemented")

    async def test_loop_does_not_catch_basesystem_exits(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-07 — reconciliation_loop not yet implemented")
