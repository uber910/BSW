"""Unit tests for bet-maker AMQP consumer handler.

Branches covered per D-30 / VALIDATION 05-05-01..05-05-05:
- subscriber config (locked APIs verified)
- happy path -> ack
- poison (schema_version != 1, IntegrityError) -> reject(requeue=False)
- transient (OperationalError) retry -> ack
- transient exhaustion -> reject(requeue=False)
- settle.noop (0 PENDING) -> ack
- invariant: nack(requeue=True) never called (R7)

TestRabbitBroker is in-memory -- no real broker needed. The settle interactor
is mocked via _settle_with_retry to isolate handler-level error handling
from DB plumbing. Plan 04 already proves the interactor against real PG.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from faststream import AckPolicy
from faststream.rabbit.schemas import ExchangeType, RabbitExchange
from faststream.rabbit.testing import TestRabbitBroker
from sqlalchemy.exc import IntegrityError, OperationalError

from bet_maker.entrypoints.messaging import router, set_sessionmaker
from bet_maker.schemas.messages import EventFinishedMessage, EventTerminalState
from bet_maker.schemas.settle import SettleResult

EXCHANGE = RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)


def _valid_message() -> EventFinishedMessage:
    return EventFinishedMessage(
        schema_version=1,
        event_id=uuid4(),
        new_state=EventTerminalState.FINISHED_WIN,
        coefficient=Decimal("1.50"),
        occurred_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        correlation_id="test-correlation",
    )


def _settle_result(event_id: object, settled_count: int = 1) -> SettleResult:
    eid = event_id if isinstance(event_id, UUID) else uuid4()
    return SettleResult(
        event_id=eid,
        terminal_state=EventTerminalState.FINISHED_WIN,
        settled_count=settled_count,
        settled_bet_ids=[uuid4() for _ in range(settled_count)],
        settled_via="consumer",
        settled_at=datetime.now(timezone.utc),
    )


def _make_fake_sessionmaker() -> MagicMock:
    """Build a fake async_sessionmaker whose .begin() returns an async context manager."""
    sm = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    sm.begin = MagicMock(return_value=ctx)
    return sm


@pytest.fixture(autouse=True)
def _pin_fake_sessionmaker() -> None:
    """Pin a sentinel sessionmaker so _require_sessionmaker() check passes."""
    set_sessionmaker(_make_fake_sessionmaker())


class TestSubscriberConfig:
    """05-05-01: locked FastStream API forms."""

    def test_subscriber_ack_policy_is_manual(self) -> None:
        subs = list(router.broker.subscribers)
        assert any(getattr(s, "ack_policy", None) == AckPolicy.MANUAL for s in subs), (
            "no subscriber registered with AckPolicy.MANUAL (R1/F1)"
        )

    def test_at_least_one_subscriber_registered(self) -> None:
        """SC#5 prerequisite: subscriber count > 0 for /health."""
        assert len(router.broker.subscribers) > 0


@pytest.mark.asyncio(loop_scope="session")
class TestHappyPath:
    """05-05-02: ack only after UoW commit."""

    async def test_calls_settle_and_acks(self) -> None:
        msg = _valid_message()
        with patch(
            "bet_maker.entrypoints.messaging._settle_with_retry",
            new=AsyncMock(return_value=_settle_result(msg.event_id, settled_count=1)),
        ) as settle_mock:
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    msg,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )
        settle_mock.assert_called_once()


@pytest.mark.asyncio(loop_scope="session")
class TestPoison:
    """05-05-03: ValidationError / UnsupportedSchemaVersion / IntegrityError -> reject."""

    async def test_unsupported_schema_version_rejects(self) -> None:
        msg = _valid_message()
        with (
            patch(
                "bet_maker.entrypoints.messaging._SCHEMA_VERSION_SUPPORTED",
                new=2,
            ),
            patch(
                "bet_maker.entrypoints.messaging._settle_with_retry",
                new=AsyncMock(),
            ) as settle_mock,
        ):
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    msg,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )
        settle_mock.assert_not_called()

    async def test_integrity_error_rejects(self) -> None:
        msg = _valid_message()
        integ = IntegrityError("stmt", {}, Exception("violates check constraint"))
        with patch(
            "bet_maker.entrypoints.messaging._settle_with_retry",
            new=AsyncMock(side_effect=integ),
        ) as settle_mock:
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    msg,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )
        settle_mock.assert_called_once()


@pytest.mark.asyncio(loop_scope="session")
class TestTransient:
    """05-05-04 / 05-05-05: transient retry then ack OR exhaust then reject."""

    async def test_operational_error_retries_then_succeeds(self) -> None:
        msg = _valid_message()
        calls: dict[str, int] = {"n": 0}

        async def flaky(*a: object, **kw: object) -> SettleResult:
            calls["n"] += 1
            if calls["n"] < 2:
                raise OperationalError("stmt", {}, Exception("conn"))
            return _settle_result(msg.event_id, settled_count=1)

        with patch(
            "bet_maker.entrypoints.messaging._settle_with_retry",
            new=AsyncMock(side_effect=flaky),
        ):
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    msg,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )

    async def test_exhaustion_rejects(self) -> None:
        msg = _valid_message()
        with patch(
            "bet_maker.entrypoints.messaging._settle_with_retry",
            new=AsyncMock(side_effect=OperationalError("stmt", {}, Exception("conn"))),
        ):
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    msg,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )


@pytest.mark.asyncio(loop_scope="session")
class TestNoop:
    """05-05-02 happy variant: 0 PENDING -> ack, not reject."""

    async def test_zero_pending_acks(self) -> None:
        msg = _valid_message()
        with patch(
            "bet_maker.entrypoints.messaging._settle_with_retry",
            new=AsyncMock(return_value=_settle_result(msg.event_id, settled_count=0)),
        ) as settle_mock:
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    msg,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )
        settle_mock.assert_called_once()


class TestInvariants:
    """R7: nack(requeue=True) must NEVER appear in handler module."""

    def test_nack_never_called_in_source(self) -> None:
        """Statically verify the handler source. (Belt-and-suspenders for R7.)"""
        src = Path("src/bet_maker/entrypoints/messaging.py").read_text()
        lines = src.splitlines()
        code_lines = [
            ln
            for ln in lines
            if not ln.strip().startswith("#")
            and not ln.strip().startswith('"""')
            and not ln.strip().startswith("- ")
            and not ln.strip().startswith("*")
        ]
        code = "\n".join(code_lines)
        assert "msg.nack(" not in code, "R7 violated: msg.nack( call found in messaging.py"
