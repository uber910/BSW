"""E2E stub — real RabbitMQ via testcontainers.

Implementation lands in Plan 05-09. D-31 / QA-06 / F6.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_e2e_consumer_settles_bet_placeholder() -> None:
    pytest.skip("Wave 0 stub — filled by Plan 05-09 (e2e real-RabbitMQ test)")
