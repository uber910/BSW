---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 09
subsystem: api

tags: [fastapi, httpx, tenacity, error-handling, http-status, 503, exception-ladder]

requires:
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: "LineProviderUnavailable exception (Plan 04-04 facades/line_provider_client.py)"
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: "HttpEventLookup wired into app.state.event_lookup at lifespan (Plan 04-07)"
provides:
  - "POST /bet now translates LineProviderUnavailable into HTTPException(503, 'event validation unavailable: line-provider unreachable')"
  - "Exception ladder ordering: 503 (LineProviderUnavailable) caught BEFORE 422 (EventNotBettable)"
  - "TestPostBet503 with 2 tests proving the 503 path + ladder ordering + no PG write"
affects: [05-rabbitmq-integration, 06-reconciliation-job]

tech-stack:
  added: []
  patterns:
    - "Exception ladder: more-specific upstream-failure exceptions caught before domain-validation exceptions"
    - "Test pattern: app.dependency_overrides[get_event_lookup] with try/finally cleanup pinning a fake EventLookup that raises"
    - "Static 503 detail string — no event_id, no internal exception text, no DSN leak"
    - "Before/after GET /bets count assertion proves zero PG write on validation-failure path"

key-files:
  created: []
  modified:
    - "src/bet_maker/entrypoints/api/bets.py — new `except LineProviderUnavailable -> 503` clause inserted before `except EventNotBettable -> 422`; LineProviderUnavailable import added; docstring updated with D-08 reference"
    - "tests/bet_maker/test_bet_routes.py — TestPostBet503 class added with 2 tests (test_post_bet_503_when_line_provider_unavailable / test_post_bet_503_ladder_precedes_422); module-top imports for FastAPI, EventSnapshot, LineProviderUnavailable added"

key-decisions:
  - "D-08 ladder order MUST be LineProviderUnavailable first, EventNotBettable second — sibling exceptions but explicit reading clarity prevails over arbitrary alphabetical ordering"
  - "Static detail string 'event validation unavailable: line-provider unreachable' — no variable substitution, no reason leak (T-04-09-Info-disclosure mitigation)"
  - "`from exc` preserved on the 503 raise — internal LineProviderUnavailable.reason is available on the exception chain for logs but never in the response body"

patterns-established:
  - "Pattern: D-17 503-test via dependency_overrides[get_event_lookup]+_RaisingLookup — independent of LP infrastructure (unit-style, no respx/ASGITransport needed)"
  - "Pattern: try/finally around dependency_overrides[get_event_lookup] = fake; app.dependency_overrides.pop(get_event_lookup, None) — ensures cleanup even on test failure, prevents leakage to other tests in session-scoped app"
  - "Pattern: PG-no-write assertion via GET /bets count before/after — proves place_bet validation runs BEFORE async with uow (Pitfall 3 / T-04-09-PartialWrite mitigation)"

requirements-completed: [BM-04]

duration: ~5min
completed: 2026-05-17
---

# Phase 04 Plan 09: POST /bet 503 path (LineProviderUnavailable → 503) Summary

**POST /bet now returns HTTP 503 with a static detail string when LineProviderUnavailable propagates from the place_bet interactor, with the exception ladder ordered so 503 is caught before 422 and no PG write occurs.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-17T14:05:00.000Z
- **Completed:** 2026-05-17T14:10:00.000Z
- **Tasks:** 2
- **Files modified:** 2 (1 src + 1 test)

## Accomplishments

- POST /bet maps LineProviderUnavailable to HTTPException(503, "event validation unavailable: line-provider unreachable") via a new except clause that sits ABOVE the existing EventNotBettable -> 422 clause (D-08 ladder order).
- The new clause uses `from exc` to preserve the exception chain — internal `LineProviderUnavailable.reason` stays available for log inspection but never surfaces in the response body.
- TestPostBet503 contributes 2 tests that (a) verify the 503 path with the exact static detail string, and (b) prove the ladder order by injecting a _RaisingLookup that would normally have surfaced as 422 if EventNotBettable were caught first.
- An explicit GET /bets count-before / count-after assertion proves that no bet row is written on the 503 path — the place_bet interactor short-circuits validation BEFORE entering `async with uow:`, so PG is never touched (T-04-09-PartialWrite / Pitfall 3 mitigation).
- BM-04 fully closed: POST /bet validation now uses the real HttpEventLookup (Plan 04-07) and the LP-down path produces 503 (success criterion #5 of Phase 4).

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend src/bet_maker/entrypoints/api/bets.py — 503 path** — `4d6d73e` (feat)
2. **Task 2: Add TestPostBet503 class to tests/bet_maker/test_bet_routes.py** — `9869ae7` (test)

**Plan metadata commit:** pending (final docs commit attached after this SUMMARY.md is written)

## Files Created/Modified

- `src/bet_maker/entrypoints/api/bets.py` — +12 lines: import LineProviderUnavailable; new `except LineProviderUnavailable as exc:` clause before `except EventNotBettable`; docstring extended with D-08 + Pitfall 7 references.
- `tests/bet_maker/test_bet_routes.py` — +85 lines: module-top imports (FastAPI, EventSnapshot, LineProviderUnavailable); TestPostBet503 class with 2 tests inserted between TestPostBetEventNotBettable and TestGetBets.

## Decisions Made

- None — plan executed exactly as specified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - ruff PLW0108] Lambda may be unnecessary on dependency_overrides assignment**
- **Found during:** Task 2 (TestPostBet503 ruff check)
- **Issue:** `app.dependency_overrides[get_event_lookup] = lambda: _RaisingLookup()` flagged by PLW0108 (lambda could be inlined as the class directly).
- **Fix:** Added `# noqa: PLW0108` on both lambda lines. The plan VERBATIM specifies `lambda: _RaisingLookup()` as the override pattern — preserving the lambda also keeps the acceptance criterion `grep -c "dependency_overrides\[get_event_lookup\]" tests/bet_maker/test_bet_routes.py` returning 2.
- **Files modified:** `tests/bet_maker/test_bet_routes.py`
- **Verification:** `uv run ruff check tests/bet_maker/test_bet_routes.py` exits 0; tests pass.
- **Committed in:** `9869ae7` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — pre-existing lint shape preserved with `# noqa`).
**Impact on plan:** No semantic change; lambda-as-factory pattern is the documented FastAPI dependency_overrides idiom and the acceptance grep requires the exact `dependency_overrides[get_event_lookup]` substring.

