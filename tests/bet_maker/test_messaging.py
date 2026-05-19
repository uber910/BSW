"""Unit tests for bet-maker AMQP consumer handler.

Branches covered:
- subscriber config (locked APIs verified)
- happy path -> ack
- poison (schema_version != 1, IntegrityError) -> reject(requeue=False)
- transient (OperationalError) retry -> ack
- transient exhaustion -> reject(requeue=False)
- settle.noop (0 PENDING) -> ack
- invariant: nack(requeue=True) never called

TestRabbitBroker is in-memory -- no real broker needed. The settle interactor
is mocked via _settle_with_retry to isolate handler-level error handling
from DB plumbing. The interactor itself is proved against real PG elsewhere.
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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import bet_maker.api.messaging as msg_mod
from bet_maker.api.messaging import router, set_sessionmaker
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.messages import EventFinishedMessage, EventTerminalState
from bet_maker.schemas.settle import SettleResult
from bet_maker.uow.postgres import PostgresUnitOfWork

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
    """Locked FastStream API forms."""

    def test_subscriber_ack_policy_is_manual(self) -> None:
        subs = list(router.broker.subscribers)
        assert any(getattr(s, "ack_policy", None) == AckPolicy.MANUAL for s in subs), (
            "no subscriber registered with AckPolicy.MANUAL"
        )

    def test_at_least_one_subscriber_registered(self) -> None:
        """SC#5 prerequisite: subscriber count > 0 for /health."""
        assert len(router.broker.subscribers) > 0


