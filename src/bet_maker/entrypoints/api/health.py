from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from bet_maker.facades.deps import EngineDep, RabbitBrokerDep
from bet_maker.infrastructure.db.pings import ping_postgres

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(engine: EngineDep, broker: RabbitBrokerDep) -> JSONResponse:
    """GET /health — PG + RMQ + subscriber-count check (D-20 / SC#5).

    Returns 200 only when all three are healthy:
      - ping_postgres(engine) returns True (Phase 3 D-26 baseline)
      - broker.ping(timeout=1.0) returns True (RMQ reachable, D-22 bounded)
      - len(broker.subscribers) > 0 (consumer registered, R6)

    Returns 503 with per-check status string when any check fails.
    docker-compose healthcheck consumes the HTTP status; observability tools
    consume the body shape.

    T-05-08-01: broker.ping(timeout=1.0) bounded — does not block /health
    indefinitely if broker hangs.
    T-05-08-02: len(broker.subscribers) > 0 ensures green only when consumer
    is registered — import-time errors leave subscribers=[]; SC#5 enforces 503.
    """
    pg_ok = await ping_postgres(engine)
    rmq_ok = await broker.ping(timeout=1.0)
    subs_ok = len(broker.subscribers) > 0

    if pg_ok and rmq_ok and subs_ok:
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "checks": {
                    "postgres": "ok",
                    "rabbitmq": "ok",
                    "rabbitmq_consumer": "ok",
                },
            },
        )
    return JSONResponse(
        status_code=503,
        content={
            "status": "degraded",
            "checks": {
                "postgres": "ok" if pg_ok else "down",
                "rabbitmq": "ok" if rmq_ok else "down",
                "rabbitmq_consumer": "ok" if subs_ok else "no subscribers",
            },
        },
    )
