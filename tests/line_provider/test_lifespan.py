"""Lifespan stub for line-provider broker.connect ordering.

Implementation lands in Plan 05-07. D-24.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_event_bus_is_rabbit_in_production_placeholder() -> None:
    pytest.skip("Wave 0 stub — filled by Plan 05-07 (lifespan composition)")
