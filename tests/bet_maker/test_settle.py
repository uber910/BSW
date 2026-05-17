"""Stub for settle_bets_for_event interactor + concurrent settle race.

Implementation lands in Plan 05-04. D-12 / D-17 / D-18.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_idempotent_placeholder() -> None:
    pytest.skip("Wave 0 stub — filled by Plan 05-04 (settle interactor)")


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_no_double_update_placeholder() -> None:
    pytest.skip("Wave 0 stub — filled by Plan 05-04 (settle interactor)")
