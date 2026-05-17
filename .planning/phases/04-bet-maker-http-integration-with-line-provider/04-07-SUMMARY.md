---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 07
subsystem: infra
tags: [httpx, asgi-lifespan, dependency-injection, lifespan, shutdown-order]

requires:
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: HttpEventLookup (04-05), BetMakerSettings line_provider_http_* fields (04-03), make_retry_decorator + LineProviderUnavailable (04-04)
provides:
  - Singleton httpx.AsyncClient with explicit Timeout(5.0) pinned on app.state.line_provider_http_client (D-12 / D-02)
  - HttpEventLookup wired into production lifespan replacing StubEventLookup (D-14 / D-21)
  - Reverse-order shutdown — http_client.aclose() BEFORE engine.dispose() with nested try/finally (D-20)
  - get_line_provider_http_client provider + LineProviderHttpClientDep alias for Plan 04-08 routes (D-12)
  - Reworked _clear_event_lookup autouse fixture (PATTERNS.md critical finding line 801)
  - Session-scoped line_provider_app fixture for Plan 04-08 ASGI proxy integration tests (D-16)
affects: [04-08, 04-09]

tech-stack:
  added: []
  patterns:
    - "DI pattern A2: long-lived clients pinned to app.state + cast() in provider — no module-level singletons"
    - "Lifespan reverse-order shutdown via nested try/finally — guarantees dispose even if aclose raises"
    - "Autouse fixture swap-pattern: per-test isolation by replacing the protocol implementation, not by mutating its internals"

key-files:
  created: []
  modified:
    - src/bet_maker/facades/deps.py (+15 lines: httpx import, get_line_provider_http_client provider, LineProviderHttpClientDep alias)
    - src/bet_maker/entrypoints/lifespan.py (+20 lines: httpx + HttpEventLookup imports, http_client construction, state pins, nested try/finally shutdown)
    - tests/bet_maker/conftest.py (+27 lines: _clear_event_lookup rewritten to StubEventLookup swap, line_provider_app session-scoped fixture)
    - tests/bet_maker/test_lifespan.py (full rewrite: 4 classes — TestLifespanStatePins, TestProductionLifespanWiring, TestShutdownOrder, TestLifespanRetryExhaustion)

key-decisions:
  - "Singleton httpx.AsyncClient created in lifespan after wait_for_postgres; injected into HttpEventLookup at construction time (D-12 + D-19)"
  - "Explicit httpx.Timeout(5.0) on construction — D-02 Pitfall 1 mitigation (no slowloris-style upstream hang stalling workers)"
  - "Reverse-order shutdown with nested try/finally — engine.dispose runs even if http_client.aclose raises (D-20 Pitfall 6)"
  - "Test isolation strategy switched from StubEventLookup._events.clear() to per-test StubEventLookup() swap — works regardless of which Protocol implementation production wires"
  - "AsyncEngine.dispose patched at class level (not instance) because the descriptor is read-only on AsyncEngine instances"

patterns-established:
  - "App.state pinning + provider cast(): DI hook for every long-lived runtime object goes through request.app.state.<name> + typed cast in a get_<name> provider; aliases via Annotated[T, Depends(get_<name>)]"
  - "Lifespan double try/finally: outer wrap waits for yield, inner ensures dispose-after-aclose ordering even on partial failure"
  - "Per-test Protocol-implementation swap: autouse fixture replaces production EventLookup with a deterministic Stub before each test body executes — production-shape assertions go in a separate class that builds a fresh app inside the test"

requirements-completed: [BM-04]

duration: 6min
completed: 2026-05-17
---

# Phase 04 Plan 07: Lifecycle wiring (HttpEventLookup + singleton httpx client + reverse-order shutdown)

**Production lifespan now owns the singleton httpx.AsyncClient and wires HttpEventLookup as the EventLookup implementation, replacing StubEventLookup — bet_maker is one route-wiring step away from end-to-end LP integration.**

## Performance

