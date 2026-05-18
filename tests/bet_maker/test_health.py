"""Tests for bet_maker /health endpoint.

QA-10: pytest must collect and pass green.
INFR-08: HTTP-level E2E proof of structlog request-id propagation via
RequestContextMiddleware — X-Request-ID is echoed back in response headers.
D-28: response shape updated: {status, checks: {postgres}} — not bare {status: ok}.
BM-08: 503 when PG engine pool is disposed (D-29 SQLAlchemyError -> False).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
class TestHealth:
    """Health endpoint tests — session loop for session-scoped app/client fixtures."""

    async def test_health_returns_status_ok(self, client: AsyncClient) -> None:
        """QA-10: /health returns 200 with all three checks ok (D-28/D-20).

        Shape: {status: ok, checks: {postgres, rabbitmq, rabbitmq_consumer}}.
        """
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["rabbitmq"] == "ok"
        assert body["checks"]["rabbitmq_consumer"] == "ok"

    async def test_health_echoes_request_id_header(self, client: AsyncClient) -> None:
        """INFR-08 (HTTP-level E2E): RequestContextMiddleware echoes X-Request-ID.

        Without correct middleware wiring, this fails. Unchanged from P1 baseline.
        """
        response = await client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    async def test_health_returns_503_when_pg_down(self, app: FastAPI, client: AsyncClient) -> None:
        """BM-08 / D-28: 503 + {status: degraded, checks: {postgres: down}} when PG unreachable.

        monkeypatch ping_postgres to return False — simulates pool closed / DSN changed.
        D-29: ping_postgres catches SQLAlchemyError and returns False; we test
        the route layer's response to False directly here.
        """
        with patch(
            "bet_maker.entrypoints.api.health.ping_postgres",
            new=AsyncMock(return_value=False),
        ):
            response = await client.get("/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["postgres"] == "down"

    async def test_health_returns_503_when_rmq_down(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """D-20 / SC#5: 503 when broker.ping fails (RMQ unreachable)."""
        from bet_maker.entrypoints.messaging import router  # noqa: PLC0415

        with patch.object(router.broker, "ping", new=AsyncMock(return_value=False)):
            response = await client.get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["rabbitmq"] == "down"
        assert body["checks"]["rabbitmq_consumer"] == "ok"

    async def test_health_returns_503_when_no_subscribers(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """D-20 / SC#5 / R6: 503 when len(broker.subscribers) == 0.

        broker.subscribers is a @property on Registrator base class, so
        patch.object must target the class (not instance) via PropertyMock.
        """
        from bet_maker.entrypoints.messaging import router  # noqa: PLC0415

        broker_type = type(router.broker)
        with patch.object(broker_type, "subscribers", new_callable=PropertyMock, return_value=[]):
            response = await client.get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["rabbitmq_consumer"] == "no subscribers"

    async def test_health_returns_200_includes_rabbitmq_checks(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """D-20: happy path returns 200 with all three checks 'ok'."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["rabbitmq"] == "ok"
        assert body["checks"]["rabbitmq_consumer"] == "ok"
