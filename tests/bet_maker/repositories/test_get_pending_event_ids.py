"""Wave-0 stub — Plan 06-05. Target req: BM-12.

Replace pytest.fail(...) with real assertions when Plan 06-05 implements
get_pending_event_ids in src/bet_maker/repositories/bets.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
class TestGetPendingEventIds:
    async def test_returns_distinct_event_ids_for_pending_bets(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-05 — get_pending_event_ids not yet implemented")

    async def test_excludes_won_lost_cancelled_bets(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-05 — get_pending_event_ids not yet implemented")

    async def test_returns_empty_list_when_no_pending(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-05 — get_pending_event_ids not yet implemented")

    async def test_no_commit_no_flush(self) -> None:
        pytest.fail("Wave-0 stub for Plan 06-05 — get_pending_event_ids not yet implemented")
