"""E2E: real PG + real RMQ + drop-publish recovery.

Three scenarios:
  a) consumer happy path (regression check).
  b) drop-publish recovery via reconciler.
  c) delete-event recovery via reconciler (CANCELLED branch).

Verified paths:
  - RabbitEventBus: line_provider.facades.event_bus.RabbitEventBus.
  - event_store internal dict: _data (InMemoryEventStore uses self._data, not self._events).
  - app.state.event_store: set in line_provider/lifespan.py.
  - reconciler uses app.state.reconciler_event_lookup (separate from app.state.event_lookup):
    both must be swapped to lp_client so the reconciler can reach the in-process LP app.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.jobs.reconciler import reconciliation_loop

_POLL_BUDGET_S = 8.0
_FAST_INTERVAL_S = 1.0
_BUFFER_S = 1.5


async def _swap_to_fast_reconciler(app: FastAPI) -> asyncio.Task[None]:
    """Cancel the default 30s task, return a 1.0s task pinned to app.state."""
    old = app.state.reconciliation_task
    old.cancel()
    with suppress(asyncio.CancelledError):
        await old
    fast: asyncio.Task[None] = asyncio.create_task(
        reconciliation_loop(app, interval_s=_FAST_INTERVAL_S),
        name="reconciliation",
    )
    app.state.reconciliation_task = fast
    return fast


async def _restore_default_reconciler(app: FastAPI, fast_task: asyncio.Task[None]) -> None:
    fast_task.cancel()
    with suppress(asyncio.CancelledError):
        await fast_task
    app.state.reconciliation_task = asyncio.create_task(
        reconciliation_loop(app, interval_s=app.state.settings.reconciliation_interval_s),
        name="reconciliation",
    )


async def _poll_bet_status(client: AsyncClient, bet_id: str, budget_s: float) -> dict[str, object]:
    """Poll GET /bets until the bet leaves PENDING or budget is exhausted."""
    loop = asyncio.get_running_loop()
    end = loop.time() + budget_s
    while loop.time() < end:
        r = await client.get("/bets")
        assert r.status_code == 200, r.text
        for bet in r.json():
            if bet["id"] == bet_id and bet["status"] != "PENDING":
                return dict(bet)
        await asyncio.sleep(0.1)
    r = await client.get("/bets")
    for bet in r.json():
        if bet["id"] == bet_id:
            return dict(bet)
    raise AssertionError(f"bet {bet_id} not found in GET /bets")


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerDropPublishE2E:
    async def test_consumer_happy_path_settles_won(
        self,
        app: FastAPI,
        client: AsyncClient,
        line_provider_app: FastAPI,
    ) -> None:
        """Scenario a: consumer happy path (regression check)."""
        lp_transport = ASGITransport(app=line_provider_app)
        async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
            event_id = str(uuid4())
            deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

            r = await lp_client.post(
                "/event",
                json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
            )
            assert r.status_code in (200, 201), r.text

            original_event_lookup = app.state.event_lookup
            original_reconciler_lookup = app.state.reconciler_event_lookup
            test_lookup = HttpEventLookup(http_client=lp_client, attempts=3, max_backoff=1.0)
            app.state.event_lookup = test_lookup
            app.state.reconciler_event_lookup = test_lookup
            fast = await _swap_to_fast_reconciler(app)
            try:
                rb = await client.post("/bet", json={"event_id": event_id, "amount": "10.00"})
                assert rb.status_code == 201, rb.text
                bet_id = rb.json()["id"]

                rp = await lp_client.put(
                    f"/event/{event_id}",
                    json={
                        "coefficient": "1.50",
                        "deadline": deadline,
                        "state": "FINISHED_WIN",
                    },
                )
                assert rp.status_code in (200, 204), rp.text

                bet = await _poll_bet_status(client, bet_id, _POLL_BUDGET_S)
            finally:
                app.state.event_lookup = original_event_lookup
                app.state.reconciler_event_lookup = original_reconciler_lookup
                await _restore_default_reconciler(app, fast)

        assert bet["status"] == "WON", bet

    async def test_drop_publish_reconciler_recovers_won(
        self,
        app: FastAPI,
        client: AsyncClient,
        line_provider_app: FastAPI,
    ) -> None:
        """Scenario b: AMQP publish dropped; reconciler recovers."""
        lp_transport = ASGITransport(app=line_provider_app)
        async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
            event_id = str(uuid4())
            deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

            r = await lp_client.post(
                "/event",
                json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
            )
            assert r.status_code in (200, 201), r.text

            original_event_lookup = app.state.event_lookup
            original_reconciler_lookup = app.state.reconciler_event_lookup
            test_lookup = HttpEventLookup(http_client=lp_client, attempts=3, max_backoff=1.0)
            app.state.event_lookup = test_lookup
            app.state.reconciler_event_lookup = test_lookup
            fast = await _swap_to_fast_reconciler(app)
            try:
                rb = await client.post("/bet", json={"event_id": event_id, "amount": "10.00"})
                assert rb.status_code == 201, rb.text
                bet_id = rb.json()["id"]

                with patch(
                    "line_provider.facades.event_bus.RabbitEventBus.publish",
                    new=AsyncMock(return_value=None),
                ):
                    rp = await lp_client.put(
                        f"/event/{event_id}",
                        json={
                            "coefficient": "1.50",
                            "deadline": deadline,
                            "state": "FINISHED_WIN",
                        },
                    )
                    assert rp.status_code in (200, 204), rp.text

                await asyncio.sleep(_FAST_INTERVAL_S + _BUFFER_S)
                bet = await _poll_bet_status(client, bet_id, _POLL_BUDGET_S)
            finally:
                app.state.event_lookup = original_event_lookup
                app.state.reconciler_event_lookup = original_reconciler_lookup
                await _restore_default_reconciler(app, fast)

        assert bet["status"] == "WON", bet

    async def test_delete_event_reconciler_cancels_bet(
        self,
        app: FastAPI,
        client: AsyncClient,
        line_provider_app: FastAPI,
    ) -> None:
        """Scenario c: event deleted from LP -> bet -> CANCELLED."""
        lp_transport = ASGITransport(app=line_provider_app)
        async with AsyncClient(transport=lp_transport, base_url="http://lp") as lp_client:
            event_id = str(uuid4())
            deadline = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

            r = await lp_client.post(
                "/event",
                json={"event_id": event_id, "coefficient": "1.50", "deadline": deadline},
            )
            assert r.status_code in (200, 201), r.text

            original_event_lookup = app.state.event_lookup
            original_reconciler_lookup = app.state.reconciler_event_lookup
            test_lookup = HttpEventLookup(http_client=lp_client, attempts=3, max_backoff=1.0)
            app.state.event_lookup = test_lookup
            app.state.reconciler_event_lookup = test_lookup
            fast = await _swap_to_fast_reconciler(app)
            try:
                rb = await client.post("/bet", json={"event_id": event_id, "amount": "10.00"})
                assert rb.status_code == 201, rb.text
                bet_id = rb.json()["id"]

                event_store = line_provider_app.state.event_store
                event_store._data.pop(UUID(event_id), None)

                await asyncio.sleep(_FAST_INTERVAL_S + _BUFFER_S)
                bet = await _poll_bet_status(client, bet_id, _POLL_BUDGET_S)
            finally:
                app.state.event_lookup = original_event_lookup
                app.state.reconciler_event_lookup = original_reconciler_lookup
                await _restore_default_reconciler(app, fast)

        from bet_maker.schemas.bets import BetStatus  # noqa: PLC0415

        assert bet["status"] == BetStatus.CANCELLED.value, bet
