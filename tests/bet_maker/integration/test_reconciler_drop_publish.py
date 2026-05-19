"""Integration: respx-mocked LP drives reconciler decision branches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import respx
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.jobs.reconciler import _reconcile_event
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus

_LP_BASE_URL = "http://line-provider:8000"


def _make_lookup(http_client: httpx.AsyncClient) -> HttpEventLookup:
    return HttpEventLookup(
        http_client=http_client,
        attempts=2,
        max_backoff=0.1,
    )


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerDropPublish:
    async def test_respx_mocked_lp_terminal_state_triggers_reconciler_settle(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

        with respx.mock(base_url=_LP_BASE_URL, assert_all_called=False) as mock_router:
            mock_router.get(f"/event/{event_id}").mock(
                return_value=Response(
                    200,
                    json={
                        "event_id": str(event_id),
                        "coefficient": "1.50",
                        "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        "state": "FINISHED_WIN",
                    },
                )
            )
            async with httpx.AsyncClient(base_url=_LP_BASE_URL, timeout=5.0) as http_client:
                await _reconcile_event(session_factory, _make_lookup(http_client), event_id)

        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.WON
        assert bet.settled_via == "reconciler"

    async def test_respx_mocked_lp_404_triggers_reconciler_cancel(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

        with respx.mock(base_url=_LP_BASE_URL, assert_all_called=False) as mock_router:
            mock_router.get(f"/event/{event_id}").mock(return_value=Response(404))
            async with httpx.AsyncClient(base_url=_LP_BASE_URL, timeout=5.0) as http_client:
                await _reconcile_event(session_factory, _make_lookup(http_client), event_id)

        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.CANCELLED
        assert bet.settled_via == "reconciler"

    async def test_reconciler_skip_when_lp_still_returns_new(
        self,
        session_factory: async_sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        event_id = uuid4()
        async with session_factory.begin() as session:
            session.add(Bet(event_id=event_id, amount=Decimal("10.00")))

        with respx.mock(base_url=_LP_BASE_URL, assert_all_called=False) as mock_router:
            mock_router.get(f"/event/{event_id}").mock(
                return_value=Response(
                    200,
                    json={
                        "event_id": str(event_id),
                        "coefficient": "1.50",
                        "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        "state": "NEW",
                    },
                )
            )
            async with httpx.AsyncClient(base_url=_LP_BASE_URL, timeout=5.0) as http_client:
                await _reconcile_event(session_factory, _make_lookup(http_client), event_id)

        async with session_factory() as session:
            bet = (await session.execute(select(Bet).where(Bet.event_id == event_id))).scalar_one()
        assert bet.status == BetStatus.PENDING
        assert bet.settled_via is None
