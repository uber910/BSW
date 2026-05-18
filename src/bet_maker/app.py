from __future__ import annotations

from fastapi import FastAPI

from bet_maker.api import bets, events, health
from bet_maker.api.messaging import router as rabbit_router
from bet_maker.lifespan import lifespan
from bet_maker.middleware import RequestContextMiddleware


def build_app() -> FastAPI:
    app = FastAPI(
        title="bet-maker",
        description=(
            "Сервис приёма и истории ставок. Хранит ставки в PostgreSQL, "
            "получает финальные статусы событий из RabbitMQ "
            "(queue `bet_maker.events.finished`), reconciler как защита "
            "от потерянных сообщений. AsyncAPI: /asyncapi."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(bets.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
