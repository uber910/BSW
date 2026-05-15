# Phase 4: bet-maker HTTP integration with line-provider — Research

**Researched:** 2026-05-15
**Domain:** Inter-service HTTP integration (async Python) — httpx singleton client + tenacity retry + respx mocking + ASGITransport integration tests
**Confidence:** HIGH (all libraries verified via Context7 + PyPI; project code shape inspected end-to-end; TZ source re-verified against D-01 cache-removal decision)

## Summary

Phase 4 wires `bet-maker` into `line-provider` over HTTP. The phase has a narrow, well-bounded surface:

1. **One singleton `httpx.AsyncClient`** lives in `entrypoints/lifespan.py`, pinned to `app.state.line_provider_http_client`, closed in `finally` before `engine.dispose()`.
2. **Two independent facades** consume that client — `HttpEventLookup` (validation path for `POST /bet`) and `list_active_events` selector (proxy path for `GET /events`). Both share a single `make_retry_decorator(attempts, max_backoff)` factory and a single `LineProviderUnavailable` exception, both living in `facades/line_provider_client.py`.
3. **Service-boundary `EventRead` schema** is added to `bet_maker/schemas/events.py` (mirror of the existing intentional `EventState` duplication).
4. **No TTL cache** (locked in CONTEXT.md D-01; TZ allows lag but does not require cache — verified verbatim on TZ page 3). First task of the phase syncs `REQUIREMENTS.md` BM-04 and `ROADMAP.md` Phase 4 SC#1 to remove the cache wording.
5. **Tests:** unit tests with `respx>=0.22,<0.23` (new dev-dep) for facade-level retry/4xx/5xx scenarios; one integration test that drives both FastAPI apps in a single event loop via `ASGITransport` + `asgi-lifespan.LifespanManager` (already in dev-deps).

**Primary recommendation:** Treat Phase 4 as a *mechanical wiring phase, not a design phase.* All design questions are locked in CONTEXT.md D-01..D-21. Researcher's value-add here is verifying library API shapes, exception hierarchies, and timeout/retry semantics so the planner can write task actions that compile on the first run.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Singleton HTTP client lifecycle | API / Backend (lifespan) | — | Connection pool must outlive a single request; closed on shutdown to drain in-flight connections before engine.dispose() |
| Inter-service request retry policy | Backend (facade layer) | — | Retry sits *between* the route and the wire; routes stay thin, facades own resilience |
| Event validation on `POST /bet` | Backend (interactor) | Backend (facade: HttpEventLookup) | Interactor `place_bet` is unchanged from P3; HttpEventLookup is a Protocol-substituted facade |
| `GET /events` proxy | Backend (selector + route) | — | Pure read; no DB; no UoW; selector returns DTO list, route returns 200 + body |
| LP unavailability handling | Backend (route exception mapper) | — | `LineProviderUnavailable` -> 503 at route layer; interactor and selector raise, do not map |
| Mock HTTP transport for unit tests | Test infrastructure (respx) | — | respx is a route-table over httpx's transport API; does NOT need a real network or real LP app |
| Two-app integration test | Test infrastructure (ASGITransport + asgi-lifespan) | — | Both FastAPI apps run in one Python process / one event loop; LP's lifespan must be triggered via `LifespanManager` (HTTPX does NOT manage ASGI lifespan automatically — verified via Context7 [CITED]) |

## Standard Stack

### Core (already pinned, no changes needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | `>=0.28,<0.29` (current 0.28.1) | Singleton `AsyncClient`; `ASGITransport` for integration tests; `Timeout`, `TransportError`, `HTTPStatusError` exception classes | Already in `pyproject.toml`. Same lib for prod and tests — verified via Context7 `/encode/httpx` [VERIFIED] |
| tenacity | `>=9.1,<10` (current 9.1.4) | `@retry(stop=stop_after_attempt(N), wait=wait_exponential(...), retry=retry_if_exception_type(...), before_sleep=..., reraise=True)` decorator factory | Already in `pyproject.toml`. AsyncRetrying auto-detected when decorating async fns — verified via Context7 `/jd/tenacity` [VERIFIED] |
| pydantic | `>=2.13,<3` | `EventRead` model (`extra="forbid"`, `frozen=True`) | Already in pyproject |
| pydantic-settings | `>=2.14,<3` | 2 new fields on `BetMakerSettings` (D-21) | Already in pyproject |
| fastapi | `>=0.115,<0.137` | `APIRouter`, `Depends`, `HTTPException(status_code=503, detail=...)` for the new `events.py` route | Already in pyproject |

### Dev (one new dep)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **respx** | `>=0.22,<0.23` (per CONTEXT.md D-15) | Mock backend for httpx — patches httpx transport, sequences responses via `mock(side_effect=[Response(500), Response(500), Response(200, json=...)])` | Standard community choice for httpx mocking. Current PyPI: 0.23.1 (2026-04-08). 0.22.x line still maintained; CONTEXT pin to `>=0.22,<0.23` is the conservative choice. [VERIFIED: PyPI] |
| asgi-lifespan | `>=2.1,<3` | Triggers FastAPI lifespan events when running via `ASGITransport` (HTTPX does NOT call `startup`/`shutdown` automatically — official httpx docs are explicit about this) | Already in dev-deps (P2 Plan 02-01). Required by integration test D-16 because the LP app needs `app.state.event_store` populated by lifespan before the bet-maker proxy hits `GET /events`. [VERIFIED: Context7 /encode/httpx] |

### Version verification (executed)

```bash
# Already verified during research session
npm/curl -fsS https://pypi.org/pypi/respx/json   -> 0.23.1 (2026-04-08), requires httpx>=0.25.0
                                                  -> 0.22.0 (2024-12-19), requires httpx>=0.25.0
# Both 0.22 and 0.23 lines are compatible with httpx 0.28; CONTEXT pin 0.22 is safe.
```

[VERIFIED: PyPI 2026-05-15]

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `respx` | `pytest-httpx` | Equivalent capability. `pytest-httpx` is fixture-first; `respx` has cleaner `respx.mock(base_url=...)` decorator + `respx_mock` fixture. CONTEXT.md D-15 + deferred Idea fix this on `respx` — do not relitigate. |
| `httpx.AsyncClient` singleton | Per-request client | Per-request constructs a fresh connection pool every call -> defeats keep-alive, blows out the FD limit under load, and breaks Pitfall A2 (event-loop sharing). PITFALLS.md row 1004 explicitly bans this. [CITED: PITFALLS.md] |
| ASGITransport for cross-app test | Real `docker compose up` in CI | Real docker = slow, flaky, harder to debug. ASGITransport runs both apps in one process / one event loop — purpose-built for this scenario. ARCHITECTURE.md lines 991-1014 codify this pattern. [CITED: ARCHITECTURE.md] |
| Manual `try/except + while` retry loop | tenacity decorator | tenacity composes `stop`/`wait`/`retry`/`before_sleep` declaratively, handles AsyncRetrying transparently, and is already pinned. Hand-rolled = re-implement well-tested logic. |
| Unified `LineProviderClient.get_event() / .get_events()` facade | Two independent facades (D-11) | CONTEXT.md D-11 explicitly rejects the unified facade to prevent coupling read-path and validation-path. Locked decision — do not relitigate. |

**Installation:**

```bash
uv add --group dev "respx>=0.22,<0.23"
uv sync --frozen
```

## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: TTL cache REMOVED from P4 scope.** First task syncs `REQUIREMENTS.md` BM-04 (remove "+ tiny TTL cache" wording, keep "проксирует список активных событий из line-provider через httpx с retry (tenacity)") and `ROADMAP.md` Phase 4 SC#1 (replace "with acceptable lag (cached via TTL dict)" -> "with acceptable lag (свежий результат каждого запроса; отставание = длительность одного HTTP-вызова к LP плюс retry-backoff)"). README P7 (DOC-02) mentions cache as a "next-step extension."

**D-02: Singleton `httpx.AsyncClient`** created in `entrypoints/lifespan.py` as:
```python
http_client = httpx.AsyncClient(
    base_url=str(settings.line_provider_base_url),
    timeout=httpx.Timeout(5.0),  # total timeout, not infinite-default
)
app.state.line_provider_http_client = http_client
```
`finally`: `await http_client.aclose()` **before** `await engine.dispose()`.

**D-03: HTTP-route retry policy:** 3 attempts, `wait_exponential(multiplier=0.5, min=0.5, max=2)`, `reraise=True`. Worst case ~3s before client response. Parametrized via `BetMakerSettings.line_provider_http_attempts` + `..._backoff_max_s` (D-21). Retry decorator factory `make_retry_decorator(attempts, max_backoff)` lives in `facades/line_provider_client.py` and is reused by both `HttpEventLookup` and `list_active_events`.

