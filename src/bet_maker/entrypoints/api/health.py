from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from bet_maker.facades.deps import (
    EngineDep,
    RabbitBrokerDep,
    ReconciliationTaskDep,
)
from bet_maker.infrastructure.db.pings import ping_postgres

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Service health (PG + RMQ + consumer + reconciler)",
    responses={
        503: {
            "description": (
                "Degraded — one of: postgres / rabbitmq / rabbitmq_consumer / "
                "reconciler is down. Payload: "
                "{status: 'degraded', checks: {postgres, rabbitmq, "
                "rabbitmq_consumer, reconciler}}."
            ),
        },
    },
)
async def health(
    engine: EngineDep,
    broker: RabbitBrokerDep,
    reconciler_task: ReconciliationTaskDep,
) -> JSONResponse:
    """GET /health — PG + RMQ + subscriber + reconciler check.

    Returns 200 only when all four are healthy:
      - ping_postgres(engine) returns True
      - broker.ping(timeout=1.0) returns True
      - len(broker.subscribers) > 0
      - not reconciler_task.done()  (`not task.done()` is sufficient
        liveness; task.exception() would raise InvalidStateError while
        the task is still running)

    Returns 503 with per-check status string when any check fails.
    """
    pg_ok = await ping_postgres(engine)
    rmq_ok = await broker.ping(timeout=1.0)
    subs_ok = len(broker.subscribers) > 0
    reconciler_ok = not reconciler_task.done()

    if pg_ok and rmq_ok and subs_ok and reconciler_ok:
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "checks": {
                    "postgres": "ok",
                    "rabbitmq": "ok",
                    "rabbitmq_consumer": "ok",
                    "reconciler": "ok",
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
                "reconciler": "ok" if reconciler_ok else "dead",
            },
        },
    )
