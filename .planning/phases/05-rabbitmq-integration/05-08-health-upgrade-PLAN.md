---
phase: 05
plan: 08
type: execute
wave: 2
depends_on: [05, 07]
files_modified:
  - src/bet_maker/entrypoints/api/health.py
  - tests/bet_maker/test_health.py
autonomous: true
requirements: [BM-09]
must_haves:
  truths:
    - "/health 200 returns {status: ok, checks: {postgres: ok, rabbitmq: ok, rabbitmq_consumer: ok}}"
    - "/health 503 if PG ping fails OR broker.ping fails OR len(subscribers) == 0 (D-20 / SC#5)"
    - "broker.ping(timeout=1.0) called per request — bounded latency"
    - "len(router.broker.subscribers) > 0 check uses the public list attribute"
  artifacts:
    - path: "src/bet_maker/entrypoints/api/health.py"
      provides: "extended health handler with RMQ + subscriber checks"
      contains: "rabbitmq_consumer"
    - path: "tests/bet_maker/test_health.py"
      provides: "3 new 503-branch tests"
      contains: "test_health_returns_503_when_rmq_down"
  key_links:
    - from: "src/bet_maker/entrypoints/api/health.py"
      to: "router.broker.ping + router.broker.subscribers"
      via: "RabbitBrokerDep from facades/deps.py"
      pattern: "broker.ping"
---