**D-04: Reconciler retry policy (5 attempts, max_backoff=10) is DEFERRED to P6 BM-12** via the same `make_retry_decorator` factory with different parameters. P4 fixes intent only; do not implement reconciler settings now.

**D-05: Retry on:** `httpx.TransportError` (covers `TimeoutException`, `ConnectError`, `ReadError`, `NetworkError`) **+** `httpx.HTTPStatusError` where `status_code >= 500`. 4xx (404/422/400) **propagate without retry** — they are contract responses from LP. **429 is NOT retried** — LP is not rate-limited, adding 429 retry paints an incorrect reliability picture.

**D-06: `tenacity.before_sleep` hook + structlog binding** (event_id, attempt_number, sleep_s). Exact wrapper shape is Claude's discretion (closure, decorator-factory, or `partial`), but the log line MUST include `attempt_number`, `sleep_s`, `exception_type`.

**D-07: `LineProviderUnavailable(reason: str)`** — new exception class in `facades/line_provider_client.py`. Raised by `HttpEventLookup.get_event` and `list_active_events` after retry exhaustion on 5xx/timeout.

**D-08: POST /bet on `LineProviderUnavailable` -> 503** with `{"detail":"event validation unavailable: line-provider unreachable"}`. No PG write. `EventNotBettable -> 422` (P3 D-06) preserved.

**D-09: 404 from LP** in `HttpEventLookup.get_event` -> `return None` -> interactor maps to `EventNotBettable("event not found")` -> 422 `event {id} is not bettable: event not found`. Existing happy-path P3 unchanged.

**D-10: GET /events bet-maker on `LineProviderUnavailable` -> 503** `{"detail":"line-provider unreachable"}`. Empty list -> 200 + `[]` (normal success).

**D-11: Two independent facades** — NOT a unified `LineProviderClient`:
- `facades/http_event_lookup.py` — `HttpEventLookup(EventLookup Protocol)` with constructor `(http_client: httpx.AsyncClient, *, attempts=3, max_backoff=2.0)` and method `get_event(event_id)`.
- `selectors/list_active_events.py` — `async def list_active_events(http_client, *, attempts=3, max_backoff=2.0) -> list[EventRead]`.
- Shared `LineProviderUnavailable` + `make_retry_decorator` factory live in `facades/line_provider_client.py`.

**D-12: Single singleton httpx client per service**, pinned to `app.state.line_provider_http_client`. Provider `get_line_provider_http_client(request)` in `facades/deps.py` + `LineProviderHttpClientDep` alias.

**D-13: `EventRead`** added to `bet_maker/schemas/events.py` with `event_id: UUID, coefficient: Decimal, deadline: datetime, state: EventState`, `extra="forbid"`, `frozen=True`. Intentional service-boundary duplication (symmetric to existing `EventState` duplication).

**D-14: Production lifespan** sets `app.state.event_lookup = HttpEventLookup(http_client=...)`. `StubEventLookup` stays in `facades/event_lookup.py` for unit tests of `place_bet` (P3 D-23 truncate-fixture pattern); NOT removed.

**D-15: Unit tests for `HttpEventLookup` + `list_active_events` use `respx`** (new dev-dep `respx>=0.22,<0.23`). Scenarios: 200, 404, 4xx-propagates-no-retry, 5xx-exhausts-retries, 5xx-then-200-retry-succeeds, empty `[]`, multi-event list, timeout-retries.

**D-16: Integration test `tests/bet_maker/test_events_routes.py`** uses two FastAPI apps in one event loop via `ASGITransport`. Override `app.dependency_overrides[get_line_provider_http_client] = lambda: httpx.AsyncClient(transport=ASGITransport(app=line_provider_app))`. `asyncio_default_fixture_loop_scope="session"` is already in `pyproject.toml` — keep fixture scope == event-loop scope.

**D-17: Extend `test_bet_routes.py`** with `TestPostBet503` — fake `EventLookup` raises `LineProviderUnavailable("simulated")` via `app.dependency_overrides[get_event_lookup]` -> expect 503.

**D-18: `/health` untouched in P4.** Read-side `/events` returns 503 when LP down; `/bets` and `/bet/{id}` keep working. LP-unreachability MUST NOT take bet-maker /health down.

**D-19: Startup order:**
1. `configure_structlog`
2. `engine, sessionmaker = create_engine_and_sessionmaker(settings)`
3. `await wait_for_postgres(engine)`
4. `http_client = httpx.AsyncClient(base_url=..., timeout=Timeout(5.0))`
5. `app.state.{settings, engine, sessionmaker, line_provider_http_client, event_lookup}` pins
6. `yield`

**D-20: Shutdown order (reverse):**
1. `await http_client.aclose()`
2. `await engine.dispose()`

**D-21: `BetMakerSettings` adds two fields** (env_prefix `BET_MAKER_` preserved):
- `line_provider_http_attempts: int = Field(default=3, ge=1, le=10)`
- `line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)`

### Claude's Discretion

- Exact structure of `before_sleep` hook (closure vs `partial` vs decorator-factory). Log MUST include `attempt_number`, `sleep_s`, `exception_type`.
- Exact location of `LineProviderUnavailable` (recommend `facades/line_provider_client.py` per CONTEXT.md — one fewer import cycle).
- Exact signature of `make_retry_decorator` (returns `Callable` vs returns `AsyncRetrying`). Pick the most readable; any pattern from tenacity 9.x works.
- Integration-test fixture orchestration (nested `LifespanManager` vs direct `lifespan_context` usage). Both apps must live in the same event loop.
- For negative cases in `test_events_routes.py`: real LP with adjusted state (`PUT /event/{id}` -> FINISHED_WIN) vs `respx` overlay on the LP-bound client. Recommended: real LP for happy-path and 1-2 negative scenarios; `respx` for 5xx-specific tests where forcing 5xx out of a real FastAPI app is contrived.

### Deferred Ideas (OUT OF SCOPE)

- TTL cache on `GET /events` — REMOVED in D-01. README P7 (DOC-02) mentions as "next-step extension."
- `GET /events?ids=1,2,3` batch endpoint — P6 perf-extension.
- `Idempotency-Key` header on `POST /bet` — REQUIREMENTS v2 API-01.
- Circuit breaker (`aiocircuitbreaker`) — out of scope.
- 429 retry / `Retry-After` — LP not rate-limited.
- OpenAPI tags/summaries/examples for new routes — P7 (DOC-02). P4 only needs `tags=["events"]` + `response_model=list[EventRead]`.
- Smoke /health check for LP connectivity — out of scope (D-18).
- EventState parity test between line_provider and bet_maker schemas — P5 e2e.
- `respx` vs `pytest-httpx` — settled on `respx` (D-15).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BM-04 | `GET /events` proxies active events from line-provider via httpx with retry (tenacity). | (1) httpx `AsyncClient` singleton pattern (Context7 /encode/httpx); (2) tenacity `@retry(...)` decorator + `wait_exponential` + `retry_if_exception_type` (Context7 /jd/tenacity); (3) `EventRead` schema duplication pattern (existing in `src/line_provider/schemas/events.py:65`); (4) ASGITransport integration test pattern (Context7 /encode/httpx + ARCHITECTURE.md lines 991-1014). |

**Implicit requirement satisfied:** `BM-06` re-affirmation — P3 stubbed event validation with `StubEventLookup`; P4 replaces with `HttpEventLookup` (same Protocol). No new requirement ID — BM-06 stays "Complete (Plan 03-09)" because the Protocol contract is unchanged.

## Project Constraints (from CLAUDE.md)

| Constraint | Source | How P4 honors it |
|------------|--------|------------------|
| Python 3.10 | TZ + CLAUDE.md Tech Stack | `from __future__ import annotations`, `X \| Y` unions, `match` allowed |
| FastAPI recommended | TZ | FastAPI 0.115+ already pinned; new route uses `APIRouter` |
| Полностью асинхронное взаимодействие | TZ | httpx `AsyncClient` (async); tenacity auto-detects async fn (AsyncRetrying); no sync wrappers |
| Все компоненты докеризованы, запуск через `docker compose up` | TZ | bet-maker already in docker-compose; P4 adds no new service. `BET_MAKER_LINE_PROVIDER_BASE_URL=http://line-provider:8000` already configured. |
| PEP8 + type hints + тесты | TZ "плюсы" / CLAUDE.md "обязательные" | `mypy --strict` passes; ruff clean; respx unit tests + ASGITransport integration test |
| No emojis in docs and code | global instructions | RESEARCH.md follows this; all artefacts produced in P4 must follow |
| DB readonly (per global instructions) | global instructions | P4 does not run DDL; alembic untouched |
| Use Context7 for library lookups | global + memory hints | Done in this research |
| Verify decisions against TZ source | memory hint | Verified: TZ page 3 explicitly says "допускается небольшое отставание" — does NOT require cache. D-01 alignment confirmed. |

