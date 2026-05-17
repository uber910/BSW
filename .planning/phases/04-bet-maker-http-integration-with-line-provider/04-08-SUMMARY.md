---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 08
subsystem: api
tags: [fastapi, httpx, asgi-transport, respx, integration-tests]

requires:
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: list_active_events selector (04-06), LineProviderHttpClientDep + lifespan singleton httpx.AsyncClient + line_provider_app fixture (04-07), HttpEventLookup (04-05), LineProviderUnavailable (04-04), EventRead schema (04-02)
provides:
  - bet-maker GET /events route (200 + list[EventRead] / 503 + static detail "line-provider unreachable")
  - events.router wired into FastAPI app (ordering health -> bets -> events)
  - D-16 integration test pattern proven end-to-end (two FastAPI apps in one event loop via ASGITransport + LifespanManager)
  - HttpEventLookup chain proven via real LP (TestPostBetViaRealLp 201 happy path + 422 on 404)
  - respx 503 overlay pattern for forcing LP failures inside two-apps fixture
affects: [05-rabbitmq-integration, 06-reconciliation, 07-finalisation]

tech-stack:
  added: []
  patterns:
    - "Route-level exception ladder: catch domain exception (LineProviderUnavailable) -> raise HTTPException(503, static detail) with `from exc`"
    - "Two FastAPI apps in one event loop via ASGITransport + session-scoped fixtures (D-16 / Pitfall A2)"
    - "Fixture-order layering: autouse stub-swap runs first, function-scoped real_lp_wiring re-swaps to HttpEventLookup AFTER, restores at teardown"

key-files:
  created:
    - src/bet_maker/entrypoints/api/events.py
    - tests/bet_maker/test_events_routes.py
  modified:
    - src/bet_maker/app.py

key-decisions:
  - "D-10 implemented exactly: 200 + list / 503 + static detail; no caching (D-01)"
  - "T-04-08-Info-disclosure mitigation: detail is the literal string 'line-provider unreachable'; internal reason kept only on exception chain via `from exc` (visible in logs, never in HTTP body)"
  - "Test bodies for LP POST /event drop the `state` field (LP EventCreate has extra='forbid'; state defaults to NEW server-side)"

patterns-established:
  - "Pattern: route reads HTTP-client via LineProviderHttpClientDep, delegates to selector, maps domain exception to HTTPException"
  - "Pattern: session-scoped lp_http_client (ASGITransport bound to line_provider_app) shared across integration tests"
  - "Pattern: function-scoped real_lp_wiring overrides both get_line_provider_http_client dep AND app.state.event_lookup, with teardown restore"
  - "Pattern: respx context-manager 503 overlay for forcing LP failures without touching the real LP fixture"

requirements-completed: [BM-04]

duration: 5min
completed: 2026-05-17
---

# Phase 04 / Plan 08: GET /events route + two-FastAPI-apps integration test

**bet-maker exposes GET /events (200 list / 503 static detail) and the full proxy chain is verified against a real line-provider app in the same event loop via ASGITransport.**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-05-17
- **Tasks:** 3
- **Files modified:** 3 (2 new, 1 modified)

## Accomplishments
- `GET /events` route at `src/bet_maker/entrypoints/api/events.py:33` -- returns `list[EventRead]` on success, `HTTPException(503, "line-provider unreachable")` on `LineProviderUnavailable` (D-10 + T-04-08-Info-disclosure mitigation).
- `src/bet_maker/app.py:5` import line extended to include `events`; `src/bet_maker/app.py:19` registers `events.router` after the bets router (ordering: health -> bets -> events).
- `tests/bet_maker/test_events_routes.py` with 6 integration tests across 3 classes -- proves the D-16 pattern (two FastAPI apps in one event loop) and the full HttpEventLookup chain.

## Task Commits

1. **Task 1: Create src/bet_maker/entrypoints/api/events.py** -- `50c00f5` (feat)
2. **Task 2: Extend src/bet_maker/app.py -- include events router** -- `160dc65` (feat)
3. **Task 3: Create tests/bet_maker/test_events_routes.py** -- `e9c8012` (test)