<objective>
Extend `/health` to the Phase 5 contract (D-20 / SC#5). Three checks now AND-gated:

1. `await ping_postgres(engine)` (existing).
2. `await broker.ping(timeout=1.0)` (new).
3. `len(broker.subscribers) > 0` (new — proves consumer registered, NOT just connected).

Response shape (200 happy / 503 degraded):
```json
{
  "status": "ok" | "degraded",
  "checks": {
    "postgres": "ok" | "down",
    "rabbitmq": "ok" | "down",
    "rabbitmq_consumer": "ok" | "no subscribers"
  }
}
```

Pitfalls guarded:
- **SC#5**: 503 fires on ANY of three failures (not just PG).
- **R6**: subscriber-count check ensures `/health` does NOT report green if no subscriber registered (e.g., due to an import error).
- **Latency**: `broker.ping(timeout=1.0)` bounded — does not block /health indefinitely if broker hangs.

Output: 1 extended handler, 3 new tests on top of existing test_health.py.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/phases/05-rabbitmq-integration/05-CONTEXT.md
@.planning/phases/05-rabbitmq-integration/05-RESEARCH.md
@.planning/phases/05-rabbitmq-integration/05-PATTERNS.md
@src/bet_maker/entrypoints/api/health.py
@src/bet_maker/facades/deps.py
@tests/bet_maker/test_health.py

<interfaces>
<!-- Plan 05 added RabbitBrokerDep; we consume it here -->

From src/bet_maker/facades/deps.py (Plan 05):
```python
def get_rabbit_broker(request: Request) -> RabbitBroker: ...
RabbitBrokerDep = Annotated[RabbitBroker, Depends(get_rabbit_broker)]
```

From RESEARCH §6 (verified API):
```python
rmq_ok = await router.broker.ping(timeout=1.0)  # returns bool
sub_count = len(router.broker.subscribers)       # public list attribute
```

From src/bet_maker/entrypoints/api/health.py (Phase 3 current):
```python
@router.get("/health")
async def health(engine: EngineDep) -> JSONResponse:
    pg_ok = await ping_postgres(engine)
    if pg_ok:
        return JSONResponse(200, {"status": "ok", "checks": {"postgres": "ok"}})
    return JSONResponse(503, {"status": "degraded", "checks": {"postgres": "down"}})
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add 3 new 503-branch tests to tests/bet_maker/test_health.py</name>
  <read_first>
    - tests/bet_maker/test_health.py (full file — existing patch pattern reference)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/bet_maker/test_health.py (modified)`
  </read_first>
  <behavior>
    Add 3 new test methods to the existing `TestHealth` class (keeping the existing 3 tests untouched):

    - `test_health_returns_503_when_rmq_down`: patch `router.broker.ping` to return False; assert 503 + `body["checks"]["rabbitmq"] == "down"` AND `body["checks"]["postgres"] == "ok"` (PG still works).
    - `test_health_returns_503_when_no_subscribers`: patch `router.broker.subscribers` property to return `[]`; assert 503 + `body["checks"]["rabbitmq_consumer"] == "no subscribers"`.
    - `test_health_returns_200_includes_rabbitmq_checks`: hit /health in happy state (all three OK); assert `body["checks"]["rabbitmq"] == "ok"` AND `body["checks"]["rabbitmq_consumer"] == "ok"` AND status 200.

    Also update the existing `test_health_returns_status_ok` test to assert the new `checks` keys exist (rabbitmq, rabbitmq_consumer) instead of only `postgres` — backward-incompatible shape change requires updating the existing assertion.
  </behavior>
  <action>
    Step A — Update the existing `test_health_returns_status_ok` test. Currently it asserts:
    ```python
    assert body["checks"]["postgres"] == "ok"
    ```
    Extend to also assert:
    ```python
    assert body["checks"]["rabbitmq"] == "ok"
    assert body["checks"]["rabbitmq_consumer"] == "ok"
    ```

    Step B — Append 3 new test methods to the existing `TestHealth` class:

    ```python
    async def test_health_returns_503_when_rmq_down(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """D-20 / SC#5: 503 when broker.ping fails (RMQ unreachable)."""
        from bet_maker.entrypoints.messaging import router
        with patch.object(router.broker, "ping", new=AsyncMock(return_value=False)):
            response = await client.get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["rabbitmq"] == "down"
        # rabbitmq_consumer still 'ok' because subscriber list is intact
        assert body["checks"]["rabbitmq_consumer"] == "ok"

    async def test_health_returns_503_when_no_subscribers(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """D-20 / SC#5 / R6: 503 when len(broker.subscribers) == 0."""
        from bet_maker.entrypoints.messaging import router
        # Mock the subscribers attribute to be empty
        with patch.object(type(router.broker), "subscribers", new_callable=lambda: property(lambda self: [])):
            response = await client.get("/health")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["rabbitmq_consumer"] == "no subscribers"

    async def test_health_returns_200_includes_rabbitmq_checks(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """D-20: happy path returns 200 with all three checks 'ok'."""
        response = await client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"]["postgres"] == "ok"
        assert body["checks"]["rabbitmq"] == "ok"
        assert body["checks"]["rabbitmq_consumer"] == "ok"
    ```

    Note on patching `subscribers`: it's a list attribute on the broker instance per RESEARCH §6. `patch.object(router.broker, "subscribers", new=[])` should work directly. If that fails because it's a property at the class level, use `patch.object(type(router.broker), "subscribers", new_callable=lambda: property(lambda self: []))`. Executor: try the simple form first.

    The `app` fixture is session-scoped and the lifespan was started with real RMQ via Plan 07 wiring — the bet-maker tests already work this way. If session-scope fixture mismatch arises, the `app` fixture in `tests/bet_maker/conftest.py` already requires `pg_dsn` only; the `amqp_url` fixture is independent and must be injected as a dependency of `app`. UPDATE `tests/bet_maker/conftest.py` `app` fixture to also accept `amqp_url` and env-poke `BET_MAKER_RABBITMQ_URL` (see Task 2 below for the conftest update — it is required to make the existing app fixture work after Plan 07 enables real broker).
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_health.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'test_health_returns_503_when_rmq_down' tests/bet_maker/test_health.py`
    - `grep -q 'test_health_returns_503_when_no_subscribers' tests/bet_maker/test_health.py`
    - `grep -q 'test_health_returns_200_includes_rabbitmq_checks' tests/bet_maker/test_health.py`
    - `grep -q 'body\["checks"\]\["rabbitmq"\]' tests/bet_maker/test_health.py`
    - `grep -q '"no subscribers"' tests/bet_maker/test_health.py`
    - `uv run pytest tests/bet_maker/test_health.py -x -q` exits 0 (existing 3 + new 3 = 6 tests pass)
    - `uv run mypy tests/bet_maker/test_health.py` exits 0
  </acceptance_criteria>
  <done>3 new test methods green; existing 3 still pass after shape update; full health test class covers SC#5.</done>
</task>

<task type="auto">
  <name>Task 2: Update tests/bet_maker/conftest.py app fixture to inject amqp_url (required by Plan 07 wiring)</name>
  <read_first>
    - tests/bet_maker/conftest.py (full file)
    - tests/conftest.py (Plan 01 added rabbitmq_container + amqp_url session fixtures)
  </read_first>
  <action>
    Modify the existing `app` fixture in `tests/bet_maker/conftest.py` so it injects `amqp_url` env var alongside the existing `BET_MAKER_POSTGRES_DSN` poke. This is required because Plan 07's bet-maker lifespan now connects to the real broker, and tests must point at the testcontainer URL.

    Change the function signature and body of the `app` fixture:

    Current:
    ```python
    @pytest_asyncio.fixture(scope="session")
    async def app(pg_dsn: str) -> AsyncIterator[FastAPI]:
        os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
        try:
            application = build_app()
            async with LifespanManager(application):
                yield application
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
    ```

    Replace with:
    ```python
    @pytest_asyncio.fixture(scope="session")
    async def app(pg_dsn: str, amqp_url: str) -> AsyncIterator[FastAPI]:
        """Session-scoped bet-maker FastAPI app with PG + RMQ wired to testcontainers.

        Plan 05-08 / Plan 05-07: bet-maker lifespan now requires a reachable
        RabbitMQ — points at the testcontainers `amqp_url` fixture.
        """
        os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
        os.environ["BET_MAKER_RABBITMQ_URL"] = amqp_url
        try:
            from bet_maker.app import build_app  # noqa: PLC0415
            application = build_app()
            async with LifespanManager(application):
                yield application
        finally:
            os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
            os.environ.pop("BET_MAKER_RABBITMQ_URL", None)
    ```

    Do the same for the existing `line_provider_app` fixture (it must also point at the testcontainers AMQP URL because Plan 07 wired the real broker into line-provider too):
    ```python
    @pytest_asyncio.fixture(scope="session")
    async def line_provider_app(amqp_url: str) -> AsyncIterator[FastAPI]:
        os.environ["LINE_PROVIDER_RABBITMQ_URL"] = amqp_url
        try:
            from line_provider.app import build_app  # noqa: PLC0415
            application = build_app()
            async with LifespanManager(application):
                yield application
        finally:
            os.environ.pop("LINE_PROVIDER_RABBITMQ_URL", None)
    ```

    Verify with `uv run pytest tests/bet_maker -x -q --co` first (collect-only) to confirm fixture wiring is sound before running the suite.
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker -x -q --co 2>&amp;1 | tail -3 &amp;&amp; uv run pytest tests/bet_maker/test_health.py tests/bet_maker/test_lifespan.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'amqp_url: str' tests/bet_maker/conftest.py`
    - `grep -q 'BET_MAKER_RABBITMQ_URL' tests/bet_maker/conftest.py`
    - `grep -q 'LINE_PROVIDER_RABBITMQ_URL' tests/bet_maker/conftest.py`
    - `uv run pytest tests/bet_maker -x -q --co` exits 0 (collection passes)
    - `uv run pytest tests/bet_maker/test_health.py tests/bet_maker/test_lifespan.py -x -q` exits 0
    - `uv run mypy tests/bet_maker/conftest.py` exits 0
  </acceptance_criteria>
  <done>Existing app fixture now bound to testcontainers RMQ; lifespan starts cleanly under tests.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement extended /health handler in src/bet_maker/entrypoints/api/health.py</name>
  <read_first>
    - src/bet_maker/entrypoints/api/health.py (full file)
    - src/bet_maker/facades/deps.py (RabbitBrokerDep from Plan 05)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-20
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Operational Checks
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/entrypoints/api/health.py (modified)`
  </read_first>
  <behavior>
    Endpoint must:
    - Inject `engine: EngineDep` and `broker: RabbitBrokerDep`.
    - Compute three booleans: `pg_ok`, `rmq_ok`, `subs_ok`.
    - Use `await broker.ping(timeout=1.0)` and `len(broker.subscribers) > 0`.
    - Return 200 only if all three true; otherwise 503 with per-check status.
  </behavior>
  <action>
    Overwrite `src/bet_maker/entrypoints/api/health.py`:

    ```python
    from __future__ import annotations

    from fastapi import APIRouter
    from fastapi.responses import JSONResponse

    from bet_maker.facades.deps import EngineDep, RabbitBrokerDep
    from bet_maker.infrastructure.db.pings import ping_postgres

    router = APIRouter(tags=["health"])


    @router.get("/health")
    async def health(engine: EngineDep, broker: RabbitBrokerDep) -> JSONResponse:
        """GET /health — PG + RMQ + subscriber-count check (D-20 / SC#5).

        Returns 200 only when all three are healthy:
          - ping_postgres(engine) returns True (Phase 3 D-26 baseline)
          - broker.ping(timeout=1.0) returns True (RMQ reachable)
          - len(broker.subscribers) > 0 (consumer registered, R6)

        Otherwise returns 503 with per-check status string. docker-compose
        healthcheck consumes the HTTP status; observability tools consume the
        body shape.
        """
        pg_ok = await ping_postgres(engine)
        rmq_ok = await broker.ping(timeout=1.0)
        subs_ok = len(broker.subscribers) > 0

        if pg_ok and rmq_ok and subs_ok:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "checks": {
                        "postgres": "ok",
                        "rabbitmq": "ok",
                        "rabbitmq_consumer": "ok",
                    },
                },
            )
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "checks": {
                    "postgres": "ok" if pg_ok else "down",
                    "rabbitmq": "ok" if rmq_ok else "down",
                    "rabbitmq_consumer": "ok" if subs_ok else "no subscribers",
                },
            },
        )
    ```

    Do NOT catch exceptions from `broker.ping` — `ping(timeout=...)` returns False on transport failure per FastStream API. If a programming error raises, it propagates to FastAPI as a 500 (correct behaviour — handler is broken, not the service).
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_health.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from bet_maker.facades.deps import EngineDep, RabbitBrokerDep' src/bet_maker/entrypoints/api/health.py`
    - `grep -q 'await broker.ping(timeout=1.0)' src/bet_maker/entrypoints/api/health.py`
    - `grep -q 'len(broker.subscribers)' src/bet_maker/entrypoints/api/health.py`
    - `grep -q '"rabbitmq": "ok"' src/bet_maker/entrypoints/api/health.py`
    - `grep -q '"rabbitmq_consumer"' src/bet_maker/entrypoints/api/health.py`
    - `grep -q '"no subscribers"' src/bet_maker/entrypoints/api/health.py`
    - `grep -q 'pg_ok and rmq_ok and subs_ok' src/bet_maker/entrypoints/api/health.py`
    - `uv run pytest tests/bet_maker/test_health.py -x -q` exits 0
    - `uv run mypy src/bet_maker/entrypoints/api/health.py` exits 0
    - `uv run ruff check src/bet_maker/entrypoints/api/health.py` exits 0
  </acceptance_criteria>
  <done>/health 503-on-any-failure semantic shipped; SC#5 closed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| /health endpoint | Surface used by docker-compose healthcheck + operator observability — must accurately reflect downstream readiness |