## Architecture Patterns

### System Architecture Diagram

```
[Client]
    |  GET /events                                  POST /bet
    |  GET /bet/{id}                                {event_id, amount}
    |  GET /bets                                    |
    v                                               v
[bet-maker FastAPI app]                       [bet-maker FastAPI app]
    |                                               |
    | entrypoints/api/events.py                     | entrypoints/api/bets.py
    |   - try: list_active_events(http_client)      |   - try: place_bet(uow, event_id, amount,
    |   - except LineProviderUnavailable: 503       |             event_lookup=HttpEventLookup)
    |                                               |   - except LineProviderUnavailable: 503
    |                                               |   - except EventNotBettable: 422
    v                                               v
[selectors/list_active_events.py]             [interactors/place_bet.py]
    |                                               |
    | @make_retry_decorator(N, max_backoff)         | (P3, unchanged)
    |   await http_client.get("/events")            |   await event_lookup.get_event(event_id)
    |   r.raise_for_status()                        |     -> HttpEventLookup
    |   return [EventRead.model_validate(x) for x   |        @make_retry_decorator(N, max_backoff)
    |           in r.json()]                        |          await http_client.get(f"/event/{id}")
    |                                               |          if 404: return None
    | 5xx after retry -> LineProviderUnavailable    |          r.raise_for_status()
    |                                               |          return EventSnapshot.model_validate(...)
    |                                               |
    +-----------> [singleton httpx.AsyncClient] <---+
                  (app.state.line_provider_http_client)
                  base_url=http://line-provider:8000
                  timeout=Timeout(5.0)
                          |
                          v
                  [line-provider FastAPI app]
                          |
                          v
                  - GET /events       -> 200 + list[EventRead]
                  - GET /event/{id}   -> 200 + EventRead / 404
```

### Recommended Project Structure (additions)

```
src/bet_maker/
├── facades/
│   ├── line_provider_client.py     # NEW: LineProviderUnavailable + make_retry_decorator + (optional) before_sleep helper
│   ├── http_event_lookup.py        # NEW: HttpEventLookup(EventLookup Protocol)
│   ├── event_lookup.py             # UNCHANGED (Protocol + EventSnapshot + StubEventLookup remain)
│   ├── uow.py                      # UNCHANGED (P3)
│   └── deps.py                     # MODIFIED: + get_line_provider_http_client + LineProviderHttpClientDep
├── selectors/
│   ├── list_active_events.py       # NEW (mirrors line_provider name, different file path)
│   ├── list_bets.py                # UNCHANGED (P3)
│   └── get_bet.py                  # UNCHANGED (P3)
├── schemas/
│   ├── events.py                   # MODIFIED: + EventRead alongside existing EventState
│   ├── bets.py                     # UNCHANGED (P3)
│   └── ...
├── entrypoints/
│   ├── api/
│   │   ├── events.py               # NEW: GET /events route
│   │   ├── bets.py                 # MODIFIED: + except LineProviderUnavailable -> 503
│   │   └── health.py               # UNCHANGED (D-18)
│   ├── lifespan.py                 # MODIFIED: + http_client create + http_event_lookup wiring + reverse-order shutdown
│   └── middleware.py               # UNCHANGED
├── settings/config.py              # MODIFIED: + 2 fields (D-21)
└── app.py                          # MODIFIED: + app.include_router(events.router)

tests/bet_maker/
├── conftest.py                     # MODIFIED: + line_provider_app fixture (LifespanManager) for D-16
├── test_http_event_lookup.py       # NEW (respx unit tests, D-15)
├── test_list_active_events.py      # NEW (respx unit tests, D-15)
├── test_events_routes.py           # NEW (ASGITransport integration test, D-16)
├── test_bet_routes.py              # MODIFIED: + TestPostBet503 class (D-17)
├── test_lifespan.py                # MODIFIED: + assert line_provider_http_client pinned + assert HttpEventLookup wired
└── ...
```

### Pattern 1: Singleton httpx.AsyncClient in FastAPI lifespan

**What:** One `httpx.AsyncClient` per service, created on startup, closed on shutdown, pinned to `app.state` for Depends-based access.

**When to use:** Always, for any outbound HTTP from a long-running async service. Per-request clients defeat connection pooling, blow out FD limits under load, and break event-loop discipline in tests.

**Example (target shape for P4 lifespan):**
```python
# Source: ARCHITECTURE.md lines 599-660 + Context7 /encode/httpx
import httpx
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = BetMakerSettings()
    configure_structlog(settings.log_level)

    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    try:
        await wait_for_postgres(engine)
    except Exception as exc:
        await engine.dispose()
        raise

    http_client = httpx.AsyncClient(
        base_url=str(settings.line_provider_base_url),
        timeout=httpx.Timeout(5.0),
    )

    event_lookup = HttpEventLookup(
        http_client=http_client,
        attempts=settings.line_provider_http_attempts,
        max_backoff=settings.line_provider_http_backoff_max_s,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.line_provider_http_client = http_client
    app.state.event_lookup = event_lookup

    try:
        yield
    finally:
        await http_client.aclose()    # D-20: BEFORE engine.dispose
        await engine.dispose()
```

[CITED: Context7 /encode/httpx + project ARCHITECTURE.md]

### Pattern 2: tenacity retry on async httpx call with structlog before_sleep

**What:** Composable retry decorator that retries on `httpx.TransportError` + `httpx.HTTPStatusError` (when status >= 500), with exponential backoff and structured log on each retry attempt.

**When to use:** Every outbound call to line-provider from either `HttpEventLookup.get_event` or `list_active_events`.

**Example:**
```python
# Source: Context7 /jd/tenacity (RetryCallState attributes verified)
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryCallState,
)
import httpx

log = structlog.get_logger()


def _is_retryable_status(exc: BaseException) -> bool:
    """5xx is retryable; 4xx propagates without retry (contract responses)."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


def _retry_predicate(exc: BaseException) -> bool:
    # httpx.TransportError covers: TimeoutException, ConnectError, ReadError, NetworkError
    return isinstance(exc, httpx.TransportError) or _is_retryable_status(exc)


def _log_before_sleep(retry_state: RetryCallState) -> None:
    """D-06: structured log on each retry attempt before sleeping."""
    sleep_s = retry_state.next_action.sleep if retry_state.next_action else 0.0
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.warning(
        "line_provider.http.retry",
        attempt_number=retry_state.attempt_number,
        sleep_s=sleep_s,
        exception_type=type(exc).__name__ if exc else None,
    )


def make_retry_decorator(attempts: int, max_backoff: float):
    """Factory used by HttpEventLookup AND list_active_events (D-11).

    Also reused in P6 BM-12 reconciler with different (attempts, max_backoff).
    """
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=max_backoff),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        # Note: retry_if_exception_type matches both; the wait/stop fires anyway,
        # but we filter via predicate is not exposed by retry_if_exception_type.
        # Better: use a custom retry callable (see _retry_predicate above) for
        # surgical 4xx-no-retry behaviour:
        # retry=lambda rs: rs.outcome.failed and _retry_predicate(rs.outcome.exception()),
        before_sleep=_log_before_sleep,
        reraise=True,
    )
```

**Important refinement on `retry=`:** `retry_if_exception_type((TransportError, HTTPStatusError))` matches **any** `HTTPStatusError` — including 4xx. To enforce D-05 (no retry on 4xx) you must use a **custom retry callable**:

```python
from tenacity import retry_if_exception

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False

# In make_retry_decorator(...):
retry=retry_if_exception(_is_retryable),
```

[VERIFIED: Context7 /jd/tenacity — `retry_if_exception(callable)` accepts an exception predicate]

### Pattern 3: respx unit tests for httpx client behavior

**What:** `respx` patches httpx at the transport layer (no real network), supports sequenced responses for retry tests, supports `base_url` markers for cleaner test fixtures.

**When to use:** Unit tests of `HttpEventLookup` and `list_active_events` — every retry/4xx/5xx/timeout scenario in D-15.

