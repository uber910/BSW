"""Wave 0 stub — implemented in plan 03-06.

BM-02 / D-17: AsyncUnitOfWork commits on clean __aexit__, rolls back
on exception inside `async with uow:` block. Test invariant: bet created
inside failing UoW NOT visible after rollback (assert get_by_id returns None).
Risk axis 3 (RESEARCH §Critical Risk Axes): concurrent UoWs isolated via
asyncio.gather over 5 UoWs — each commits its own session, no shared state.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-06")