## Files Created/Modified
- `src/bet_maker/entrypoints/api/events.py` (NEW, 38 lines) -- single `GET /events` route + 503 mapping.
- `src/bet_maker/app.py` (modified) -- import + `app.include_router(events.router)`.
- `tests/bet_maker/test_events_routes.py` (NEW, 249 lines) -- 6 tests in TestGetEventsAgainstRealLp / TestGetEvents503 / TestPostBetViaRealLp.

## Decisions Made
- **Static detail string for 503**: per threat T-04-08-Info-disclosure, the body must NOT leak upstream error text. The route raises `HTTPException(503, detail="line-provider unreachable")` and uses `from exc` so the internal `LineProviderUnavailable.reason` (which contains httpx error text) is preserved on the exception chain for log inspection only.
- **No caching**: per D-01, P4 does not implement TTL caching; every `/events` request hits LP.
- **Test-body schema correction**: LP `EventCreate` is `extra="forbid"` and has no `state` field (state defaults to NEW). The plan's verbatim POST bodies included `"state": "NEW"` which would 422. Dropped that field from the 3 LP-POST test bodies. Documented in the Task 3 commit message.
- **Session-scoped LP fixture trade-off**: LP's in-memory store carries state across session-scoped tests. `test_returns_empty_list_when_lp_empty` therefore only asserts `isinstance(response.json(), list)` rather than strict emptiness (acknowledged in plan).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Blocking] Test bodies dropped the `state` field for LP POST /event**
- **Found during:** Task 3 (writing integration tests)
- **Issue:** Plan's verbatim test bodies posted `{"event_id": ..., "coefficient": ..., "deadline": ..., "state": "NEW"}` but LP `EventCreate` has `extra="forbid"` and no `state` field -- the POST would have returned 422 and the integration tests would have failed at fixture-setup time.
- **Fix:** Removed `"state": "NEW"` from the 3 `lp_client.post("/event", json=...)` bodies; LP defaults state to NEW server-side anyway.
- **Files modified:** `tests/bet_maker/test_events_routes.py`
- **Verification:** All 6 tests pass; LP POST returns 201 as expected.
- **Committed in:** `e9c8012` (Task 3 commit).

**2. [Rule 2 - Formatting] Shortened two long docstrings to fit line-length=100**
- **Found during:** Task 3 (ruff check)
- **Issue:** Two docstring lines exceeded the project's `line-length=100` ruff rule (E501) because they contained arrows.
- **Fix:** Rewrote the docstrings as ASCII `->` chains; semantic content preserved.
- **Files modified:** `tests/bet_maker/test_events_routes.py`
- **Verification:** `uv run ruff check` clean.
- **Committed in:** `e9c8012` (Task 3 commit).

---

**Total deviations:** 2 auto-fixed (1 blocking schema-mismatch, 1 formatting)
**Impact on plan:** Both fixes preserve plan intent. The schema fix is mandatory; the formatting fix is cosmetic. No scope creep.

## Issues Encountered
None beyond the two auto-fixed deviations above. Fixture order (autouse `_clear_event_lookup` -> function-scoped `real_lp_wiring`) worked as predicted -- `TestPostBetViaRealLp::test_happy_path_through_real_lp` succeeds with a real LP-resolved `event_id`, which is the empirical proof that `real_lp_wiring` runs AFTER the autouse stub-swap.

## Test Results
- `uv run pytest tests/bet_maker/test_events_routes.py -q -x` -- 6/6 passed in 3.39s.
- `uv run pytest tests/bet_maker -q -x` -- 147 passed (+6 new) in 9.83s.
- `uv run pytest -q` -- 242 passed in 10.13s.
- `uv run mypy src` -- clean, 71 source files.
- `uv run ruff check` -- clean.

## Next Phase Readiness
- BM-04 functional coverage now complete (route + integration test).
- Plan 04-09 remaining (final plan of Phase 4): POST /bet 503 path -- `LineProviderUnavailable` from `HttpEventLookup` -> HTTPException(503) on the POST route + `TestPostBet503`.

---
*Phase: 04-bet-maker-http-integration-with-line-provider*
*Completed: 2026-05-17*
