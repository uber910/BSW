from __future__ import annotations

from fastapi import FastAPI

from bet_maker.entrypoints.api import bets, events, health
from bet_maker.entrypoints.lifespan import lifespan
from bet_maker.entrypoints.middleware import RequestContextMiddleware


def build_app() -> FastAPI:
    app = FastAPI(
        title="bet-maker",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(bets.router)
    app.include_router(events.router)
    return app