**Example (5xx-then-200 retry succeeds):**
```python
# Source: Context7 /lundberg/respx
import httpx
import pytest
import respx
from httpx import Response

from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.facades.line_provider_client import LineProviderUnavailable


@pytest.mark.asyncio
@respx.mock(base_url="http://line-provider:8000", assert_all_called=True)
async def test_get_event_5xx_then_200_retry_succeeds(respx_mock) -> None:
    """D-15 / D-05: 5xx triggers retry; subsequent 200 succeeds."""
    event_id_str = "11111111-1111-1111-1111-111111111111"
    respx_mock.get(f"/event/{event_id_str}").mock(
        side_effect=[
            Response(503),
            Response(503),
            Response(200, json={
                "event_id": event_id_str,
                "coefficient": "2.50",
                "deadline": "2026-12-01T12:00:00+00:00",
                "state": "NEW",
            }),
        ]
    )

    async with httpx.AsyncClient(base_url="http://line-provider:8000",
                                  timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=2.0)
        snapshot = await lookup.get_event(UUID(event_id_str))

    assert snapshot is not None
    assert snapshot.state == EventState.NEW
```

**Example (404 returns None, no retry):**
```python
@pytest.mark.asyncio
@respx.mock(base_url="http://line-provider:8000")
async def test_get_event_404_returns_none(respx_mock) -> None:
    """D-09: 404 from LP -> get_event returns None (NOT raise)."""
    event_id = uuid4()
    route = respx_mock.get(f"/event/{event_id}").mock(return_value=Response(404))

    async with httpx.AsyncClient(base_url="http://line-provider:8000",
                                  timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=2.0)
        result = await lookup.get_event(event_id)

    assert result is None
    assert route.call_count == 1   # NO retry on 4xx
```

**Example (5xx exhausts retries -> LineProviderUnavailable):**
```python
@pytest.mark.asyncio
@respx.mock(base_url="http://line-provider:8000")
async def test_get_event_5xx_exhausts_raises(respx_mock) -> None:
    """D-05/D-07: 5xx after 3 attempts -> LineProviderUnavailable."""
    event_id = uuid4()
    respx_mock.get(f"/event/{event_id}").mock(return_value=Response(503))

    async with httpx.AsyncClient(base_url="http://line-provider:8000",
                                  timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=2.0)
        with pytest.raises(LineProviderUnavailable):
            await lookup.get_event(event_id)
```

[VERIFIED: Context7 /lundberg/respx — `side_effect=[Response(...), ...]` is the sequencing API; `respx_mock` is the standard pytest fixture; `@pytest.mark.respx(base_url=...)` or `@respx.mock(base_url=...)` both supported]

### Pattern 4: Two FastAPI apps in one event loop via ASGITransport (D-16 integration test)

**What:** Run both `line-provider` and `bet-maker` as ASGI applications inside a single Python process, with one shared event loop. bet-maker's outbound httpx client is rewired to use an `ASGITransport(app=line_provider_app)` so it talks directly to the LP app object — no docker, no real TCP.

**When to use:** D-16 integration test `tests/bet_maker/test_events_routes.py` — exercises the full proxy path end-to-end without network.

**Critical: HTTPX does NOT manage ASGI lifespan automatically.** [CITED: Context7 /encode/httpx]

> "When using ASGITransport, HTTPX does not manage the ASGI application's lifespan events. It is recommended to use LifespanManager from the asgi-lifespan library in conjunction with AsyncClient to handle application startup and shutdown gracefully."

This means the LP app fixture MUST wrap `build_app()` in `LifespanManager` to populate `app.state.event_store` and `app.state.event_bus` before bet-maker tries to proxy through it. Same pattern as the existing `tests/line_provider/conftest.py:14-22`.

**Example (target shape):**
```python
# tests/bet_maker/test_events_routes.py
import os
from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bet_maker.facades.deps import get_line_provider_http_client


@pytest_asyncio.fixture(scope="session")
async def line_provider_app() -> AsyncIterator[FastAPI]:
    """Session-scoped line_provider FastAPI app with lifespan triggered.

    Session-scoped so the same event-loop is shared with the bet_maker `app`
    fixture (also session-scoped — see tests/bet_maker/conftest.py:36-58).
    """
    from line_provider.app import build_app  # local import: avoid eager side-effects
    application = build_app()
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture(scope="session")
async def bet_maker_client_against_real_lp(
    app: FastAPI,
    line_provider_app: FastAPI,
) -> AsyncIterator[AsyncClient]:
    """bet_maker AsyncClient whose internal LP-client is wired to the real LP app.

    Override app.state.line_provider_http_client via dependency_overrides so
    the bet_maker process talks to the in-process LP via ASGITransport.
    """
    lp_client = AsyncClient(
        transport=ASGITransport(app=line_provider_app),
        base_url="http://line-provider:8000",  # matches BetMakerSettings default
        timeout=Timeout(5.0),
    )
    # Override the provider so HttpEventLookup + list_active_events get this client
    app.dependency_overrides[get_line_provider_http_client] = lambda: lp_client

    # ALSO override app.state.event_lookup so place_bet uses HttpEventLookup
    # bound to the lp_client — required because event_lookup is read from
    # app.state, not via Depends in the interactor.
    from bet_maker.facades.http_event_lookup import HttpEventLookup
    app.state.event_lookup = HttpEventLookup(
        http_client=lp_client, attempts=3, max_backoff=2.0,
    )

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await lp_client.aclose()
        app.dependency_overrides.pop(get_line_provider_http_client, None)
```

**Test scenarios (D-16):**
1. `POST /event` to LP -> `GET /events` to bet-maker returns it.
2. `PUT /event/{id}` to LP transitioning to FINISHED_WIN -> `GET /events` to bet-maker returns empty (LP filters by state==NEW).
3. `POST /bet` to bet-maker with valid `event_id` -> 201 (full path: bet-maker -> HttpEventLookup -> LP -> back -> place_bet -> PG).
4. `POST /bet` with non-existent event_id -> 422 (LP returns 404 -> HttpEventLookup returns None -> EventNotBettable).

For 5xx-specific scenarios in this test file (if any), use `respx` to layer over the `lp_client` rather than trying to force a real FastAPI app into 5xx territory.

[CITED: Context7 /encode/httpx + project pattern at tests/line_provider/conftest.py]

### Anti-Patterns to Avoid

| Anti-pattern | Why it's bad | What to do instead |
|--------------|-------------|---------------------|
| Per-request `httpx.AsyncClient()` construction | Defeats keep-alive pooling, blows FD limit, breaks Pitfall A2 (event-loop sharing across requests) | Singleton in lifespan, pinned to `app.state.line_provider_http_client` (D-12) |
| Default `httpx.Timeout` (infinite) | Slow LP holds the route forever; request body never returns; clients keep their TCP connections open until the worker exhausts FDs | Explicit `httpx.Timeout(5.0)` (D-02) — verified vs PITFALLS.md row "Integration Gotcha: httpx.Timeout infinite default" |
| Sharing one `AsyncClient` across event loops | asyncpg-style "Future attached to different loop" errors at runtime, flaky tests under fixture-scope drift | Singleton per service; fixture scope == event-loop scope (`asyncio_default_fixture_loop_scope="session"` already pinned in pyproject.toml line 77) [CITED: PITFALLS.md row 1004] |
| Unbounded retry / retry on 4xx | LP's 422 "event not bettable" should reach the user as 422 immediately; retrying paints LP as faulty when it isn't | `stop_after_attempt(N)` + `retry_if_exception(_is_retryable)` predicate that filters out 4xx (D-05) |
| Calling `response.raise_for_status()` inside a try/except that swallows `HTTPStatusError` | tenacity never sees the 5xx; retry never fires | Let `HTTPStatusError` propagate; tenacity's `retry_if_exception(...)` predicate filters status >= 500 |
| Missing `await` on `aclose()` | Coroutine never runs; pool leaks; tests pass but `docker compose down` shows hung connections | `await http_client.aclose()` in `finally` (D-20) |
| Module-level `httpx.AsyncClient(...)` singleton | Same anti-pattern A2; binds to import-time event loop | Construct in lifespan only; access via `app.state` (D-12) |
| Importing `line_provider.schemas.events.EventRead` directly into bet_maker | Couples services; breaks service boundary; deploy of LP can break bet-maker | Duplicate `EventRead` in `bet_maker/schemas/events.py` (D-13). Symmetric with existing `EventState` duplication |
| Using a single unified `LineProviderClient` facade | Couples read-path (GET /events) and validation-path (POST /bet); each path's failure mode bleeds into the other | Two independent facades + shared exception/retry-factory (D-11) |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with exponential backoff | Manual `for attempt in range(N): try/except + asyncio.sleep(2**attempt)` | `tenacity.retry(...)` decorator | Edge cases: jitter, max-backoff cap, AsyncRetrying detection, before_sleep hooks, reraise semantics — tenacity has them all already; pinned at 9.1.4 |
| Mock HTTP responses in tests | `monkeypatch.setattr(httpx.AsyncClient, "get", ...)` or custom `MockTransport` | `respx>=0.22` | respx supports sequenced responses (`side_effect=[Response(500), Response(200)]`), `assert_all_called`, `assert_all_mocked`, `pytest.mark.respx(base_url=...)`, and patches at transport layer (no monkeypatch fragility) |
| Trigger FastAPI lifespan in tests | Manually call `await app.router.startup()` / `shutdown()` | `asgi_lifespan.LifespanManager(app)` (already in dev-deps) | HTTPX `ASGITransport` does NOT trigger lifespan; manually wiring startup/shutdown around `app.state` is error-prone. LifespanManager wraps both events. |
| HTTP status -> exception mapping | Custom `if response.status_code == 404: raise NotFound(...)` ladder | `response.raise_for_status()` -> catch `httpx.HTTPStatusError`; check `.response.status_code` for 404 special-case | One method on `Response`; well-tested across all status codes |
| Connection pool management | Configure HTTP/1.1 keep-alive, connection limits, per-host pools | `httpx.AsyncClient` default pool | httpx's default pool is sane (100 connections, 20 per-host); explicit override only with measured need |
| Two-app integration testing | Spin up `docker compose up line-provider` in the test fixture | `ASGITransport(app=line_provider_app)` + `LifespanManager` | In-process; one event loop; ms-level test runtime; no docker overhead |

