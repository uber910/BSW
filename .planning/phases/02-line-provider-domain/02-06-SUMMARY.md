---
phase: 02-line-provider-domain
plan: 06
subsystem: line-provider/selectors
tags: [line-provider, selectors, pure-read, list-active, time-filter, wave-3]

requires:
  - phase: 02-line-provider-domain
    plan: 02
    provides: line_provider.schemas.events.Event (frozen), EventState enum
  - phase: 02-line-provider-domain
    plan: 04
    provides: InMemoryEventStore.get_by_id / list_all (lock-free reads), snapshot semantics
provides:
  - src/line_provider/selectors/__init__.py — empty package marker
  - src/line_provider/selectors/get_event_by_id.py — async get_event_by_id(store, *, event_id) -> Event | None (pure delegate)
  - src/line_provider/selectors/list_active_events.py — async list_active_events(store) -> list[Event] (state==NEW AND deadline > utc_now())
  - tests/line_provider/test_selectors.py — 8 unit tests covering LP-04 happy/miss + LP-05 state/deadline/boundary/combined/empty + W-2 smoke
affects:
  - 02-07-routes (consumes get_event_by_id for GET /event/{id} route, list_active_events for GET /events route)

tech-stack:
  added: []
  patterns:
    - "Module-level utc_now import (`from config.time import utc_now`) enables monkey-patch friendly time injection in tests via `monkeypatch.setattr('line_provider.selectors.list_active_events.utc_now', lambda: ...)` — no DI noise in production API, no freezegun needed (Open Question 4 closed)."
    - "Pure-function selectors layer: no mutation, no event_bus, no I/O. Selectors only invoke read-only store methods (get_by_id, list_all) — Plan 02-04 lock-free read contract preserved end-to-end."
    - "Snapshot consistency: `now = utc_now()` captured once at top of list_active_events so all events are filtered against the same instant (no time-walk across the comprehension)."
    - "Strict `>` deadline comparison (not `>=`) — event exactly on the boundary is NOT active; test `test_list_active_events_excludes_deadline_equal_to_now` fixes this contract for Plan 02-07 routes."

key-files:
  created:
    - src/line_provider/selectors/__init__.py
    - src/line_provider/selectors/get_event_by_id.py
    - src/line_provider/selectors/list_active_events.py
    - tests/line_provider/test_selectors.py
  modified: []

key-decisions:
  - "Module-level `from config.time import utc_now` (Open Question 4 from 02-RESEARCH.md) — chosen over DI-parameter `now: datetime | None = None`. Tests monkey-patch `line_provider.selectors.list_active_events.utc_now` directly; production API stays clean (single positional `store` arg). No `freezegun` dependency introduced."
  - "Two separate selector modules (`get_event_by_id.py`, `list_active_events.py`) rather than a single `selectors.py` — matches Plan 02 PATTERNS.md §1 file-to-analog mapping and mirrors the one-file-per-pure-function convention established by `src/config/time.py`. Future selectors land as additional files, not as edits to a shared module."
  - "`get_event_by_id` is a pure delegate — `return await store.get_by_id(event_id)` is one line. Could have inlined this in routes, but the selector indirection keeps Plan 02-07 routes thin (selector → HTTPException(404) mapping) and matches the layered convention used by `set_event_state` interactor / `create_event` interactor in Plan 02-05."
  - "TDD discipline preserved: RED (failing smoke with ModuleNotFoundError) → GREEN (selectors implementation) → test expansion to full 8-test suite. Three atomic commits; ef01829 final test commit is technically refactor-shaped (tests pass immediately against existing GREEN implementation), preserving the Plan 02-04 / 02-05 pattern."

requirements-completed: []
requirements-partial: [LP-04, LP-05]

duration: 2min17s
completed: 2026-05-15
---

# Phase 02 Plan 06: line-provider Selectors Summary

**Pure read-only selectors layer for line-provider: `get_event_by_id` (LP-04) returns Event | None for route 404-mapping, `list_active_events` (LP-05) filters store.list_all by `state == NEW AND deadline > utc_now()` with strict `>` boundary semantics. Module-level utc_now import enables deterministic, freezegun-free monkey-patching in tests. Selectors do not mutate state and never call event_bus — Plan 02-07 routes will invoke them directly inside thin GET handlers.**

## Performance

- **Duration:** ~2 min 17 s (2 tasks, autonomous, no checkpoints)
- **Started:** 2026-05-15T08:52:22Z
- **Completed:** 2026-05-15T08:54:39Z
- **Tasks:** 2 / 2
- **Files created:** 4 (2 production modules + 1 empty package marker + 1 test file)
- **Tests added:** 8 (all async, all green on first GREEN run)
- **Full suite after this plan:** 72 passed (64 baseline P1 + P2-01..05 + 8 new)

