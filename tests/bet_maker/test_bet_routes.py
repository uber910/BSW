"""Integration tests for bet_maker bets API routes.

``POST /bet`` returns 201 + ``BetRead`` on the happy path and 422 on
invalid input or ``EventNotBettable`` (event_lookup miss / deadline /
state). ``GET /bets`` returns 200 with bets ordered by ``created_at``
DESC. ``GET /bet/{id}`` returns 200 or 404. Decimal round-trips as a
string ("10.00" -> ``body["amount"] == "10.00"``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime as dt
from datetime import timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bet_maker.facades.event_lookup import EventSnapshot
from bet_maker.facades.line_provider_client import LineProviderUnavailable


@pytest.mark.asyncio(loop_scope="session")
class TestPostBet:
    """POST /bet — happy path and validation errors."""

    async def test_post_bet_happy_path_returns_201(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """POST /bet returns 201 + BetRead with all required fields."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10.00"})
        assert response.status_code == 201
        body = response.json()
        assert body["event_id"] == str(event_id)
        assert body["status"] == "PENDING"
        assert "id" in body
        assert "created_at" in body

    async def test_post_bet_decimal_roundtrip(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """amount "10.00" round-trip preserved as string (not float)."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10.00"})
        assert response.status_code == 201
        body = response.json()
        assert body["amount"] == "10.00"

    async def test_post_bet_amount_normalized_to_2dp(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """Integer amount "10" is normalised to "10.00"."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10"})
        assert response.status_code == 201
        assert response.json()["amount"] == "10.00"

    async def test_post_bet_422_amount_more_than_2dp(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """422 when amount has > 2 decimal places."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10.123"})
        assert response.status_code == 422

    async def test_post_bet_422_amount_zero(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """422 when amount == 0 (must be > 0)."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "0"})
        assert response.status_code == 422

    async def test_post_bet_422_amount_negative(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """422 when amount < 0."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "-5.00"})
        assert response.status_code == 422

    async def test_post_bet_422_missing_amount(self, client: AsyncClient) -> None:
        """422 when amount field is missing."""
        response = await client.post("/bet", json={"event_id": str(uuid4())})
        assert response.status_code == 422

    async def test_post_bet_422_invalid_event_id(self, client: AsyncClient) -> None:
        """422 when event_id is not a valid UUID."""
        response = await client.post("/bet", json={"event_id": "not-a-uuid", "amount": "10.00"})
        assert response.status_code == 422

    async def test_post_bet_422_extra_field(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """422 when extra field is sent (extra='forbid')."""
        event_id = seed_event()
        response = await client.post(
            "/bet",
            json={"event_id": str(event_id), "amount": "10.00", "unexpected": "value"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
class TestPostBetEventNotBettable:
    """POST /bet — EventNotBettable reason strings."""

    async def test_post_bet_422_event_not_found(self, client: AsyncClient) -> None:
        """422 with 'event not found' when event_id not in lookup."""
        unknown_id = uuid4()
        response = await client.post("/bet", json={"event_id": str(unknown_id), "amount": "10.00"})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "event not found" in detail
        assert str(unknown_id) in detail

    async def test_post_bet_422_deadline_passed(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """422 with 'deadline passed' when event deadline is in the past."""
        past = dt.now(timezone.utc) - timedelta(hours=1)
        event_id = seed_event(deadline=past)
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10.00"})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "deadline passed" in detail

    async def test_post_bet_422_event_not_active(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """422 with 'event not active' when event state is FINISHED_WIN."""
        event_id = seed_event(state="FINISHED_WIN")
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10.00"})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "event not active" in detail


@pytest.mark.asyncio(loop_scope="session")
class TestPostBet503:
    """POST /bet — 503 when LineProviderUnavailable raised."""

    async def test_post_bet_503_when_line_provider_unavailable(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """LineProviderUnavailable in place_bet -> 503 with static detail.

        No PG row should be written (verified by counting bets via GET /bets
        before and after — count must be equal).
        """

        class _RaisingLookup:
            """Fake EventLookup that simulates LineProviderUnavailable on every call."""

            async def get_event(self, event_id: UUID) -> EventSnapshot | None:
                raise LineProviderUnavailable(reason="simulated upstream outage")

        from bet_maker.facades.deps import get_event_lookup  # noqa: PLC0415

        # Snapshot bet count before
        before = await client.get("/bets")
        assert before.status_code == 200
        count_before = len(before.json())

        app.dependency_overrides[get_event_lookup] = lambda: _RaisingLookup()  # noqa: PLW0108
        try:
            response = await client.post(
                "/bet",
                json={"event_id": str(uuid4()), "amount": "10.00"},
            )
            assert response.status_code == 503
            assert (
                response.json()["detail"]
                == "event validation unavailable: line-provider unreachable"
            )
        finally:
            app.dependency_overrides.pop(get_event_lookup, None)

        # Snapshot bet count after
        after = await client.get("/bets")
        assert after.status_code == 200
        assert len(after.json()) == count_before, "503 path must NOT write a bet to PG"

    async def test_post_bet_503_ladder_precedes_422(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """Even if event_id is bogus (would normally 422), the 503 fires first.

        This proves the exception ladder ordering — LineProviderUnavailable is
        caught BEFORE EventNotBettable (which would be raised if the lookup
        returned None instead of raising).
        """

        class _RaisingLookup:
            async def get_event(self, event_id: UUID) -> EventSnapshot | None:
                raise LineProviderUnavailable(reason="simulated")

        from bet_maker.facades.deps import get_event_lookup  # noqa: PLC0415

        app.dependency_overrides[get_event_lookup] = lambda: _RaisingLookup()  # noqa: PLW0108
        try:
            # Bogus event_id — but the lookup never returns None because
            # it raises first. Route ladder catches LineProviderUnavailable
            # before any None->EventNotBettable->422 mapping happens.
            response = await client.post(
                "/bet",
                json={"event_id": str(uuid4()), "amount": "5.00"},
            )
            assert response.status_code == 503
            # Confirm we did NOT fall through to 422
            assert response.status_code != 422
        finally:
            app.dependency_overrides.pop(get_event_lookup, None)


@pytest.mark.asyncio(loop_scope="session")
class TestGetBets:
    """GET /bets — list all bets ordered by created_at DESC."""

    async def test_get_bets_empty_returns_list(self, client: AsyncClient) -> None:
        """GET /bets returns empty list when no bets exist."""
        response = await client.get("/bets")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_bets_returns_placed_bets(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """GET /bets includes the bet just placed."""
        event_id = seed_event()
        await client.post("/bet", json={"event_id": str(event_id), "amount": "5.00"})
        response = await client.get("/bets")
        assert response.status_code == 200
        bets = response.json()
        assert len(bets) == 1
        assert bets[0]["event_id"] == str(event_id)

    async def test_get_bets_ordered_desc_by_created_at(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """GET /bets returns bets newest-first (created_at DESC)."""
        e1 = seed_event()
        e2 = seed_event()
        await client.post("/bet", json={"event_id": str(e1), "amount": "1.00"})
        await client.post("/bet", json={"event_id": str(e2), "amount": "2.00"})
        response = await client.get("/bets")
        assert response.status_code == 200
        bets = response.json()
        assert len(bets) == 2
        ts0 = bets[0]["created_at"]
        ts1 = bets[1]["created_at"]
        assert ts0 >= ts1


@pytest.mark.asyncio(loop_scope="session")
class TestGetBet:
    """GET /bet/{id} — fetch single bet."""

    async def test_get_bet_by_id_returns_200(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """GET /bet/{id} returns 200 + BetRead on existing bet."""
        event_id = seed_event()
        post_resp = await client.post("/bet", json={"event_id": str(event_id), "amount": "15.50"})
        assert post_resp.status_code == 201
        bet_id = post_resp.json()["id"]

        response = await client.get(f"/bet/{bet_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == bet_id
        assert body["event_id"] == str(event_id)
        assert Decimal(body["amount"]) == Decimal("15.50")

    async def test_get_bet_by_id_returns_404(self, client: AsyncClient) -> None:
        """GET /bet/{id} returns 404 with detail='bet {id} not found' on miss."""
        missing_id = uuid4()
        response = await client.get(f"/bet/{missing_id}")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert str(missing_id) in detail
        assert "not found" in detail
