"""Smoke test: line-provider /asyncapi endpoint exposed by FastStream RabbitRouter.

line-provider's RabbitRouter (publisher-only — no ``@router.subscriber``)
still registers ``/asyncapi`` to document the publish contract. A
regression that comments out ``app.include_router(rabbit_router)`` in
``src/line_provider/app.py`` would silently strip the endpoint — this
smoke test catches that.

Content-type may be HTML or JSON depending on FastStream version; both
are acceptable.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_asyncapi_endpoint_returns_200(client: AsyncClient) -> None:
    """/asyncapi available on line-provider for AsyncAPI publish-contract docs."""
    response = await client.get("/asyncapi")
    assert response.status_code == 200, (
        f"GET /asyncapi returned {response.status_code} — "
        "FastStream RabbitRouter not wired? "
        "See src/line_provider/app.py::build_app — app.include_router(rabbit_router) "
        "is required."
    )
    assert response.content, "/asyncapi returned empty body"
    content_type = response.headers.get("content-type", "")
    assert any(t in content_type for t in ("html", "json")), (
        f"/asyncapi content-type not html or json: {content_type!r}"
    )
