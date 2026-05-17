"""Unit stub for RabbitEventBus.publish correlation propagation.

Implementation lands in Plan 05-06. D-23 / Pitfall 6.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_publish_passes_correlation_id_placeholder() -> None:
    pytest.skip("Wave 0 stub — filled by Plan 05-06 (RabbitEventBus publisher)")
