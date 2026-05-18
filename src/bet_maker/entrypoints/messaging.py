"""bet-maker AMQP consumer entrypoint (D-25).

Single FastStream RabbitRouter with one subscriber binding queue
`bet_maker.events.finished` to topic exchange `bsw.events` via wildcard
`event.finished.*` (D-06). Manual ack policy (R1/F1), prefetch=10 (F2),
DLX wiring via RabbitQueue.arguments (D-04 / D-25).

Pitfalls guarded:
- R1/F1 -- `ack_policy=AckPolicy.MANUAL` (never default REJECT_ON_ERROR).
- R2/F4 -- `await msg.ack()` is the LAST statement after `async with uow:` exits cleanly.
- R7 -- `msg.nack(requeue=True)` is NEVER called; transient retried in-handler via tenacity,
  then reject(requeue=False) on exhaustion.
- F2 -- `Channel(prefetch_count=10)`.
- F5 / Anti-Pattern 5 -- one `RabbitRouter` per service; this module is the sole owner.
- F7 -- schema_version != 1 -> UnsupportedSchemaVersion -> POISON -> DLQ.
- A7 -- clear_contextvars at entry, bind in try, clear in finally.
"""

from __future__ import annotations

import asyncio

import structlog
from faststream import AckPolicy
from faststream.rabbit.fastapi import RabbitMessage, RabbitRouter
from faststream.rabbit.schemas import Channel, ExchangeType, RabbitExchange, RabbitQueue
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.contextvars import bind_contextvars, clear_contextvars
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.interactors.settle_bets_for_event import settle_bets_for_event
from bet_maker.messaging.routing import EVENT_FINISHED_WILDCARD
from bet_maker.schemas.messages import EventFinishedMessage
from bet_maker.settings.config import BetMakerSettings

_SCHEMA_VERSION_SUPPORTED = 1

log = structlog.get_logger()


class UnsupportedSchemaVersion(ValueError):  # noqa: N818
    """D-09: payload.schema_version != 1 -> POISON -> DLQ.

    Distinct from pydantic.ValidationError because schema_version validation
    is a logical check after parse, not a parse failure. Caught in same
    POISON branch as ValidationError.
    """


def _is_transient(exc: BaseException) -> bool:
    """D-09 TRANSIENT classification (DB-side errors)."""
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return True
    return isinstance(exc, asyncio.TimeoutError)


def _log_before_sleep(retry_state: RetryCallState) -> None:
    sleep_s = retry_state.next_action.sleep if retry_state.next_action else 0.0
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.warning(
        "settle.transient_retry",
        attempt_number=retry_state.attempt_number,
        sleep_s=sleep_s,
        exception_type=type(exc).__name__ if exc else None,
    )


_settle_with_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    retry=retry_if_exception(_is_transient),
    before_sleep=_log_before_sleep,
    reraise=True,
)(settle_bets_for_event)


# ------------------- sessionmaker pin (set by lifespan) -------------------
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def set_sessionmaker(sm: async_sessionmaker[AsyncSession]) -> None:
    """Pin the sessionmaker created by lifespan so the handler can build
    a fresh UoW per message (A2: never share sessions across tasks).
    Called by `src/bet_maker/entrypoints/lifespan.py` after engine init.
    """
    global _sessionmaker  # noqa: PLW0603
    _sessionmaker = sm


def _require_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError(
            "messaging.set_sessionmaker has not been called — lifespan wiring missing"
        )
    return _sessionmaker


# ------------------- router + subscriber ----------------------------------

_settings = BetMakerSettings()

router = RabbitRouter(
    str(_settings.rabbitmq_url),
    default_channel=Channel(prefetch_count=10),
)


@router.subscriber(
    queue=RabbitQueue(
        "bet_maker.events.finished",
        durable=True,
        routing_key=EVENT_FINISHED_WILDCARD,
        arguments={
            "x-dead-letter-exchange": "bsw.events.dlx",
            "x-dead-letter-routing-key": "bet_maker.events.finished",
        },
    ),
    exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
    ack_policy=AckPolicy.MANUAL,
)
async def on_event_finished(
    payload: EventFinishedMessage,
    msg: RabbitMessage,
) -> None:
    """Settle PENDING bets for a finished event (BM-09, BM-10, BM-11).

    Manual-ack ladder (D-09 / D-10 / D-11):
    - happy -> ack AFTER uow commit
    - POISON (ValidationError / UnsupportedSchemaVersion / IntegrityError)
      -> reject(requeue=False) -> DLQ
    - TRANSIENT exhausted (caught by default Exception)
      -> reject(requeue=False) -> DLQ (reconciler will retry -- Core Value)
    - nack(requeue=True) NEVER called (R7)
    """
    clear_contextvars()
    try:
        bind_contextvars(
            message_id=msg.message_id,
            correlation_id=msg.correlation_id,
            event_id=str(payload.event_id),
        )
        if payload.schema_version != _SCHEMA_VERSION_SUPPORTED:
            raise UnsupportedSchemaVersion(
                f"schema_version={payload.schema_version} not supported (expected 1)"
            )

        sessionmaker = _require_sessionmaker()
        async with AsyncUnitOfWork(sessionmaker) as uow:
            await _settle_with_retry(
                uow,
                event_id=payload.event_id,
                terminal_state=payload.new_state,
                settled_via="consumer",
            )
        await msg.ack()

    except (ValidationError, UnsupportedSchemaVersion, IntegrityError) as exc:
        log.warning(
            "settle.poison_to_dlq",
            exc_type=type(exc).__name__,
            exc=str(exc)[:500],
        )
        await msg.reject(requeue=False)

    except Exception as exc:
        log.error(
            "settle.transient_exhausted",
            exc_type=type(exc).__name__,
            exc=str(exc)[:500],
        )
        await msg.reject(requeue=False)

    finally:
        clear_contextvars()