**Key insight:** In Phase 4 the *only* thing we hand-roll is the **predicate** that distinguishes retryable 5xx from non-retryable 4xx inside `httpx.HTTPStatusError`. tenacity's stock `retry_if_exception_type(HTTPStatusError)` retries *all* status errors — we need the custom `retry_if_exception(_is_retryable)` predicate (4 lines of code). Everything else is library-resident.

## Runtime State Inventory

Phase 4 is greenfield wiring (no rename, no rebrand, no migration). Step 2.5 does not apply.

The single state-shape addition is `app.state.line_provider_http_client` — an in-process pointer, not persisted state. Lifespan creates it on startup, closes it on shutdown; no DB rows, no broker queues, no OS-registered tasks, no env-var rename. Section omitted intentionally.

## Common Pitfalls

### Pitfall 1: `httpx.Timeout` infinite default
**What goes wrong:** `httpx.AsyncClient()` without `timeout=...` defaults to `Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)` in 0.28.x — actually fine — BUT older docs/blog posts say "default is no timeout." Project PITFALLS.md row "Integration Gotcha: httpx.Timeout infinite default" flags this; D-02 makes the timeout explicit.
**Why it happens:** Copy-pasted Stack Overflow snippets predate httpx 0.20.
**How to avoid:** Always pass `timeout=httpx.Timeout(5.0)` explicitly. CONTEXT.md D-02 locks this.
**Warning signs:** A slow LP holding `POST /bet` for 30+ seconds before timing out; uvicorn worker count climbing during a partial LP outage.
[CITED: PITFALLS.md row 1014]

### Pitfall 2: Sharing one AsyncClient across event loops in tests
**What goes wrong:** A session-scoped client used inside a function-scoped event loop raises "Future attached to a different loop" or "Event loop is closed." Same root cause as P3 D-23 (truncate-fixture session/function scope reconciliation).
**Why it happens:** `pytest-asyncio` defaults to function-scoped event loops; an `httpx.AsyncClient` constructed in a session-scoped fixture binds to a different loop than the one running the test.
**How to avoid:** `asyncio_default_fixture_loop_scope="session"` is already set in `pyproject.toml` (line 77). When you create the `line_provider_app` fixture for D-16, mark it `scope="session"` — same as the existing `app` fixture in `tests/bet_maker/conftest.py:36`. Use `@pytest.mark.asyncio(loop_scope="session")` on all test classes that share the session-scoped client (already convention in P3 tests).
**Warning signs:** Flaky tests; "got Future <Future pending> attached to a different loop"; tests pass in isolation but fail when run together.
[CITED: PITFALLS.md row 1004; project convention at tests/bet_maker/conftest.py:36-58]

### Pitfall 3: ASGITransport doesn't trigger lifespan
**What goes wrong:** D-16 integration test sets up `httpx.AsyncClient(transport=ASGITransport(app=line_provider_app))` and calls `GET /events`; LP returns AttributeError because `app.state.event_store` was never initialised.
**Why it happens:** HTTPX's `ASGITransport` is a pure-transport adapter; it does not call ASGI `lifespan` events. Official httpx docs say: "It is recommended to use `LifespanManager` from the asgi-lifespan library in conjunction with AsyncClient."
**How to avoid:** Wrap the LP app in `asgi_lifespan.LifespanManager` before the AsyncClient connects (mirror of `tests/line_provider/conftest.py:14-22`). `asgi-lifespan>=2.1` is already in dev-deps.
**Warning signs:** `AttributeError: 'State' object has no attribute 'event_store'` from line-provider routes during D-16 test runs.
[CITED: Context7 /encode/httpx — "ASGI startup and shutdown" section]

### Pitfall 4: tenacity retry_if_exception_type(HTTPStatusError) over-retries
**What goes wrong:** Retries every 4xx — including 422 "amount > 2dp" — making validation errors look like LP outages and amplifying latency on user mistakes.
**Why it happens:** `retry_if_exception_type` matches by class, not by attribute. `HTTPStatusError` wraps both 4xx and 5xx.
**How to avoid:** Use `retry=retry_if_exception(_is_retryable)` with a custom callable that checks `exc.response.status_code >= 500` for `HTTPStatusError`. See Pattern 2 above.
**Warning signs:** Unit tests for "POST /bet with extra field returns 422 immediately" actually take 3 seconds before responding because tenacity retried.

### Pitfall 5: Calling `response.raise_for_status()` inside try/except that swallows HTTPStatusError
**What goes wrong:** Custom try/except inside the facade catches `HTTPStatusError`, returns `None`, and tenacity never sees the exception -> retry never fires on 5xx.
**Why it happens:** Conflating "404 -> None" with general status-error handling. They're different: 404 is a contract response (D-09), 5xx is an outage signal (D-07).
**How to avoid:** Inside `HttpEventLookup.get_event`, special-case `response.status_code == 404 -> return None` BEFORE calling `raise_for_status()`. Then let `raise_for_status()` raise `HTTPStatusError` (5xx) freely so the tenacity decorator on the outer call sees it.

```python
@make_retry_decorator(attempts, max_backoff)
async def _get(event_id):
    response = await http_client.get(f"/event/{event_id}")
    if response.status_code == 404:
        return None
    response.raise_for_status()    # raises on 5xx -> tenacity retries
    return EventSnapshot.model_validate(response.json())
```

### Pitfall 6: aclose() ordering vs engine.dispose()
**What goes wrong:** `engine.dispose()` runs before `http_client.aclose()`; the httpx pool tries to send a final keep-alive close-frame, but doesn't matter for HTTP — however the *reverse* mistake (closing http_client AFTER engine) is invisible but conceptually wrong.
**Why it happens:** Try/finally blocks accumulate cleanup in startup order, not reverse.
**How to avoid:** D-20 mandates explicit reverse order: `await http_client.aclose()` then `await engine.dispose()`. Verify in `test_lifespan.py` by checking close-order side effects, OR (simpler) by code review at PR time.

### Pitfall 7: place_bet interactor catches LineProviderUnavailable
**What goes wrong:** Old assumption "interactor maps all exceptions to EventNotBettable" leaks LineProviderUnavailable into 422 instead of 503.
**Why it happens:** Refactoring impulse: "the interactor already maps lookup errors to EventNotBettable, why not this one too?"
**How to avoid:** `place_bet` (src/bet_maker/interactors/place_bet.py) must NOT catch `LineProviderUnavailable`. It propagates straight through. Route layer (bets.py) catches it. CONTEXT.md D-08 says route ladder order: 1) `except LineProviderUnavailable -> 503`, 2) `except EventNotBettable -> 422`. Order matters because LineProviderUnavailable is NOT a subclass of EventNotBettable.

### Pitfall 8: respx mock leaks across tests
**What goes wrong:** `@respx.mock` decorator without `assert_all_called=True` and shared fixture state across tests can cause routes from one test to silently match requests from another.
**Why it happens:** Default respx behaviour is permissive; routes pass through if not matched.
**How to avoid:** Use `@respx.mock(assert_all_mocked=True)` (no real network calls allowed) and consider `assert_all_called=True` for tests where you want to enforce that every defined route was hit. Use the `respx_mock` pytest fixture (function-scoped) rather than module-level decorators when possible.

## Code Examples