## Issues Encountered

- None — both tasks landed first-try after the noqa adjustment.

## Verification Evidence

- `grep -c "from bet_maker.facades.line_provider_client import LineProviderUnavailable" src/bet_maker/entrypoints/api/bets.py` → 1.
- `grep -c "except LineProviderUnavailable as exc:" src/bet_maker/entrypoints/api/bets.py` → 1.
- `grep -c "HTTP_503_SERVICE_UNAVAILABLE" src/bet_maker/entrypoints/api/bets.py` → 1.
- `grep -c '"event validation unavailable: line-provider unreachable"' src/bet_maker/entrypoints/api/bets.py` → 1.
- `grep -c "except EventNotBettable as exc:" src/bet_maker/entrypoints/api/bets.py` → 1 (preserved).
- Source-line ladder order check: `LineProviderUnavailable` at line 48 < `EventNotBettable` at line 53 → D-08 ordering proven.
- `grep -c "@router.get(" src/bet_maker/entrypoints/api/bets.py` → 2 (GET /bets and GET /bet/{id} unchanged).
- `grep -c "^class TestPostBet503:" tests/bet_maker/test_bet_routes.py` → 1.
- `grep -c "async def test_post_bet_503_when_line_provider_unavailable" tests/bet_maker/test_bet_routes.py` → 1.
- `grep -c "async def test_post_bet_503_ladder_precedes_422" tests/bet_maker/test_bet_routes.py` → 1.
- `grep -c "LineProviderUnavailable" tests/bet_maker/test_bet_routes.py` → 8 (≥ 2 required).
- `grep -c "dependency_overrides\[get_event_lookup\]" tests/bet_maker/test_bet_routes.py` → 2.
- `uv run pytest tests/bet_maker/test_bet_routes.py::TestPostBet503 -q -x` → 2 passed.
- `uv run pytest tests/bet_maker -q -x` → 149 passed (+2 from Plan 04-08's 147).
- `uv run pytest -q` → 244 passed (+2 from Plan 04-08's 242).
- `uv run mypy src` → clean (71 source files).
- `uv run ruff check` → clean.

## Threat Coverage (STRIDE register from PLAN)

- T-04-09-Info-disclosure (Information Disclosure): mitigated — static detail string only; internal `LineProviderUnavailable.reason` preserved on exception chain for logs but never surfaced to the client.
- T-04-09-PartialWrite (Tampering — PG transaction integrity): mitigated (HIGH) — `test_post_bet_503_when_line_provider_unavailable` asserts `count_before == count_after` via GET /bets; place_bet's three-branch validation runs BEFORE `async with uow:` so the UoW never opens on the LP-down path.
- T-04-09-LadderMisorder (Spoofing — exception order regression): mitigated — `test_post_bet_503_ladder_precedes_422` plus source-line acceptance check (`lp_line < enb_line`).
- T-04-09-DoS-pgflood (Denial of Service — upstream LP outage causing PG overload): mitigated — same Pitfall-3 ordering argument as PartialWrite; no PG round-trip on LP-down.

## Next Phase Readiness

- BM-04 fully complete: POST /bet validation goes through the real HttpEventLookup (Plan 04-07 lifespan) and LP-down condition produces a clear, fast 503 instead of timeout/500.
- Phase 4 plan progress: 9/9 plans complete. Phase ready for closure (`/gsd-complete-phase 4` or manual phase-gate review).
- No downstream phase blocks on this work — Phase 5 (RabbitMQ integration) and Phase 6 (Reconciliation job) reuse the singleton httpx.AsyncClient and `LineProviderUnavailable` exception, both available since Plans 04-04/04-07.

---
*Phase: 04-bet-maker-http-integration-with-line-provider*
*Completed: 2026-05-17*