## Accomplishments

- `src/line_provider/selectors/get_event_by_id.py` exports a single async function `get_event_by_id(store, *, event_id: UUID) -> Event | None` that delegates to `store.get_by_id(event_id)`. Returning `None` (instead of raising) is the contract Plan 02-07's `GET /event/{event_id}` route handler will translate to HTTP 404 — keeps the route handler readable as a four-liner with `if event is None: raise HTTPException(404)`.
- `src/line_provider/selectors/list_active_events.py` exports a single async function `list_active_events(store) -> list[Event]`. Captures `now = utc_now()` once at the top of the function (snapshot consistency: all events are filtered against the same instant, even if the comprehension is long). Returns `[e for e in await store.list_all() if e.state == EventState.NEW and e.deadline > now]`. The strict `>` (not `>=`) ensures events exactly on the boundary are excluded — closes Plan 02 ROADMAP success criterion 3 (LP-05 timing semantics).
- `tests/line_provider/test_selectors.py` covers 8 scenarios:
  1. `test_get_event_by_id_returns_event` — LP-04 happy path
  2. `test_get_event_by_id_returns_none_when_missing` — LP-04 miss returns None (proves 404-mapping contract)
  3. `test_list_active_events_excludes_finished_states` — LP-05 state filter: FINISHED_WIN + FINISHED_LOSE excluded
  4. `test_list_active_events_excludes_past_deadline` — LP-05 deadline filter: past deadlines excluded
  5. `test_list_active_events_excludes_deadline_equal_to_now` — LP-05 boundary semantics: strict `>` ensures `deadline == now` is excluded
  6. `test_list_active_events_returns_only_new_and_future` — LP-05 combined: 1 NEW+future + 1 NEW+past + 1 FINISHED+future → only NEW+future surfaces
  7. `test_smoke_get_and_list_active` — W-2 revision smoke (replaces brittle inline `python -c` verify from earlier plan revision)
  8. `test_list_active_events_empty_store` — empty store yields `[]`
- All time-sensitive tests monkey-patch the module-level `utc_now` via `monkeypatch.setattr("line_provider.selectors.list_active_events.utc_now", lambda: _NOW)` with `_NOW = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)` — fully deterministic, no `freezegun` dependency, no race with the real wall-clock on CI.

## Task Commits

1. **Task 1 — RED phase (failing smoke for selectors)** — `ef8e820` (test)
2. **Task 1 — GREEN phase (selectors implementation)** — `065fb29` (feat)
3. **Task 2 — Full 8-test suite expansion** — `ef01829` (test)

## Files Created/Modified

- `src/line_provider/selectors/__init__.py` — empty package marker
- `src/line_provider/selectors/get_event_by_id.py` — 1 function, 14 lines, 0 comments. Imports limited to `uuid.UUID`, `InMemoryEventStore`, `Event`. Pure delegate.
- `src/line_provider/selectors/list_active_events.py` — 1 function, 13 lines (post-ruff-format), 0 comments. Imports `utc_now` from `config.time` (module-level — monkey-patchable), `InMemoryEventStore`, `Event`, `EventState`.
- `tests/line_provider/test_selectors.py` — 8 async tests + private `_event` factory. Module docstring cites LP-04, LP-05, and Open Question 4 (utc_now monkey-patch decision). 10 REQ-ID references via grep (`LP-04|LP-05` count). 5 instances of the monkey-patch target string `line_provider.selectors.list_active_events.utc_now`.

## Decisions Made

- **Module-level `utc_now` import for monkey-patch testability** — Open Question 4 from 02-RESEARCH.md fixed in favour of the no-DI option. The function signature stays clean (`async def list_active_events(store) -> list[Event]`) and tests use `monkeypatch.setattr("line_provider.selectors.list_active_events.utc_now", lambda: _NOW)`. Production code does not pay any complexity tax for testability — `now = utc_now()` reads exactly like the canonical `from config.time import utc_now` pattern already established in `schemas/events.py` (FutureDeadline validator).
- **Returning `Event | None` (not raising) from `get_event_by_id`** — D-19 from 02-CONTEXT.md says route → 404 if missing. We push the None→404 translation up to the route handler (Plan 02-07) rather than have the selector raise a domain exception. Reason: this selector is pure read; the only "error" condition is "event not in store", which is not a domain exception (no contract violated). Routes own HTTP error semantics; selectors own data access semantics.
- **Snapshot consistency: `now = utc_now()` captured once** — Plan 02 RESEARCH.md §«list_active_events selector» (line 855-869) showed the exact pattern. Reading `utc_now()` once at the top of the function (rather than inside the comprehension) ensures all events are filtered against the same instant. If `list_all()` returns 1000 events, the comprehension does not race with system clock changes mid-iteration.
- **Strict `>` boundary, not `>=`** — Plan 02 threat T-06-03 (boundary case deadline == now). An event exactly on the boundary is treated as already-expired (not active). Test `test_list_active_events_excludes_deadline_equal_to_now` fixes this contract so Plan 02-07 routes don't accidentally expose boundary events that bet-maker would then have to reject again on POST /bet (BM-06).