### facades/line_provider_client.py (NEW — shape)
```python
# Source: synthesised from Context7 /jd/tenacity + project ARCHITECTURE.md
from __future__ import annotations

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger()


class LineProviderUnavailable(Exception):
    """D-07: line-provider unreachable after retry exhaustion.

    Route layer (D-08, D-10) maps to HTTP 503. Interactor place_bet
    must NOT catch this — propagates straight through to the route.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _is_retryable(exc: BaseException) -> bool:
    """D-05: retry on TransportError (timeout/connect/network) and 5xx
    HTTPStatusError. 4xx propagates without retry (contract responses).
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _log_before_sleep(retry_state: RetryCallState) -> None:
    sleep_s = retry_state.next_action.sleep if retry_state.next_action else 0.0
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.warning(
        "line_provider.http.retry",
        attempt_number=retry_state.attempt_number,
        sleep_s=sleep_s,
        exception_type=type(exc).__name__ if exc else None,
    )


def make_retry_decorator(attempts: int, max_backoff: float):
    """D-03 / D-11: shared retry-factory. Reused by HttpEventLookup,
    list_active_events, and P6 BM-12 reconciler with different params.
    """
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=max_backoff),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_log_before_sleep,
        reraise=True,
    )
```

### facades/http_event_lookup.py (NEW — shape)
```python
# Source: synthesised against EventLookup Protocol at facades/event_lookup.py:30
from __future__ import annotations

from uuid import UUID

import httpx

from bet_maker.facades.event_lookup import EventSnapshot
from bet_maker.facades.line_provider_client import (
    LineProviderUnavailable,
    make_retry_decorator,
)


class HttpEventLookup:
    """D-11 / D-14: production implementation of EventLookup Protocol.

    Replaces StubEventLookup in production lifespan. StubEventLookup is
    retained for unit tests (P3 D-23 truncate-fixture pattern).
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        attempts: int = 3,
        max_backoff: float = 2.0,
    ) -> None:
        self._http_client = http_client
        self._retry = make_retry_decorator(attempts, max_backoff)

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        """D-09: 404 -> None; 5xx after retry -> LineProviderUnavailable."""

        @self._retry
        async def _call() -> EventSnapshot | None:
            response = await self._http_client.get(f"/event/{event_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
            return EventSnapshot(
                event_id=UUID(payload["event_id"]),
                deadline=payload["deadline"],   # Pydantic parses ISO -> AwareDatetime
                state=payload["state"],
            )

        try:
            return await _call()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            raise LineProviderUnavailable(reason=str(exc)) from exc
```

### selectors/list_active_events.py (NEW — shape)
```python
from __future__ import annotations

import httpx

from bet_maker.facades.line_provider_client import (
    LineProviderUnavailable,
    make_retry_decorator,
)
from bet_maker.schemas.events import EventRead


async def list_active_events(
    http_client: httpx.AsyncClient,
    *,
    attempts: int = 3,
    max_backoff: float = 2.0,
) -> list[EventRead]:
    """D-10 / D-11: proxy GET /events from line-provider.

    Returns [] when LP returns []. Raises LineProviderUnavailable on
    5xx/timeout exhaustion. 4xx propagates.
    """
    retry_decorator = make_retry_decorator(attempts, max_backoff)

    @retry_decorator
    async def _call() -> list[EventRead]:
        response = await http_client.get("/events")
        response.raise_for_status()
        return [EventRead.model_validate(item) for item in response.json()]

    try:
        return await _call()
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LineProviderUnavailable(reason=str(exc)) from exc
```

### entrypoints/api/events.py (NEW — shape)
```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from bet_maker.facades.deps import LineProviderHttpClientDep
from bet_maker.facades.line_provider_client import LineProviderUnavailable
from bet_maker.schemas.events import EventRead
from bet_maker.selectors.list_active_events import list_active_events

router = APIRouter(tags=["events"])


@router.get("/events", response_model=list[EventRead])
async def get_events(http_client: LineProviderHttpClientDep) -> list[EventRead]:
    """BM-04: proxy active events from line-provider.

    D-10: LineProviderUnavailable -> 503 {"detail":"line-provider unreachable"}.
    Empty list -> 200 + [].
    """
    try:
        return await list_active_events(http_client)
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="line-provider unreachable",
        ) from exc
```

### entrypoints/api/bets.py modification (POST /bet — add 503 branch)
```python
# Source: current src/bet_maker/entrypoints/api/bets.py:21-45 + D-08
# Add a new except branch BEFORE the existing EventNotBettable handler.
# Order matters: LineProviderUnavailable is NOT a subclass of EventNotBettable.
async def post_bet(body, uow, event_lookup):
    try:
        return await place_bet(uow, event_id=body.event_id, amount=body.amount,
                                event_lookup=event_lookup)
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event validation unavailable: line-provider unreachable",
        ) from exc
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc
```

### schemas/events.py addition (EventRead)
```python
# Add to existing src/bet_maker/schemas/events.py (which currently only
# contains EventState) — D-13.
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    """D-13: service-boundary schema for GET /events response.

    Intentionally duplicated from line_provider/schemas/events.EventRead.
    Service-boundary isolation: bet-maker does NOT import from line_provider.
    P5 e2e test will assert value-parity (deferred).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    coefficient: Decimal
    deadline: datetime
    state: EventState
```

### facades/deps.py addition
```python
# Append to existing src/bet_maker/facades/deps.py
import httpx

def get_line_provider_http_client(request: Request) -> httpx.AsyncClient:
    """D-12: read the singleton httpx.AsyncClient — pinned by lifespan."""
    return cast(httpx.AsyncClient, request.app.state.line_provider_http_client)


LineProviderHttpClientDep = Annotated[httpx.AsyncClient, Depends(get_line_provider_http_client)]
```

