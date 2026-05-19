"""Integration tests for line_provider HTTP routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from freezegun import freeze_time
from httpx import AsyncClient

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState
from tests.line_provider._fakes import FakeEventBus


def _iso_future(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _iso_past() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _iso_naive_future() -> str:
    return (datetime.now() + timedelta(hours=1)).isoformat()


def _create_body(coefficient: str = "1.50", deadline: str | None = None) -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "coefficient": coefficient,
        "deadline": deadline or _iso_future(),
    }


class TestWiring:
    """Lifespan + router wiring smoke tests."""

    async def test_lifespan_wires_event_store(self, app: FastAPI) -> None:
        """Lifespan creates InMemoryEventStore in app.state.

        ``NoopEventBus`` is replaced with ``RabbitEventBus`` in production
        lifespan; the autouse ``_reset_event_store`` fixture replaces the
        bus with ``FakeEventBus`` for test isolation, so only the
        event_store type is verified here. Production ``RabbitEventBus``
        wiring is verified in
        ``test_lifespan.py::TestLineProviderLifespan``.
        """
        assert isinstance(app.state.event_store, InMemoryEventStore)

    async def test_app_registers_events_router(self, app: FastAPI) -> None:
        """build_app() includes events.router alongside health.router."""
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/health" in paths
        assert "/event" in paths
        assert "/event/{event_id}" in paths
        assert "/events" in paths


class TestCreate:
    async def test_post_event_returns_201(self, client: AsyncClient) -> None:
        """POST /event 201 + EventRead with state=NEW."""
        body = _create_body()
        response = await client.post("/event", json=body)
        assert response.status_code == 201
        data = response.json()
        assert data["event_id"] == body["event_id"]
        assert data["state"] == "NEW"
        assert data["coefficient"] == "1.50"

    async def test_post_duplicate_returns_409(self, client: AsyncClient) -> None:
        """Duplicate event_id returns 409."""
        body = _create_body()
        await client.post("/event", json=body)
        response = await client.post("/event", json=body)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    async def test_post_negative_coefficient_returns_422(self, client: AsyncClient) -> None:
        """coefficient < 0 -> 422."""
        response = await client.post("/event", json=_create_body(coefficient="-1.00"))
        assert response.status_code == 422

    async def test_post_zero_coefficient_returns_422(self, client: AsyncClient) -> None:
        """coefficient == 0 -> 422 (gt=0 enforced)."""
        response = await client.post("/event", json=_create_body(coefficient="0"))
        assert response.status_code == 422

    async def test_post_three_decimal_places_returns_422(self, client: AsyncClient) -> None:
        """coefficient with >2 decimal places -> 422."""
        response = await client.post("/event", json=_create_body(coefficient="1.234"))
        assert response.status_code == 422

    async def test_post_past_deadline_returns_422(self, client: AsyncClient) -> None:
        """deadline in the past -> 422 on POST."""
        response = await client.post("/event", json=_create_body(deadline=_iso_past()))
        assert response.status_code == 422

    async def test_post_naive_deadline_returns_422(self, client: AsyncClient) -> None:
        """Naive datetime -> 422 (AwareDatetime enforced)."""
        response = await client.post("/event", json=_create_body(deadline=_iso_naive_future()))
        assert response.status_code == 422

    async def test_post_extra_field_returns_422(self, client: AsyncClient) -> None:
        """Extra fields forbidden by EventCreate(extra='forbid')."""
        body = _create_body()
        body["state"] = "NEW"
        response = await client.post("/event", json=body)
        assert response.status_code == 422

    async def test_post_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """event_id must be a valid UUID."""
        body = _create_body()
        body["event_id"] = "not-a-uuid"
        response = await client.post("/event", json=body)
        assert response.status_code == 422


class TestUpdate:
    async def test_put_event_returns_200(self, client: AsyncClient) -> None:
        """PUT /event/{id} NEW->FINISHED_WIN returns 200 + EventRead."""
        create_body = _create_body()
        await client.post("/event", json=create_body)

        put_body = {
            "coefficient": "2.50",
            "deadline": _iso_future(),
            "state": "FINISHED_WIN",
        }
        response = await client.put(f"/event/{create_body['event_id']}", json=put_body)
        assert response.status_code == 200
        assert response.json()["state"] == "FINISHED_WIN"

    async def test_put_missing_returns_404(self, client: AsyncClient) -> None:
        """PUT on absent event -> 404."""
        put_body = {
            "coefficient": "2.00",
            "deadline": _iso_future(),
            "state": "FINISHED_WIN",
        }
        response = await client.put(f"/event/{uuid4()}", json=put_body)
        assert response.status_code == 404

    async def test_put_reverse_returns_422_with_detail(self, client: AsyncClient) -> None:
        """FINISHED_WIN->NEW returns 422 with explicit message."""
        create_body = _create_body()
        await client.post("/event", json=create_body)
        await client.put(
            f"/event/{create_body['event_id']}",
            json={
                "coefficient": "2.00",
                "deadline": _iso_future(),
                "state": "FINISHED_WIN",
            },
        )
        response = await client.put(
            f"/event/{create_body['event_id']}",
            json={
                "coefficient": "2.00",
                "deadline": _iso_future(),
                "state": "NEW",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "state transition FINISHED_WIN->NEW not allowed"

    async def test_put_no_op_state_returns_200(self, client: AsyncClient, app: FastAPI) -> None:
        """PUT with state == current_state mutates fields, does NOT publish."""
        fake = FakeEventBus()
        app.state.event_bus = fake

        create_body = _create_body()
        await client.post("/event", json=create_body)
        response = await client.put(
            f"/event/{create_body['event_id']}",
            json={
                "coefficient": "9.99",
                "deadline": _iso_future(),
                "state": "NEW",
            },
        )
        assert response.status_code == 200
        assert response.json()["coefficient"] == "9.99"
        assert fake.calls == []

    async def test_put_publishes_via_event_bus_on_terminal_transition(
        self, client: AsyncClient, app: FastAPI
    ) -> None:
        """NEW->FINISHED_WIN triggers event_bus.publish with event.finished.win."""
        fake = FakeEventBus()
        app.state.event_bus = fake

        create_body = _create_body()
        await client.post("/event", json=create_body)
        response = await client.put(
            f"/event/{create_body['event_id']}",
            json={
                "coefficient": "2.00",
                "deadline": _iso_future(),
                "state": "FINISHED_WIN",
            },
            headers={"X-Request-ID": "trace-publish"},
        )
        assert response.status_code == 200
        assert len(fake.calls) == 1
        message, routing_key = fake.calls[0]
        assert routing_key == "event.finished.win"
        assert str(message.event_id) == create_body["event_id"]
        assert message.correlation_id == "trace-publish"


class TestGet:
    async def test_get_event_by_id_returns_200(self, client: AsyncClient) -> None:
        """GET /event/{id} returns 200 + EventRead."""
        create_body = _create_body()
        await client.post("/event", json=create_body)
        response = await client.get(f"/event/{create_body['event_id']}")
        assert response.status_code == 200
        assert response.json()["event_id"] == create_body["event_id"]

    async def test_get_missing_returns_404(self, client: AsyncClient) -> None:
        """GET on absent id returns 404."""
        response = await client.get(f"/event/{uuid4()}")
        assert response.status_code == 404


class TestList:
    async def test_get_events_returns_active(self, client: AsyncClient, app: FastAPI) -> None:
        fixed_now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        store: InMemoryEventStore = app.state.event_store
        active_id = uuid4()
        finished_id = uuid4()
        past_id = uuid4()
        future = fixed_now + timedelta(hours=1)
        past = fixed_now - timedelta(hours=1)
        await store.add(
            Event(
                event_id=active_id,
                coefficient=Decimal("1.50"),
                deadline=future,
                state=EventState.NEW,
            )
        )
        await store.add(
            Event(
                event_id=finished_id,
                coefficient=Decimal("1.50"),
                deadline=future,
                state=EventState.FINISHED_WIN,
            )
        )
        await store.add(
            Event(
                event_id=past_id,
                coefficient=Decimal("1.50"),
                deadline=past,
                state=EventState.NEW,
            )
        )

        with freeze_time(fixed_now):
            response = await client.get("/events")
        assert response.status_code == 200
        ids = {item["event_id"] for item in response.json()}
        assert ids == {str(active_id)}

    async def test_get_events_empty(self, client: AsyncClient) -> None:
        """Empty store -> 200 + []."""
        response = await client.get("/events")
        assert response.status_code == 200
        assert response.json() == []


class TestRequestId:
    async def test_request_id_echoed_on_post(self, client: AsyncClient) -> None:
        """X-Request-ID header echoed in response (middleware invariant preserved)."""
        body = _create_body()
        response = await client.post(
            "/event",
            json=body,
            headers={"X-Request-ID": "trace-echo"},
        )
        assert response.headers["X-Request-ID"] == "trace-echo"

    async def test_request_id_propagated_to_event_bus(
        self, client: AsyncClient, app: FastAPI
    ) -> None:
        """X-Request-ID forwarded as correlation_id to published message."""
        fake = FakeEventBus()
        app.state.event_bus = fake

        create_body = _create_body()
        await client.post("/event", json=create_body)
        await client.put(
            f"/event/{create_body['event_id']}",
            json={
                "coefficient": "2.00",
                "deadline": _iso_future(),
                "state": "FINISHED_LOSE",
            },
            headers={"X-Request-ID": "trace-correlate"},
        )
        assert fake.calls[0][0].correlation_id == "trace-correlate"


class TestHealth:
    async def test_health_still_returns_ok_after_events_router(self, client: AsyncClient) -> None:
        """GET /health continues to return 200 after events router is added."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