## Deviations from Plan

### Pre-commit auto-format

**1. [Pre-commit auto-format] `ruff` reordered imports in `tests/line_provider/test_selectors.py` during the RED commit (Task 1 RED phase)**
- **Found during:** Task 1 RED commit (`ef8e820`)
- **Issue:** When `line_provider.selectors.*` did not yet exist on disk, ruff's import sorter (I001) classified `from line_provider.selectors.* import …` as a third-party import and grouped it above the first-party `from line_provider.infrastructure.store.in_memory import …`. After Task 1 GREEN landed the modules, ruff would re-classify them as first-party — this is the same RED-then-GREEN drift pattern documented in Plan 02-04 (commit `fc7c07c` → `69a7beb` → `44f071a`) and Plan 02-05 (commits `51b97fb` → `e6c77b9` → `81f807e`).
- **Fix:** Accepted ruff's output at RED commit (`ef8e820`). At Task 2 expansion (`ef01829`) — rewrote the test file in its entirety with the canonical first-party import block, ruff format passed without further changes.
- **Files modified:** `tests/line_provider/test_selectors.py`
- **Commit:** Folded into `ef8e820` (RED) and stabilised in `ef01829` (full suite).

**2. [Pre-commit auto-format] `ruff format` collapsed multi-line list comprehension in `list_active_events.py` to a single line**
- **Found during:** Task 1 GREEN commit (`065fb29`)
- **Issue:** Plan's example `action` block formatted the return as a 5-line comprehension:
  ```python
  return [
      e
      for e in await store.list_all()
      if e.state == EventState.NEW and e.deadline > now
  ]
  ```
  Ruff format detected that the collapsed form fits within the 100-char limit and rewrote it to:
  ```python
  return [e for e in await store.list_all() if e.state == EventState.NEW and e.deadline > now]
  ```
- **Fix:** Accepted ruff's output — semantically identical, both readable, the project convention prefers the formatter's choice. Acceptance criterion `grep -q "e.state == EventState.NEW and e.deadline > now"` is preserved (the entire predicate string is on one line).
- **Files modified:** `src/line_provider/selectors/list_active_events.py`
- **Commit:** Folded into `065fb29` (Task 1 GREEN).

## Threat Surface Scan

No new surface beyond the plan's `<threat_model>` (T-06-01..T-06-05 all addressed):

- T-06-01 (Tampering / Selector mutates store): selectors use only `store.get_by_id` and `store.list_all` (both lock-free read methods from Plan 02-04). No store mutation, no `_data[…]=` assignment, no method on `_lock`. Verified by inspection and by `test_list_active_events_excludes_finished_states` which proves the comprehension does not promote/demote any state.
- T-06-02 (Information Disclosure / FINISHED leak): strict `state == EventState.NEW` filter; `test_list_active_events_excludes_finished_states` proves both `FINISHED_WIN` and `FINISHED_LOSE` are excluded.
- T-06-03 (Boundary case deadline == now): strict `>` (not `>=`); `test_list_active_events_excludes_deadline_equal_to_now` fixes behaviour.
- T-06-04 (DoS / linear scan): accept per plan (in-memory store is ТЗ requirement; for the test-task scale events are O(10)–O(100)).
- T-06-05 (Repudiation / non-deterministic clock): mitigated by `monkeypatch.setattr("line_provider.selectors.list_active_events.utc_now", lambda: _NOW)`. Five of the eight tests use this monkey-patch; the two `get_event_by_id` tests do not need time, and the empty-store test does not exercise the time predicate.

## Known Stubs

None. Both selector modules are fully wired with their final production implementations. No `NotImplementedError`, no TODO markers, no placeholder return values. Plan 02-07 routes can import these directly.

## Issues Encountered

None beyond the two auto-formatter deviations above. The smoke test failed exactly as expected at RED phase (`ModuleNotFoundError: No module named 'line_provider.selectors'`), passed immediately after Task 1 GREEN, and all 8 final tests passed on the first run after Task 2 expansion. No architectural decisions (Rule 4) needed. No checkpoints raised. No mypy strict errors. No ruff lint failures.

## User Setup Required

None — pure-Python read-only selectors, no external services, no auth gates, no env vars, no manual verification.

## TDD Gate Compliance

