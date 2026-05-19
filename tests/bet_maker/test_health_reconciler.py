"""/health reconciler-check tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
class TestHealthReconciler:
    async def test_health_200_when_reconciler_task_alive(self, client: AsyncClient) -> None:
        """Under the session-scoped `app` fixture the reconciler task is
        sleeping (default interval 30s); /health should return 200 and
        checks.reconciler should be 'ok'."""
        response = await client.get("/health")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["checks"]["reconciler"] == "ok"

    async def test_health_503_when_reconciler_task_done(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """Override the reconciliation task with a stub whose .done() is True;
        GET /health returns 503 + reconciler: 'dead'."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from bet_maker.facades.deps import get_reconciliation_task  # noqa: PLC0415

        fake_done_task = MagicMock()
        fake_done_task.done.return_value = True
        app.dependency_overrides[get_reconciliation_task] = lambda: fake_done_task
        try:
            response = await client.get("/health")
        finally:
            app.dependency_overrides.pop(get_reconciliation_task, None)
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["reconciler"] == "dead"

    async def test_health_body_reports_reconciler_check_key(self, client: AsyncClient) -> None:
        """The `reconciler` key is always present in the checks dict."""
        response = await client.get("/health")
        body = response.json()
        assert "reconciler" in body["checks"]
