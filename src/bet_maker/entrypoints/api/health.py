from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from bet_maker.facades.deps import EngineDep
from bet_maker.infrastructure.db.pings import ping_postgres

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(engine: EngineDep) -> JSONResponse:
    """GET /health — live PG ping.

    D-26: single SELECT 1 via ping_postgres(engine) — no caching.
    D-28: 200 {"status": "ok", "checks": {"postgres": "ok"}} on success;
          503 {"status": "degraded", "checks": {"postgres": "down"}} on failure.
    D-29: SQLAlchemyError caught inside ping_postgres -> returns False.
    BM-08: 503 enables docker-compose healthcheck to detect DB outages.
    """
    pg_ok = await ping_postgres(engine)
    if pg_ok:
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "checks": {"postgres": "ok"}},
        )
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "checks": {"postgres": "down"}},
    )