### settings/config.py additions (D-21)
```python
# Append to BetMakerSettings (already has env_prefix="BET_MAKER_")
line_provider_http_attempts: int = Field(default=3, ge=1, le=10)
line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `requests` + thread executor | `httpx.AsyncClient` (native async) | httpx 0.20+ stable (2020) | Removes blocking; integrates with FastAPI's event loop |
| `pytest-httpx` / monkeypatch | `respx>=0.22` (transport-level mock) | respx 0.22 (2024-12); 0.23.1 (2026-04-08) | Cleaner sequencing API; explicit `assert_all_mocked` discipline |
| Manual `try/asyncio.sleep` retry loop | `tenacity 9.1.4` decorator + AsyncRetrying | tenacity 9.0 (2024) | Declarative; reraise=True for traceback hygiene; before_sleep for structured logs |
| `httpx.AsyncClient(app=app)` shortcut | `httpx.AsyncClient(transport=ASGITransport(app=app))` | httpx 0.28 removed `app=` shortcut | Explicit transport keeps API surface minimal |
| Manual `app.router.startup()/shutdown()` in tests | `asgi_lifespan.LifespanManager` | Stable for years | One-line wrapper, works for both startup and shutdown |

**Deprecated/outdated (do NOT use):**
- `httpx.AsyncClient(app=app)` — removed in httpx 0.28. Use `transport=ASGITransport(app=app)` instead.
- `pytest-asyncio` event_loop fixture override — replaced by `asyncio_default_fixture_loop_scope` config (already set in pyproject.toml line 77).
- tenacity `@retry(...)` without `reraise=True` — the default `RetryError` wraps the original exception and breaks traceback continuity. D-03 makes `reraise=True` mandatory.

## Assumptions Log

> The Validation Architecture, Standard Stack, and Pitfalls sections are all verified against Context7, official docs, project code, or PyPI. The following items are flagged as `[ASSUMED]` for transparency:

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `httpx.Timeout(5.0)` is sufficient for line-provider response time including the in-memory store lookup + JSON serialisation (LP is in-process for tests; networked for prod) | Pitfall 1 / D-02 | If LP under unexpected load exceeds 5s for `GET /events`, tenacity retries kick in early. Mitigation: 3 attempts with backoff already buys ~3s. If LP regularly exceeds 5s — re-evaluate per environment. |
| A2 | respx 0.22.x and 0.23.x both work with httpx 0.28.x (PyPI says `httpx>=0.25.0` — both require it but tested compatibility limit unknown) | Standard Stack / Pattern 3 | Low. respx is small and has near-zero churn between minor versions; D-15 pin `>=0.22,<0.23` is conservative. If 0.22 has a bug with httpx 0.28, planner can bump to 0.23.1 (one-line change). |
| A3 | `line-provider`'s `GET /events` response shape (UUID, Decimal-as-string, ISO-8601 datetime, state enum) is parseable by `EventRead.model_validate` via Pydantic v2's default JSON deserialisation | Pattern 3 / facades/http_event_lookup.py | Low. LP already serialises via Pydantic v2 EventRead with the same field types; symmetric duplication on bet-maker side. If a value-parity bug emerges, P5 e2e test catches it. |
| A4 | line-provider returns 200 + `[]` for empty active-events list (not 204 No Content) | D-10 / Pattern 3 | Low. Verified by inspecting `src/line_provider/entrypoints/api/events.py:82-88` — returns `list[EventRead]` via `response_model`, FastAPI default for empty list is 200 + `[]`. |

**Note:** All other claims in this research are tagged `[VERIFIED: ...]` or `[CITED: ...]`.

## Open Questions

1. **Should `make_retry_decorator` accept retry-predicate as a kwarg, or hardcode `_is_retryable`?**
   - What we know: P4 needs exactly the predicate `_is_retryable(exc)`; P6 reconciler will use the same predicate (per D-04 it shares the factory).
   - What's unclear: whether a future reconciler in P6 wants 429-aware retry or any other predicate variant.
   - Recommendation: hardcode `_is_retryable` in P4. P6 can extend the factory signature when concrete need arises. Don't over-parametrise now.

2. **Should `HttpEventLookup` and `list_active_events` share a single instance of the retry decorator, or each construct their own via the factory?**
   - What we know: Both call `make_retry_decorator(attempts, max_backoff)` with the same args (P4) or different args (P6 reconciler).
   - What's unclear: whether the factory returns a thread-safe / loop-safe decorator object that can be shared.
   - Recommendation: Each caller invokes the factory at construction time and stores the decorator. tenacity's `retry(...)` returns a callable decorator object that wraps the function on first call; sharing is fine but conceptually muddier. Construct-per-instance keeps lifetimes clear.

3. **Integration test (D-16): should the negative cases (404, past-deadline) be expressed via real LP state mutations or via respx overlay on the LP-bound client?**
   - What we know: CONTEXT.md "Claude's Discretion" leaves this open. Real LP is more authentic but harder to coordinate (creating a past-deadline event in LP requires bypassing LP's "deadline > now" validation on POST).
   - What's unclear: whether the planner prefers a hybrid (real LP for happy/state-finished cases, respx for 4xx fault injection).
   - Recommendation: Real LP for happy-path + state-finished (use `PUT /event/{id}` to transition to FINISHED_WIN; LP will then filter from `GET /events`). For "past deadline" — DO NOT use respx; just use a real event and `monkeypatch.setattr("config.time.utc_now", lambda: ...)` on the LP side, OR test that path via `tests/bet_maker/test_place_bet.py` (already covered by StubEventLookup tests in P3).

## Environment Availability

Phase 4 is code-only — no new external runtime dependencies, no databases, no migrations, no broker. The only environment change is one new dev-dependency.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10.20 | Runtime | ✓ | 3.10.20 (pinned `.python-version`) | — |
| httpx | facade + tests | ✓ | `>=0.28,<0.29` (pyproject.toml) | — |
| tenacity | facade retry | ✓ | `>=9.1,<10` (pyproject.toml) | — |
| asgi-lifespan | integration test fixture | ✓ | `>=2.1,<3` (pyproject.toml dev-deps) | — |
| respx | unit tests | ✗ | — | None — add via `uv add --group dev "respx>=0.22,<0.23"` |
| docker compose | runtime stack (existing) | (out of scope to verify in this research) | — | — |

**Missing dependencies with no fallback:** None for P4 implementation. `respx` must be added as part of Plan 04-01 (sync task) or Plan 04-02 (deps task).

**Missing dependencies with fallback:** None.

## Validation Architecture

> nyquist_validation defaults to enabled. This section is the input for VALIDATION.md generation in P4 phase-gate.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x + pytest-asyncio 1.1.x + pytest-cov 7.1.x + respx 0.22.x (NEW) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` + `[tool.coverage.run]` (lines 75-97) |
| Quick run command (per task) | `uv run pytest tests/bet_maker -q -x` |
| Full suite command (per wave merge) | `uv run pytest -q` |
| Coverage gate (phase exit) | `uv run pytest --cov=src/bet_maker --cov-fail-under=80` (P3 baseline 94.28%; P4 must not regress below ~85% — additions of 4 facades + 2 selectors + 1 route + tests should push higher, not lower) |

### Phase Requirements -> Test Map

| Req ID / Decision | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BM-04 / D-10 | `GET /events` returns 200 + list of active events from LP | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestGetEvents::test_returns_active_events -x` | ❌ Wave 0 |
| BM-04 / D-10 | `GET /events` returns 200 + `[]` when LP has no active events | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestGetEvents::test_returns_empty_list -x` | ❌ Wave 0 |
| BM-04 / D-10 | `GET /events` returns 503 when LP unreachable (5xx exhausted) | unit (respx) | `uv run pytest tests/bet_maker/test_events_routes.py::TestGetEvents::test_503_on_line_provider_unavailable -x` | ❌ Wave 0 |
| BM-04 / D-05 | `list_active_events` retries on TransportError; succeeds when LP recovers | unit (respx) | `uv run pytest tests/bet_maker/test_list_active_events.py::test_5xx_then_200_retry_succeeds -x` | ❌ Wave 0 |
| BM-04 / D-05 / D-07 | `list_active_events` exhausts on persistent 5xx -> LineProviderUnavailable | unit (respx) | `uv run pytest tests/bet_maker/test_list_active_events.py::test_5xx_exhausts_raises_unavailable -x` | ❌ Wave 0 |
| BM-04 / D-13 | `EventRead` parses LP `GET /events` payload (UUID, Decimal, datetime, state) | unit | `uv run pytest tests/bet_maker/test_schemas.py::TestEventRead -x` | ✅ (extend existing) |
| D-09 | `HttpEventLookup.get_event` returns `EventSnapshot` on 200 | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_200_returns_snapshot -x` | ❌ Wave 0 |
| D-09 | `HttpEventLookup.get_event` returns None on 404 (no retry) | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_404_returns_none -x` | ❌ Wave 0 |
| D-05 | `HttpEventLookup.get_event` propagates 422/400 from LP without retry | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_4xx_propagates_no_retry -x` | ❌ Wave 0 |
| D-07 | `HttpEventLookup.get_event` raises LineProviderUnavailable after 5xx exhaustion | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_5xx_exhausts_raises -x` | ❌ Wave 0 |
| D-05 | `HttpEventLookup.get_event` retries 5xx -> succeeds on 200 | unit (respx) | `uv run pytest tests/bet_maker/test_http_event_lookup.py::test_get_event_5xx_then_200 -x` | ❌ Wave 0 |
| D-08 | `POST /bet` returns 503 on LineProviderUnavailable; no PG write | integration | `uv run pytest tests/bet_maker/test_bet_routes.py::TestPostBet503 -x` | ✅ (extend existing) |
| D-09 | `POST /bet` returns 422 when LP returns 404 (event_id missing) | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestPostBetViaRealLp::test_404_maps_to_422 -x` | ❌ Wave 0 |
| D-12 / D-19 | `app.state.line_provider_http_client` is an httpx.AsyncClient after startup | unit | `uv run pytest tests/bet_maker/test_lifespan.py::TestLifespanStatePins::test_http_client_pinned_on_state -x` | ✅ (extend existing) |
| D-14 / D-19 | `app.state.event_lookup` is `HttpEventLookup` (not Stub) in production lifespan | unit | `uv run pytest tests/bet_maker/test_lifespan.py::TestLifespanStatePins::test_event_lookup_is_http_in_production -x` | ✅ (extend existing — currently asserts StubEventLookup; must be updated to HttpEventLookup after lifespan change) |
| D-20 | `http_client.aclose()` called before `engine.dispose()` on shutdown | unit | `uv run pytest tests/bet_maker/test_lifespan.py::TestShutdownOrder::test_aclose_before_dispose -x` | ❌ Wave 0 |
| D-21 | `BetMakerSettings.line_provider_http_attempts` reads `BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS` env | unit | `uv run pytest tests/bet_maker/test_settings.py::test_line_provider_http_attempts_default_and_env -x` | ❌ Wave 0 (or extend existing config test) |
| D-21 | `BetMakerSettings.line_provider_http_backoff_max_s` reads env | unit | `uv run pytest tests/bet_maker/test_settings.py::test_backoff_max_s_default_and_env -x` | ❌ Wave 0 |
| D-01 (sync) | `REQUIREMENTS.md` BM-04 no longer mentions TTL cache | manual diff review | grep-based (`! grep -i "TTL cache" REQUIREMENTS.md ROADMAP.md`) | manual / pre-commit hook (or check in Plan 04-01) |
| D-16 | Integration test exercises `POST /event(LP) -> GET /events(BM)` round-trip in one event loop | integration | `uv run pytest tests/bet_maker/test_events_routes.py::TestIntegration -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit (TDD cycle):** `uv run pytest tests/bet_maker -q -x` (~30s on testcontainers PG)
- **Per wave merge:** `uv run pytest -q` (full project; tests both services + e2e; ~60s)
- **Phase gate (Plan 04-N final):** `uv run pytest -q && uv run pytest --cov=src/bet_maker --cov-fail-under=80 && uv run mypy src && uv run ruff check && uv run ruff format --check` — full quality bar; coverage must not regress below 80% (target ~95% to match P3 baseline).