Plan-level TDD cycle confirmed in git log (most recent first):

1. `ef01829` test(02-06): expand selectors test suite to 8 unit tests — final test extension (RED phase was already covered by the smoke commit; the new 7 tests passed immediately against existing GREEN implementation, so this commit is REFACTOR-shaped in TDD terms — extending coverage without behaviour change)
2. `065fb29` feat(02-06): add line_provider selectors layer — GREEN gate
3. `ef8e820` test(02-06): add failing smoke test for selectors layer — RED gate

RED → GREEN → coverage-extension sequence preserved.

## Self-Check: PASSED

**Files verified:**
- `src/line_provider/selectors/__init__.py` — FOUND
- `src/line_provider/selectors/get_event_by_id.py` — FOUND (async get_event_by_id, returns Event | None, delegates to store.get_by_id)
- `src/line_provider/selectors/list_active_events.py` — FOUND (async list_active_events, filters state==NEW AND deadline > utc_now(), module-level utc_now import)
- `tests/line_provider/test_selectors.py` — FOUND (8 async tests, 5 monkey-patches of utc_now, 10 LP-04/LP-05 references)

**Commits verified:**
- `ef8e820` — FOUND (test(02-06): add failing smoke test for selectors layer)
- `065fb29` — FOUND (feat(02-06): add line_provider selectors layer (get_event_by_id, list_active_events))
- `ef01829` — FOUND (test(02-06): expand selectors test suite to 8 unit tests)

**Verification commands re-run:**
- `uv run pytest tests/line_provider/test_selectors.py -q` → 8 passed
- `uv run pytest tests/line_provider -q` → 72 passed (64 baseline + 8 new — no regressions in P1, P2-01..05)
- `uv run mypy --strict src/line_provider/selectors tests/line_provider/test_selectors.py` → Success: no issues found in 4 source files
- `uv run ruff check src/line_provider/selectors tests/line_provider/test_selectors.py` → All checks passed!
- `grep -q "async def get_event_by_id" src/line_provider/selectors/get_event_by_id.py` → exit 0
- `grep -q "async def list_active_events" src/line_provider/selectors/list_active_events.py` → exit 0
- `grep -q "from config.time import utc_now" src/line_provider/selectors/list_active_events.py` → exit 0
- `grep -q "e.state == EventState.NEW and e.deadline > now" src/line_provider/selectors/list_active_events.py` → exit 0
- `grep -q "return await store.get_by_id(event_id)" src/line_provider/selectors/get_event_by_id.py` → exit 0
- `grep -c "^# " src/line_provider/selectors/list_active_events.py src/line_provider/selectors/get_event_by_id.py` → both 0
- `grep -c "^async def test_" tests/line_provider/test_selectors.py` → 8
- `grep -q "monkeypatch.setattr" tests/line_provider/test_selectors.py` → exit 0
- `grep -c "line_provider.selectors.list_active_events.utc_now" tests/line_provider/test_selectors.py` → 5 (>=4 required)
- `grep -c "LP-04\|LP-05" tests/line_provider/test_selectors.py` → 10 (>=7 required)

## Next Phase Readiness

- **Wave 3 of Phase 2 complete (both halves).** Plan 02-05 (interactors — write side: create_event + set_event_state) and Plan 02-06 (selectors — read side: get_event_by_id + list_active_events) together cover the full domain logic surface that Plan 02-07 routes will consume. There are no remaining domain-layer dependencies for Plan 02-07.
- **Selector contract is stable.** Plan 02-07's `GET /event/{event_id}` route will call `await get_event_by_id(store, event_id=event_id)`, then `if event is None: raise HTTPException(status_code=404, detail=...)`, then return `EventRead.model_validate(event.model_dump())`. `GET /events` will call `await list_active_events(store)` and return `[EventRead.model_validate(e.model_dump()) for e in result]`. No further selector edits required.
- **Open Question 4 closed.** monkey-patch beats DI for testability of `utc_now`-dependent code paths. Bet-maker selectors (Phase 3 / Phase 4) will likely adopt the same pattern when filtering by `created_at` / `updated_at`.
- **LP-04 and LP-05 advanced from partial to partial+ — the read-data path is fully implemented**; full closure happens when Plan 02-07 routes wire selectors to HTTP and pytest-cov gates verify coverage ≥85% on `src/line_provider`. The 8 new tests carry the LP-04 / LP-05 invariants forward to the next plan with grep-traceable REQ-ID docstrings.
- **Open Todos:** None. Plan 02-07 (routes — final plan of Phase 2) is the only remaining plan; it consumes interactors (02-05) and selectors (02-06), and closes LP-03, LP-04, LP-05, LP-08, QA-04, QA-05 fully.

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
