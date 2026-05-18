from __future__ import annotations

from fastapi import FastAPI

from line_provider.entrypoints.api import events, health
from line_provider.entrypoints.lifespan import lifespan
from line_provider.entrypoints.messaging import router as rabbit_router
from line_provider.entrypoints.middleware import RequestContextMiddleware


def build_app() -> FastAPI:
    app = FastAPI(
        title="line-provider",
        description=(
            "Источник событий и их статусов. Хранит события в памяти, "
            "публикует EventFinishedMessage в RabbitMQ exchange `bsw.events` "
            "при переходе в FINISHED_WIN / FINISHED_LOSE. "
            "AsyncAPI: /asyncapi."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
