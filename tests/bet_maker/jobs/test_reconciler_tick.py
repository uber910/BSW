"""reconciler tick + error-isolation tests."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.facades.event_lookup import EventSnapshot
from bet_maker.jobs import reconciler as reconciler_module
from bet_maker.jobs.reconciler import _run_tick, reconciliation_loop
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus
from bet_maker.schemas.events import EventState


class _FakeLookup:
    """Duck-typed EventLookup (no Protocol gymnastics).

    seed(event_id, snapshot_or_none_or_raise) registers a behaviour for
    get_event. raise = sentinel callable.
    """

    def __init__(self) -> None:
        self._table: dict[UUID, EventSnapshot | None | Exception] = {}
        self.calls: list[UUID] = []

    def seed(self, event_id: UUID, val: EventSnapshot | None | Exception) -> None:
        self._table[event_id] = val

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        self.calls.append(event_id)
        v = self._table.get(event_id)
        if isinstance(v, Exception):
            raise v
        return v


def _snapshot(event_id: UUID, state: EventState) -> EventSnapshot:
    return EventSnapshot(
        event_id=event_id,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        state=state,
    )


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerTick:
    async def test_run_tick_settles_finished_win_events(
        self,
        app: FastAPI,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        lookup = _FakeLookup()
        lookup.seed(event_id, _snapshot(event_id, EventState.FINISHED_WIN))
        app.state.reconciler_event_lookup = lookup
        await _run_tick(app)
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.WON
        assert bet.settled_via == "reconciler"

    async def test_run_tick_cancels_404_events(
        self,
        app: FastAPI,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        lookup = _FakeLookup()
        lookup.seed(event_id, None)
        app.state.reconciler_event_lookup = lookup
        await _run_tick(app)
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.CANCELLED
        assert bet.settled_via == "reconciler"

    async def test_run_tick_skips_new_state_events(
        self,
        app: FastAPI,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))
        lookup = _FakeLookup()
        lookup.seed(event_id, _snapshot(event_id, EventState.NEW))
        app.state.reconciler_event_lookup = lookup
        await _run_tick(app)
        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.PENDING

    async def test_run_tick_noop_when_no_pending(
        self,
        app: FastAPI,
    ) -> None:
        lookup = _FakeLookup()
        app.state.reconciler_event_lookup = lookup
        await _run_tick(app)
        assert lookup.calls == []

    async def test_per_event_exception_isolation(
        self,
        app: FastAPI,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_a, event_b = uuid4(), uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_a, amount=Decimal("10.00")))
            session.add(Bet(event_id=event_b, amount=Decimal("10.00")))
        lookup = _FakeLookup()
        lookup.seed(event_a, RuntimeError("boom"))
        lookup.seed(event_b, _snapshot(event_b, EventState.FINISHED_WIN))
        app.state.reconciler_event_lookup = lookup
        await _run_tick(app)
        async with session_factory() as session:
            bet_a = (await session.execute(select(Bet).where(Bet.event_id == event_a))).scalar_one()
            bet_b = (await session.execute(select(Bet).where(Bet.event_id == event_b))).scalar_one()
        assert bet_a.status == BetStatus.PENDING
        assert bet_b.status == BetStatus.WON

    async def test_sleep_before_first_tick(
        self,
        app: FastAPI,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """asyncio.sleep MUST run before the first _run_tick call.

        Replace _run_tick with a counter; replace asyncio.sleep with a
        counter that records its argument; run reconciliation_loop for
        a brief moment then cancel. Assert sleep was called BEFORE the
        first tick (i.e. tick_calls == 1 when sleep_calls == 1).
        """
        tick_calls: list[int] = []
        sleep_args: list[float] = []

        async def fake_tick(_app: FastAPI) -> None:
            tick_calls.append(len(sleep_args))

        real_sleep = asyncio.sleep

        async def fake_sleep(s: float) -> None:
            sleep_args.append(s)
            await real_sleep(0)

        monkeypatch.setattr(reconciler_module, "_run_tick", fake_tick)
        monkeypatch.setattr(reconciler_module.asyncio, "sleep", fake_sleep)  # type: ignore[attr-defined]

        task = asyncio.create_task(reconciliation_loop(app, interval_s=0.01), name="reconciliation")
        await real_sleep(0.1)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        assert sleep_args, "asyncio.sleep was never called before first tick"
        if tick_calls:
            assert tick_calls[0] >= 1, "first tick ran before any sleep"


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerErrorIsolation:
    async def test_loop_continues_after_tick_exception(
        self,
        app: FastAPI,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = {"n": 0}

        async def flaky_tick(_app: FastAPI) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first tick fails")

        monkeypatch.setattr(reconciler_module, "_run_tick", flaky_tick)
        task = asyncio.create_task(reconciliation_loop(app, interval_s=0.01), name="reconciliation")
        await asyncio.sleep(0.1)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert calls["n"] >= 2, f"loop died after first tick exception (calls={calls['n']})"

    async def test_loop_does_not_catch_basesystem_exits(
        self,
        app: FastAPI,
    ) -> None:
        import inspect  # noqa: PLC0415

        src = inspect.getsource(reconciliation_loop)
        assert "except BaseException" not in src, (
            "reconciliation_loop must NOT catch BaseException — "
            "SystemExit/KeyboardInterrupt must propagate"
        )
        assert "except Exception" in src, (
            "reconciliation_loop must use 'except Exception' (narrower than BaseException)"
        )