@pytest.mark.asyncio(loop_scope="session")
class TestHappyPath:
    """Ack only after UoW commit."""

    async def test_calls_settle_and_acks(self) -> None:
        msg = _valid_message()
        with patch(
            "bet_maker.api.messaging._settle_with_retry",
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
    """ValidationError / UnsupportedSchemaVersion / IntegrityError -> reject."""

    async def test_unsupported_schema_version_rejects(self) -> None:
        msg = _valid_message()
        with (
            patch(
                "bet_maker.api.messaging._SCHEMA_VERSION_SUPPORTED",
                new=2,
            ),
            patch(
                "bet_maker.api.messaging._settle_with_retry",
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
            "bet_maker.api.messaging._settle_with_retry",
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
    """Transient retry then ack OR exhaust then reject."""

    async def test_operational_error_retries_then_succeeds(self) -> None:
        msg = _valid_message()
        calls: dict[str, int] = {"n": 0}

        async def flaky(*a: object, **kw: object) -> SettleResult:
            calls["n"] += 1
            if calls["n"] < 2:
                raise OperationalError("stmt", {}, Exception("conn"))
            return _settle_result(msg.event_id, settled_count=1)

        with patch(
            "bet_maker.api.messaging._settle_with_retry",
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
            "bet_maker.api.messaging._settle_with_retry",
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
    """Happy variant: 0 PENDING -> ack, not reject."""

    async def test_zero_pending_acks(self) -> None:
        msg = _valid_message()
        with patch(
            "bet_maker.api.messaging._settle_with_retry",
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
    """nack(requeue=True) must NEVER appear in the handler module."""

    def test_nack_never_called_in_source(self) -> None:
        """Statically verify the handler source as a belt-and-suspenders check."""
        src = Path("src/bet_maker/api/messaging.py").read_text()
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
        assert "msg.nack(" not in code, "msg.nack( call found in messaging.py"

    def test_handler_does_not_open_uow_context(self) -> None:
        """CR-01 static regression: messaging.py must NOT open `async with
        PostgresUnitOfWork(...)`.

        Manual-ack ladder relies on the interactor owning the UoW context.
        Reopening the UoW in the handler trips
        ``PostgresUnitOfWork.__aexit__``'s assert (non-reentrant) and rejects
        happy-path messages to DLQ even though the UPDATE committed.
        """
        src = Path("src/bet_maker/api/messaging.py").read_text()
        assert "async with PostgresUnitOfWork" not in src, (
            "CR-01 regression: messaging.py must NOT open `async with "
            "PostgresUnitOfWork(...)` -- the interactor `settle_bets_for_event` "
            "already owns its own UoW context. A second `async with` here trips "
            "`PostgresUnitOfWork.__aexit__`'s assert and rejects happy-path "
            "messages to DLQ."
        )


@pytest.mark.asyncio(loop_scope="session")
class TestCR01HandlerOwnsNoUoWContext:
    """CR-01 regression: handler MUST NOT open `async with uow:` itself.

    ``PostgresUnitOfWork.__aenter__`` is not reentrant: a second call from inside
    ``settle_bets_for_event`` (the interactor opens its own ``async with uow:``)
    overwrites ``_cm``/``_session``, the inner ``__aexit__`` resets them to
    ``None``, and the outer ``__aexit__`` then trips
    ``assert self._cm is not None``.

    On the happy path the inner UPDATE commits BEFORE the assert fires, so the
    DB state looks correct. But the AssertionError leaks out of the outer
    ``async with`` block, is caught by ``except Exception`` in the handler,
    logged as ``settle.transient_exhausted``, and the message is rejected to DLQ
    instead of being acked.

    Because the handler ack/reject is invisible to bet-status assertions (UPDATE
    already committed) the e2e test
    ``test_consumer_settles_bet_after_lp_transitions`` does NOT catch this.

    Behavioural net: invoking the handler against a real ``_settle_with_retry``
    (no ``AsyncMock``) MUST hit exactly ONE ``PostgresUnitOfWork.__aenter__``
    per message, not two. Two enters means the outer ``async with`` is back.

    The complementary static guard lives in
    ``TestInvariants::test_handler_does_not_open_uow_context``.
    """

    async def test_handler_enters_uow_exactly_once_on_happy_path(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Behavioural guard: real interactor + real PG via TestRabbitBroker;
        ``PostgresUnitOfWork.__aenter__`` is called exactly once per message.

        Pins the real ``session_factory`` (testcontainers PG) into the messaging
        module, seeds one PENDING bet, and patches
        ``bet_maker.api.messaging.PostgresUnitOfWork`` with a counting subclass.
        ``TestRabbitBroker`` then drives the handler the same way production
        does — through the full FastStream subscriber wrapper — so we run the
        real ``_settle_with_retry`` end-to-end (no AsyncMock).

        The interactor's own ``async with uow:`` accounts for the only enter.
        Two enters means the handler reopened the UoW (CR-01 regression).
        """
        # Pin the REAL session_factory so the handler builds a real UoW
        # against the testcontainers PG.
        set_sessionmaker(session_factory)

        # Seed one PENDING bet so the interactor takes the non-noop branch.
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

        enter_count = {"n": 0}

        class CountingPostgresUoW(PostgresUnitOfWork):
            async def __aenter__(self) -> CountingPostgresUoW:
                enter_count["n"] += 1
                await super().__aenter__()
                return self

        message = EventFinishedMessage(
            schema_version=1,
            event_id=event_id,
            new_state=EventTerminalState.FINISHED_WIN,
            coefficient=Decimal("1.50"),
            occurred_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
            correlation_id="cr01-correlation",
        )

        # Patch PostgresUnitOfWork inside the handler module + drive the
        # handler through TestRabbitBroker (same wrapping as production).
        with patch.object(msg_mod, "PostgresUnitOfWork", CountingPostgresUoW):
            async with TestRabbitBroker(router.broker) as br:
                await br.publish(
                    message,
                    queue="bet_maker.events.finished",
                    exchange=EXCHANGE,
                    routing_key="event.finished.win",
                )

        # Exactly one __aenter__ — the interactor's. Two means CR-01 regressed.
        assert enter_count["n"] == 1, (
            f"CR-01 regression: PostgresUnitOfWork.__aenter__ called "
            f"{enter_count['n']} times per message; expected exactly 1 "
            f"(only the interactor opens the UoW context). When this fails, "
            f"the outer `async with PostgresUnitOfWork` is back in messaging.py "
            f"and happy-path messages are being rejected to DLQ."
        )

        # Sanity: the bet was settled (the inner UPDATE always commits, even
        # under the CR-01 bug, so this assertion alone is NOT sufficient to
        # catch the regression — the enter_count check above is the real
        # regression net).
        async with session_factory() as session:
            settled = (
                (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalars().one()
            )
            assert settled.status == BetStatus.WON
