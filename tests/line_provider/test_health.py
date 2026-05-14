"""Smoke tests for line_provider /health endpoint.

QA-10: pytest must collect and pass green.
INFR-08: HTTP-level E2E proof of structlog request-id propagation via
RequestContextMiddleware — X-Request-ID is echoed back in response headers
(logging-side INFR-08 validated unit-wise in plan 02).
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_status_ok(client: AsyncClient) -> None:
    """QA-10: /health returns 200 with {"status": "ok"}."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_echoes_request_id_header(client: AsyncClient) -> None:
    """INFR-08 (HTTP-level E2E): RequestContextMiddleware binds request_id via
    bind_contextvars and echoes X-Request-ID header on response. Without correct
    middleware wiring (bind_contextvars + finally clear_contextvars), this fails.
    """
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0