### Wave 0 Gaps

- [ ] `tests/bet_maker/test_http_event_lookup.py` — new file; covers BM-04, D-05, D-07, D-09 (HttpEventLookup unit tests via respx)
- [ ] `tests/bet_maker/test_list_active_events.py` — new file; covers BM-04, D-05, D-07, D-10 (selector unit tests via respx)
- [ ] `tests/bet_maker/test_events_routes.py` — new file; covers BM-04, D-10, D-16 (integration via ASGITransport + LifespanManager)
- [ ] `tests/bet_maker/test_bet_routes.py::TestPostBet503` — new class added to existing file; covers D-08, D-17
- [ ] Settings tests for D-21 — new (or extend an existing config-test file if one exists; if none, add `tests/bet_maker/test_settings.py`)
- [ ] Extension of `tests/bet_maker/test_lifespan.py` — update `test_event_lookup_pinned_on_state` to assert `HttpEventLookup` not `StubEventLookup` (currently at line 36-38); add `test_http_client_pinned_on_state` + `TestShutdownOrder` class
- [ ] Framework install: `uv add --group dev "respx>=0.22,<0.23"` + `uv sync --frozen`
- [ ] Conftest extension: `line_provider_app` session-scoped fixture in `tests/bet_maker/conftest.py` (mirror of existing `app` fixture, wrapped in `LifespanManager`)

## Security Domain

> `security_enforcement` config key absent — treating as enabled per default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | TZ explicitly excludes auth (REQUIREMENTS.md "Out of Scope") |
| V3 Session Management | no | Stateless HTTP between services; no user sessions |
| V4 Access Control | no | TZ excludes user accounts |
| V5 Input Validation | yes | Pydantic v2 `extra="forbid"` + `frozen=True` on `EventRead`; UUID type-coercion in `HttpEventLookup._call`; `EventRead.model_validate` rejects unknown fields from LP. CLAUDE.md Tech Stack mandates Pydantic 2.13+ with `pydantic.mypy` plugin. |
| V6 Cryptography | no | No new crypto material in P4. No secrets in the new code path. |
| V14 Configuration | yes | New env vars (`BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS`, `..._BACKOFF_MAX_S`) follow existing pydantic-settings discipline; defaults are safe; no secrets. `BET_MAKER_LINE_PROVIDER_BASE_URL` already exists (P1). |

### Known Threat Patterns for Async Python HTTP Integration

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Slowloris-style upstream hang (LP holds the connection open forever) | Denial of Service | Explicit `httpx.Timeout(5.0)` (D-02); upstream cannot exhaust bet-maker workers indefinitely |
| Resource exhaustion via unbounded retry | Denial of Service | `stop_after_attempt(N)` cap (D-03); reconciler-level retry cap separate (D-04, P6) |
| SSRF via attacker-controlled `event_id` injected into URL path | Tampering | `event_id: UUID` is type-coerced by Pydantic at the HTTP route boundary (BetCreate / path param); UUID format prevents arbitrary URL path injection |
| Response body too large (LP returns 100MB of events) | Denial of Service | httpx does not impose a default limit; out of scope for P4 (test task scale). If concerning, add `Content-Length` check or use `client.stream()` — deferred. |
| JSON deserialisation bomb / unexpected field | Tampering | `EventRead` has `extra="forbid"` (D-13); Pydantic v2 rejects unknown fields. Mirrors `EventState` parity discipline. |
| Schema drift across service deploys (LP adds a field; bet-maker rejects) | Availability (self-inflicted) | Intentional in dev/CI — fail loud rather than silently drop fields. In production, schema-versioned messages (P5 BM-09 `schema_version`) handle this for AMQP; HTTP-side schema-versioning deferred to P7 polish if needed. |
| Information disclosure via error detail (503 detail leaks internal hostnames) | Information Disclosure | Route detail strings are static: `"line-provider unreachable"`, `"event validation unavailable: line-provider unreachable"`. No DSN, no internal IPs, no traceback exposed to client. |

## Sources

### Primary (HIGH confidence)

- **Context7 `/encode/httpx`** — `AsyncClient`, `ASGITransport`, `httpx.Timeout`, `httpx.TransportError`, `httpx.HTTPStatusError`, `raise_for_status()`, "ASGI startup and shutdown" section confirming HTTPX does not manage lifespan
- **Context7 `/jd/tenacity`** — `retry`, `stop_after_attempt`, `wait_exponential`, `retry_if_exception`, `retry_if_exception_type`, `before_sleep` hook signature, `RetryCallState.attempt_number / outcome / next_action.sleep`, `reraise=True`, AsyncRetrying auto-detection
- **Context7 `/lundberg/respx`** — `respx.mock` decorator, `respx_mock` fixture, `@pytest.mark.respx(base_url=...)`, `route.mock(side_effect=[Response(...), ...])` sequencing, `assert_all_mocked`/`assert_all_called`, `ASGIHandler` side-effect pattern
- **PyPI** — version + dependency check for respx (0.22.0 / 0.23.1 both require `httpx>=0.25.0`)
- **TZ source** `./Тестовое задание Middle Python developer.pdf` pages 1-4 — verified verbatim: page 3 "допускается небольшое отставание в «свежести» списка" (allows lag, does NOT require cache); page 2 lists HTTP API requests as one valid integration option

### Secondary (HIGH confidence — project sources)

- `./CLAUDE.md` "Technology Stack" + "Stack Patterns by Variant" — httpx 0.28.1, tenacity 9.1.4, pydantic-settings 2.14.1, asgi-lifespan, "Use httpx.AsyncClient as a singleton (created in lifespan, injected via Depends)", "Wrap calls in tenacity.retry with wait_exponential + stop_after_attempt(5)", "Never share an AsyncClient instance across event loops"
- `.planning/research/ARCHITECTURE.md` lines 571-668 ("FastAPI + FastStream lifespan composition"), 816-828 (Phase 4 buildlist), 991-1014 (Inter-service ASGITransport integration test pattern), 1086 (Wire-protocol table entry for line-provider client)
- `.planning/research/PITFALLS.md` line 1004 (cross-event-loop httpx sharing), line 1014 (httpx.Timeout infinite default), line 1031 (stuck-bet defence-in-depth requires reliable HTTP path), line 215 (reconciliation task exception handling outside tenacity)
- `src/bet_maker/facades/event_lookup.py:30-38` — EventLookup Protocol contract (frozen since P3)
- `src/bet_maker/entrypoints/lifespan.py` — current shape to extend (D-19/D-20)
- `src/bet_maker/entrypoints/api/bets.py:34-45` — exception ladder pattern to extend (D-08)
- `src/line_provider/schemas/events.py:65-71` — `EventRead` shape to duplicate (D-13)
- `src/line_provider/entrypoints/api/events.py:71-88` — confirmed LP returns `list[EventRead]` (200 + `[]` on empty)
- `tests/line_provider/conftest.py:13-30` — `LifespanManager` + `ASGITransport` fixture pattern to mirror
- `tests/bet_maker/conftest.py:36-69` — session-scoped fixture pattern + `app.dependency_overrides` discipline
- `pyproject.toml:75-80` — `asyncio_default_fixture_loop_scope="session"` already set (Pitfall 2 mitigation)
- `.planning/phases/04-bet-maker-http-integration-with-line-provider/04-CONTEXT.md` — all D-01..D-21 locked decisions

### Tertiary (LOW confidence — none)

(No claims in this research rely on unverified WebSearch results. All findings are either Context7-verified, PyPI-verified, or grounded in inspected project code.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library version verified vs PyPI on 2026-05-15; httpx + tenacity + asgi-lifespan already in `pyproject.toml`, only `respx` is new and the CONTEXT-mandated pin matches a real published version
- Architecture: HIGH — patterns lifted from inspected project code (P1/P2/P3 lifespan, conftest, route layers); ASGITransport/LifespanManager pattern proven in P2 integration tests
- Pitfalls: HIGH — all flagged pitfalls cross-referenced against `PITFALLS.md` (project-internal) and Context7 official docs (httpx ASGI lifespan caveat, tenacity `retry_if_exception_type` over-retry trap)
- Validation Architecture: HIGH — test framework + commands already exercised in P3 (`uv run pytest -q && uv run pytest --cov`); P4 only adds new test files following the same shape

**Research date:** 2026-05-15
**Valid until:** 2026-06-15 (30 days — stack is stable; only respx has had a minor release in the last 60 days)

---

*Phase: 04-bet-maker-http-integration-with-line-provider*
*Research completed: 2026-05-15*