- **Duration:** ~6 min
- **Tasks:** 4 (all TDD-ordered)
- **Files modified:** 4
- **Test count delta:** 141 bet_maker passed (+2 from Plan 04-06's 139); 236 total across both services

## Accomplishments

- Production lifespan creates a singleton `httpx.AsyncClient(base_url=settings.line_provider_base_url, timeout=httpx.Timeout(5.0))` after `wait_for_postgres` succeeds (D-02 + D-19 ordering)
- `app.state.line_provider_http_client` and `app.state.event_lookup = HttpEventLookup(...)` pinned together; HttpEventLookup receives `attempts` + `max_backoff` from BetMakerSettings (D-14 + D-21)
- Shutdown reversed with nested `try/finally`: `http_client.aclose()` runs first, `engine.dispose()` runs in the inner finally — guarantees the DB pool releases even when aclose raises (D-20 + Pitfall 6)
- `get_line_provider_http_client` + `LineProviderHttpClientDep` exported from `facades/deps.py` — the canonical DI hook Plan 04-08 will use for the GET /events route
- `_clear_event_lookup` autouse fixture rewritten — no longer relies on `_events.clear()` (absent on HttpEventLookup); now swaps in a fresh `StubEventLookup()` per test (PATTERNS.md critical finding line 801 resolved)
- New session-scoped `line_provider_app` fixture builds the line_provider FastAPI app under LifespanManager — same session-scope as bet_maker `app` for shared event loop in ASGI proxy tests (Plan 04-08 D-16)

## Task Commits

1. **Task 1: facades/deps.py** — `74cd8a1` (feat: get_line_provider_http_client provider + LineProviderHttpClientDep alias)
2. **Task 2: entrypoints/lifespan.py** — `aedf924` (feat: wire HttpEventLookup + singleton httpx client + reverse-order shutdown)
3. **Task 3: tests/bet_maker/conftest.py** — `a512e98` (test: rework _clear_event_lookup to swap StubEventLookup + add line_provider_app fixture)
4. **Task 4: tests/bet_maker/test_lifespan.py** — `8fae653` (test: update test_lifespan for HttpEventLookup + http_client pin + shutdown order)

## Files Modified

- `src/bet_maker/facades/deps.py` — 1 new provider (`get_line_provider_http_client`) + 1 new alias (`LineProviderHttpClientDep`), `import httpx` added
- `src/bet_maker/entrypoints/lifespan.py` — `import httpx` + `HttpEventLookup` imports (StubEventLookup removed); singleton `http_client = httpx.AsyncClient(...)` block; `app.state.line_provider_http_client` pin; `app.state.event_lookup = HttpEventLookup(...)` replaces StubEventLookup; nested try/finally shutdown
- `tests/bet_maker/conftest.py` — `_clear_event_lookup` rewritten to swap `StubEventLookup()` per test; new session-scoped `line_provider_app` fixture wrapping `line_provider.app.build_app()` with LifespanManager
- `tests/bet_maker/test_lifespan.py` — full rewrite: 4 classes (TestLifespanStatePins, TestProductionLifespanWiring, TestShutdownOrder, TestLifespanRetryExhaustion); StubEventLookup-based assertion removed

## Verification

- `uv run pytest tests/bet_maker -q -x` -> 141 passed (+2 net from Plan 04-06's 139)
- `uv run pytest -q` -> 236 passed (both services)
- `uv run pytest tests/bet_maker/test_lifespan.py -q -x` -> 7 passed (TestLifespanStatePins 4 + TestProductionLifespanWiring 1 + TestShutdownOrder 1 + TestLifespanRetryExhaustion 1)
- `uv run mypy src` -> clean, 70 source files
- `uv run ruff check` -> clean
- grep audits: `httpx.Timeout(5.0)` x1 in lifespan.py; `app.state.line_provider_http_client` present in both deps.py and lifespan.py

## Pitfalls and rule-1 deviations encountered

- **`AsyncEngine.dispose` is read-only on the instance.** Initial draft of `TestShutdownOrder::test_aclose_before_dispose` tried `engine.dispose = fake_dispose` after lifespan startup; this raised `AttributeError: 'AsyncEngine' object attribute 'dispose' is read-only`. Switched to class-level `patch.object(AsyncEngine, "dispose", new=fake_dispose)` — the documented fallback hook from PATTERNS.md line 1100.
- **mypy [unused-ignore].** First attempt at the dispose-mock used `# type: ignore[method-assign]`; mypy reported it as unused once the instance-assignment path was abandoned. Comment removed entirely — the class-level patch needs no ignore.
- **Pre-commit ruff format reflowed three lines across deps.py and lifespan.py** (multi-line `LineProviderHttpClientDep` collapsed to single line; lifespan signatures). Auto-fixes folded into Task 1 / Task 2 commits — no semantic change.

## Threat model coverage

| Threat | Disposition | Evidence |
|--------|-------------|----------|
| T-04-07-DoS-timeout | mitigate (HIGH) | `httpx.Timeout(5.0)` explicit in lifespan; grep audit passes |
| T-04-07-ResourceLeak | mitigate | Nested `try/finally` — `engine.dispose()` runs even on aclose exception |
| T-04-07-OrderingViolation | mitigate (MEDIUM) | `TestShutdownOrder::test_aclose_before_dispose` asserts `call_order.index("aclose") < call_order.index("dispose")` |
| T-04-07-Config | mitigate (LOW) | Plan 04-03 bounded Field constraints propagate through settings into HttpEventLookup constructor |
| T-04-07-PluggableEventLookup | accept | Conftest autouse swap is test-only; production lifespan is the sole writer of `app.state.event_lookup` |

## Downstream impact

- Plan 04-08 GET /events route can now write `client: LineProviderHttpClientDep` in its signature and call `await list_active_events(client, attempts=..., max_backoff=...)` from Plan 04-06.
- Plan 04-09 (or whichever plan adds GET /event/{id}) will use `EventLookupDep` — `get_event_lookup` already returns the production HttpEventLookup since Task 2 swapped the lifespan pin.
- BM-04 still Pending — closes in Plan 04-08 when the route lands and surfaces the LineProviderUnavailable -> HTTP 503 path end-to-end.
