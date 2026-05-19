"""E2E tests — real RabbitMQ + real PG.

These tests are the highest-fidelity integration validation. TestRabbitBroker
catches handler-level bugs; this file catches topology bugs: missing
binding, wrong exchange type, missing DLX wiring, missing correlation
propagation.

Fixtures used (all session-scoped from tests/conftest.py + tests/bet_maker/conftest.py):
  - postgres_container / pg_dsn / async_engine — real PG via testcontainers.
  - rabbitmq_container / amqp_url — real RMQ via testcontainers.
  - app / client — bet-maker FastAPI with full lifespan.
  - line_provider_app — line-provider FastAPI with full lifespan.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bet_maker.schemas.bets import BetStatus


@pytest.mark.asyncio(loop_scope="session")
class TestE2ERabbitMQ:
    """PUT to terminal state -> bet flips WON/LOST within 1s (5s budget for CI)."""

    async def test_consumer_settles_bet_after_lp_transitions_to_finished_win(
        self,
        app: FastAPI,
        client: AsyncClient,
        line_provider_app: FastAPI,
    ) -> None:
        from bet_maker.facades.http_event_lookup import HttpEventLookup  # noqa: PLC0415

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
            app.state.event_lookup = HttpEventLookup(
                http_client=lp_client,
                attempts=3,
                max_backoff=1.0,
            )
            try:
                rb = await client.post(
                    "/bet",
                    json={"event_id": event_id, "amount": "10.00"},
                )
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

                loop = asyncio.get_running_loop()
                deadline_poll = loop.time() + 5.0
                final_status: str | None = None
                while loop.time() < deadline_poll:
                    rg = await client.get("/bets")
                    assert rg.status_code == 200
                    bets = rg.json()
                    for b in bets:
                        if b["id"] == bet_id:
                            if b["status"] != BetStatus.PENDING.value:
                                final_status = b["status"]
                            break
                    if final_status is not None:
                        break
                    await asyncio.sleep(0.1)

                assert final_status == BetStatus.WON.value, (
                    f"bet did not flip to WON within 5s; final_status={final_status}"
                )
            finally:
                app.state.event_lookup = original_event_lookup

    async def test_poison_message_lands_in_dlq(
        self,
        app: FastAPI,
        line_provider_app: FastAPI,
    ) -> None:
        """schema_version=99 -> reject(requeue=False) -> DLQ.

        Publish a raw dict that does NOT match EventFinishedMessage (extra='forbid'
        + schema_version validation). Consumer rejects it to DLQ. We then passively
        declare the DLQ and check its message count.
        """
        from faststream.rabbit.schemas import (  # noqa: PLC0415
            ExchangeType,
            RabbitExchange,
            RabbitQueue,
        )

        from line_provider.api.messaging import router as lp_router  # noqa: PLC0415

        poison_body = {
            "schema_version": 99,
            "event_id": str(uuid4()),
            "new_state": "FINISHED_WIN",
            "coefficient": "1.50",
            "occurred_at": "2026-05-18T10:00:00+00:00",
            "correlation_id": "poison-test",
        }
        exchange = RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)
        await lp_router.broker.publish(
            poison_body,
            routing_key="event.finished.win",
            exchange=exchange,
            persist=True,
        )

        from bet_maker.api.messaging import router as bm_router  # noqa: PLC0415

        dlq = await bm_router.broker.declare_queue(
            RabbitQueue("bet_maker.events.finished.dlq", durable=True, declare=False)
        )
        deadline_dlq = asyncio.get_running_loop().time() + 5.0
        got = None
        while asyncio.get_running_loop().time() < deadline_dlq:
            got = await dlq.get(fail=False, timeout=0.2)
            if got is not None:
                break
            await asyncio.sleep(0.1)
        assert got is not None, "DLQ has 0 messages — poison routing failed"
        await got.ack()
