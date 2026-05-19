"""Smoke test: /asyncapi endpoint is exposed by FastStream RabbitRouter.

FastStream RabbitRouter auto-registers /asyncapi at its default URL when
app.include_router(router) is called. A regression that comments out the
include_router line would silently strip the endpoint — this smoke test
catches that.

Content-type may be HTML (AsyncAPI rendering UI) or JSON depending on
FastStream version; both are acceptable. The assertion is on status
code + non-empty body + content-type contains "html" or "json".
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
class TestAsyncAPISmoke:
    """AsyncAPI endpoint smoke test — session loop for session-scoped client."""

    async def test_asyncapi_endpoint_returns_200(self, client: AsyncClient) -> None:
        """/asyncapi must return 200 with non-empty body."""
        response = await client.get("/asyncapi")
        assert response.status_code == 200, (
            f"GET /asyncapi returned {response.status_code} — "
            "FastStream RabbitRouter not wired? "
            "See src/bet_maker/app.py::build_app — app.include_router(rabbit_router) "
            "is required."
        )
        assert response.content, "/asyncapi returned empty body"
        content_type = response.headers.get("content-type", "")
        assert any(t in content_type for t in ("html", "json")), (
            f"/asyncapi content-type not html or json: {content_type!r}"
        )