| broker.ping latency | Bounded by `timeout=1.0` — failure mode must NOT cascade into request-handling thread starvation |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-08-01 | Denial of service | broker.ping hangs indefinitely -> /health blocks | mitigate | `timeout=1.0` explicit; FastStream returns False on timeout. |
| T-05-08-02 | Repudiation | /health green while consumer not registered (e.g., import-time error) | mitigate | `len(broker.subscribers) > 0` check (R6) — handler-load failure leaves subscribers=[]; SC#5 enforces 503. |
| T-05-08-03 | Information disclosure | /health response body exposes internal state | accept | Status strings are operational metadata (postgres/rabbitmq/consumer); no PII, no DSN/credentials. |
| T-05-08-04 | Spoofing | An attacker hits /health expecting 200, gets 503; can probe internal failure mode | accept | /health is intentionally public for docker-compose healthcheck; the 503 detail is bounded to three known states. Out of scope for test task. |
</threat_model>

<verification>
- `uv run pytest tests/bet_maker/test_health.py -x -q` exits 0 (6 tests)
- `uv run pytest -q` exits 0 (full suite green)
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- Manual smoke (post-implementation): `curl http://localhost:8001/health` returns 200 with the new body shape after `docker compose up`.
</verification>

<success_criteria>
- /health returns 200 only when all three checks pass; 503 otherwise
- Response body shape matches `{status, checks: {postgres, rabbitmq, rabbitmq_consumer}}`
- 6 health tests pass (3 existing + 3 new)
- Conftest app fixtures wired to amqp_url
- No regression in other test suites
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-08-health-upgrade-SUMMARY.md` documenting: handler diff, test counts, sample 200 + 503 JSON bodies, confirmation that `len(router.broker.subscribers) > 0` is the only public-API form used.
</output>
