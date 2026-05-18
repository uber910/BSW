"""Wave-0 stub — Plan 06-06. Target req: BM-05, BM-12.

Replace pytest.fail(...) with real assertions when Plan 06-06 implements
cancel_bets_for_event in src/bet_maker/interactors/cancel_bets_for_event.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestCancelHappyPath:
    async def test_cancels_two_pending_bets_to_cancelled_status(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")

    async def test_settled_via_is_reconciler(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")

    async def test_settled_at_is_filled(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")


@pytest.mark.asyncio(loop_scope="session")
class TestCancelNoop:
    async def test_idempotent_second_call_returns_zero(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")

    async def test_noop_when_no_pending_for_event(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")

    async def test_noop_when_only_already_cancelled_exist(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")


@pytest.mark.asyncio(loop_scope="session")
class TestCancelConcurrent:
    async def test_concurrent_with_settle_no_double_update(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")


@pytest.mark.asyncio(loop_scope="session")
class TestCancelResultShape:
    async def test_cancel_result_is_frozen(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")

    async def test_cancel_result_cancelled_at_is_utc_aware(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-06 — cancel_bets_for_event not yet implemented")
