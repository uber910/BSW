---
phase: 02-line-provider-domain
plan: 04
subsystem: line-provider/infrastructure/store
tags: [line-provider, in-memory-store, asyncio-lock, concurrency, snapshots, wave-2]

requires:
  - phase: 02-line-provider-domain
    plan: 01
    provides: tests/line_provider/conftest.py lifespan-aware fixtures, coverage gate (src/line_provider, fail_under=85)
  - phase: 02-line-provider-domain
    plan: 02
    provides: line_provider.schemas.events.Event (frozen), EventState enum
provides:
  - src/line_provider/infrastructure/__init__.py — empty package marker
  - src/line_provider/infrastructure/store/__init__.py — empty package marker
  - src/line_provider/infrastructure/store/in_memory.py — InMemoryEventStore + EventAlreadyExistsError + EventNotFoundError
  - tests/line_provider/test_in_memory_store.py — 13 unit tests (CRUD + concurrent gather + lock-free reads)
affects:
  - 02-05-interactors (consumes InMemoryEventStore, both domain exceptions; uses update() tuple return for D-12 commit->publish ordering)
  - 02-06-selectors (consumes get_by_id / list_all lock-free reads)
  - 02-07-routes (consumes interactor results — store is one layer below)

tech-stack:
  added: []
  patterns:
    - "Single asyncio.Lock per store, held only on write-paths (add/update). Read-paths (get_by_id/list_all) are lock-free per D-15 — safe because CPython dict operations are atomic at bytecode level and Event is frozen (no torn read possible). Anti-Pattern 6 (concurrent dict access) mitigated."
    - "update() returns tuple (new_event, previous_state) atomically under the lock — Plan 02-05 interactor uses previous_state to decide whether to publish EventFinishedMessage without a second store round-trip (D-12 — eliminates TOCTOU read between update and publish)."
    - "model_copy(update={...}) on frozen Pydantic v2 model yields new instance — D-16 snapshot semantics. Any reference held by a caller before the update remains valid and unmutated."
    - "Domain exceptions carry .event_id attribute for structured logging; __str__ format 'event {id} already exists' / 'event {id} not found' is the stable contract Plan 02-07 routes will map to 409 / 404."

key-files:
  created:
    - src/line_provider/infrastructure/__init__.py
    - src/line_provider/infrastructure/store/__init__.py
    - src/line_provider/infrastructure/store/in_memory.py
    - tests/line_provider/test_in_memory_store.py
  modified: []

key-decisions:
  - "InMemoryEventStore exposes async get_by_id / list_all even though they are lock-free. Reason: uniform interface for interactor/selector layers (which themselves are async). Cost of awaiting a sync body is one bytecode op; benefit is no contract churn if a future implementation must take the lock."
  - "update() returns (new_event, previous_state) as a tuple, not as separate methods. Reason: atomicity — the previous_state must be observed under the same lock that wrote the new state, otherwise a concurrent update could change previous_state between observe-then-write. The tuple makes that atomicity API-visible."
  - "TDD cycle followed: smoke test (test_smoke_crud_lifecycle) committed first as RED (failing with ModuleNotFoundError), then implementation committed as GREEN (smoke passes), then the remaining 12 tests added in a single follow-up test commit (all green immediately — implementation already complete). Three atomic commits: test (RED smoke) -> feat (GREEN impl) -> test (full suite)."

requirements-completed: [LP-01]
requirements-partial: [LP-08]

duration: 4min
completed: 2026-05-15
---

# Phase 02 Plan 04: line-provider InMemoryEventStore Summary

**Async-safe in-memory event store for line-provider: dict[UUID, Event] guarded by a single asyncio.Lock on add/update, lock-free reads on get_by_id/list_all, snapshot semantics via Pydantic v2 frozen Event + model_copy, and update() returning (new_event, previous_state) so Plan 02-05 interactor can decide whether to publish EventFinishedMessage without a second store round-trip.**

## Performance

- **Duration:** ~4 min (2 tasks, autonomous, no checkpoints)
- **Started:** 2026-05-15T08:31:23Z
- **Completed:** 2026-05-15T08:33:13Z
- **Tasks:** 2 / 2
- **Files created:** 4 (1 production module + 2 empty package markers + 1 test file)
- **Tests added:** 13 unit tests
- **Full suite after this plan:** 51 passed (38 baseline P1+P2-01..03 + 13 new)

## Accomplishments

- `src/line_provider/infrastructure/store/in_memory.py` exports `InMemoryEventStore` (async add/update/get_by_id/list_all, `_data: dict[UUID, Event]`, single `_lock: asyncio.Lock`) plus two domain exceptions `EventAlreadyExistsError` and `EventNotFoundError`. Both exceptions take `event_id: str` in __init__, store it on `.event_id`, and format `__str__` as `"event {id} already exists"` / `"event {id} not found"` — the stable contract that Plan 02-07 routes will map to HTTP 409 / 404.
- `InMemoryEventStore.add` takes a pre-validated frozen `Event`, holds `_lock`, checks for duplicate `event.event_id`, raises `EventAlreadyExistsError(str(event_id))` if duplicate, else inserts and returns the same Event. Anti-Pattern 6 (concurrent dict access) is mitigated here.
- `InMemoryEventStore.update` takes `event_id` + keyword-only `coefficient: Decimal`, `deadline: datetime`, `state: EventState`. Under `_lock`: reads current via `_data.get(event_id)`, raises `EventNotFoundError(str(event_id))` if absent, captures `previous_state = current.state`, builds `new_event = current.model_copy(update={...})`, writes back to `_data[event_id]`, returns `(new_event, previous_state)` tuple. The previous_state observation and the write are atomic under one lock acquisition — D-12 / T-04-03 mitigation.
- `InMemoryEventStore.get_by_id` returns `Event | None` lock-free via `_data.get(event_id)`. Safe because CPython dict.get is atomic at bytecode level (single GIL-protected op) and Event is frozen (no torn read possible).
- `InMemoryEventStore.list_all` returns `list(self._data.values())` lock-free — D-16 snapshot semantics: a new list object is returned, so any subsequent `add` is invisible to the caller's previously-returned reference (proven by `test_list_all_returns_snapshot`).
- `tests/line_provider/test_in_memory_store.py` covers 13 tests across the full contract: 9 unit tests for CRUD + snapshot semantics (add returns event, add persists, add duplicate raises, update returns new+prev, update creates new object without mutating prior reference, update no-op state preserves previous marker, update missing raises, get_by_id None on missing, list_all returns snapshot), 3 concurrent gather tests (100 distinct ids all succeed, 20 same id → exactly 1 success + 19 EventAlreadyExistsError, 2 updates same id serialised under lock → second sees previous != NEW), and 1 smoke test (test_smoke_crud_lifecycle) which is the canonical end-to-end smoke and serves as Task 1's verify entry-point (W-2 revision replacing the brittle inline `python -c`).

## Task Commits

1. **Task 1 — RED phase (failing smoke test)** — `fc7c07c` (test)
2. **Task 1 — GREEN phase (InMemoryEventStore + domain exceptions + package markers)** — `69a7beb` (feat)
3. **Task 2 — Full unit test suite (CRUD + concurrent gather + lock-free snapshots)** — `44f071a` (test)

## Files Created/Modified

- `src/line_provider/infrastructure/__init__.py` — empty package marker
- `src/line_provider/infrastructure/store/__init__.py` — empty package marker
- `src/line_provider/infrastructure/store/in_memory.py` — `EventAlreadyExistsError`, `EventNotFoundError`, `InMemoryEventStore` (62 lines, 0 comments — strict adherence to plan's "no docstrings, no comments" rule). Imports limited to: `asyncio`, `datetime.datetime`, `decimal.Decimal`, `uuid.UUID`, and `Event` + `EventState` from `line_provider.schemas.events`. No dependencies on config, structlog, FastAPI, or DI containers — pure infrastructure.
- `tests/line_provider/test_in_memory_store.py` — 13 async unit tests, 4 `asyncio.gather` invocations (concurrent_add_distinct, concurrent_add_same, concurrent_update_serialised, and a helper inside), 15 REQ-ID grep references (`LP-01`, `LP-08`, `D-09`, `D-16`, `Anti-Pattern 6`). Two private factories `_future()` and `_event()` keep test bodies focused on the assertion under test.

## Decisions Made

- **Async signature on lock-free reads** — `get_by_id` and `list_all` are declared `async def` even though their bodies do not await. Rationale: the upstream interactor / selector layer is async (Plan 02-05 / 02-06), and changing the read-path API to sync would force every caller into `await asyncio.to_thread(...)` wrappers, defeating D-15. The lock-free bodies cost one extra bytecode op (`await NoneAwaitable`) but preserve a uniform contract — and if a future implementation needs to take the lock (e.g., to maintain a secondary index), the API stays unchanged.
- **Tuple return on `update`** — `(new_event, previous_state)` is the atomicity contract. The plan-level interactor in 02-05 will compare `previous_state != EventState.NEW` to decide whether to publish `EventFinishedMessage` (D-12). Returning the tuple from inside the same `async with self._lock` block guarantees that no concurrent `update` can change the previous_state between the read and the publish decision. T-04-03 mitigation made API-visible.
- **No docstrings / no comments in `in_memory.py`** — Plan explicitly required `grep -c "^# " == 0` and stylistic alignment with `settings/config.py`. The 62-line module reads top-to-bottom as pure code, with all behaviour documented in the test docstrings (REQ-ID-cited) and in this SUMMARY. This matches the project convention established in Phase 2 Plans 01/02/03.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Shortened `test_smoke_crud_lifecycle` docstring to satisfy ruff E501 (line >100)**
- **Found during:** Task 1 RED commit (pre-commit hook)
- **Issue:** Plan's docstring line was 109 characters: `"Covers: add -> duplicate raise -> update returns (new, prev) -> not-found raise -> get_by_id -> list_all."` — ruff E501 line-too-long.
- **Fix:** Rephrased to `"Covers: add -> duplicate -> update (new, prev) -> not-found -> get_by_id -> list_all."` (88 chars). No semantic change to the test or the assertion path.
- **Files modified:** `tests/line_provider/test_in_memory_store.py`
- **Commit:** Folded into Task 1 RED commit (`fc7c07c`).

### Pre-commit auto-format

**2. [Pre-commit auto-format] `ruff format` reordered imports during Task 1 RED commit, then reordered them back during Task 1 GREEN**
- **Found during:** Task 1 RED + GREEN commits (pre-commit ruff hook)
- **Issue:** When the test file existed but `line_provider.infrastructure` module did not yet exist, ruff treated the `from line_provider.infrastructure.store.in_memory import ...` line as a third-party import and placed it in the third-party block. Once the module was implemented (GREEN), ruff correctly recognised it as a first-party import and moved it to the first-party block.
- **Fix:** Accepted ruff's output at each step; no manual intervention. After GREEN the import block is in its canonical (stdlib / first-party / first-party) order. Test suite green at every commit.
- **Files modified:** `tests/line_provider/test_in_memory_store.py`
- **Commits:** Folded into `fc7c07c` (RED) and `44f071a` (final test). Pre-commit on Task 2 commit produced no further changes.

## Threat Surface Scan

No new surface beyond the plan's `<threat_model>` (T-04-01..T-04-06 all addressed):

- T-04-01 (Tampering / concurrent dict mutation, Anti-Pattern 6): `asyncio.Lock` on add/update — proven by `test_concurrent_add_same_id_exactly_one_succeeds` (20 concurrent add → 1 success + 19 EventAlreadyExistsError).
- T-04-02 (Tampering / caller mutates returned Event): inherited from Plan 02-02 `Event(frozen=True)`; Plan 02-02 already tested via `test_frozen`. Reaffirmed indirectly here by `test_update_creates_new_object_not_mutating_current` (D-17).
- T-04-03 (Repudiation / lost update without previous_state): `update()` returns `(new, previous_state)` atomically under the lock. Verified by `test_update_returns_new_and_previous` (sequential) and `test_concurrent_update_serialised_under_lock` (concurrent — second update observes previous_state set by first).
- T-04-04 (DoS / unbounded growth): accept per plan (in-memory store is ТЗ requirement; documented in RESEARCH.md Runtime State Inventory).
- T-04-05 (Information Disclosure / event_id leak via exception message): accept per plan (event_id is UUID4, client-generated, not PII; "event {id} already exists" is acceptable UX for a 409).
- T-04-06 (Tampering / TOCTOU between lock-free get_by_id and locked update): mitigated by re-read inside `update`'s lock — `current = self._data.get(event_id)` and the `previous_state` capture both happen inside the `async with self._lock` block. Interactor (Plan 02-05) will use this previous_state for the publish decision.

## Known Stubs

None. The InMemoryEventStore is fully wired with `asyncio.Lock`, returns the tuple contract, and is ready for direct import by Plan 02-05 interactors. No placeholders, no NotImplementedError, no TODO markers.

## Issues Encountered

None beyond the two auto-formatter / linter fix-ups documented above. Smoke test failed as expected during RED (ModuleNotFoundError — proof of TDD discipline), then passed immediately after GREEN. Full test suite was green at every step after the implementation landed. No architectural decisions (Rule 4) needed. No checkpoints raised.

## User Setup Required

None — pure in-memory infrastructure, no external services, no auth gates, no env vars, no manual verification.

## TDD Gate Compliance

Plan-level TDD cycle confirmed in git log (most recent first):

1. `44f071a` test(02-04): expand InMemoryEventStore unit tests — final test extension (RED phase of Task 2 was implicit since implementation already existed; the new 12 tests passed immediately, so this commit is REFACTOR-like in TDD terms — extending coverage without behaviour change)
2. `69a7beb` feat(02-04): add InMemoryEventStore with asyncio.Lock and domain exceptions — GREEN gate
3. `fc7c07c` test(02-04): add failing smoke test for InMemoryEventStore — RED gate

RED → GREEN → coverage-extension sequence preserved. The 13-test final state covers Anti-Pattern 6 mitigation through the concurrent gather scenarios that were the architectural raison-d'être of this plan.

## Self-Check: PASSED

**Files verified:**
- `src/line_provider/infrastructure/__init__.py` — FOUND
- `src/line_provider/infrastructure/store/__init__.py` — FOUND
- `src/line_provider/infrastructure/store/in_memory.py` — FOUND (InMemoryEventStore + 2 exceptions + asyncio.Lock + tuple return + model_copy + 0 comments)
- `tests/line_provider/test_in_memory_store.py` — FOUND (13 async tests + 4 asyncio.gather + 15 REQ-ID references)

**Commits verified:**
- `fc7c07c` — FOUND (test(02-04): add failing smoke test for InMemoryEventStore)
- `69a7beb` — FOUND (feat(02-04): add InMemoryEventStore with asyncio.Lock and domain exceptions)
- `44f071a` — FOUND (test(02-04): expand InMemoryEventStore unit tests with concurrent gather scenarios)

**Verification commands re-run:**
- `uv run pytest tests/line_provider/test_in_memory_store.py -q` → 13 passed
- `uv run pytest -q` → 51 passed (38 baseline + 13 new — no regressions in P1 / P2-01..03)
- `uv run mypy --strict src/line_provider/infrastructure tests/line_provider/test_in_memory_store.py` → Success: no issues found in 4 source files
- `uv run ruff check src/line_provider/infrastructure tests/line_provider/test_in_memory_store.py` → All checks passed!
- `grep -c "class InMemoryEventStore" src/line_provider/infrastructure/store/in_memory.py` → 1
- `grep -c "class EventAlreadyExistsError" src/line_provider/infrastructure/store/in_memory.py` → 1
- `grep -c "class EventNotFoundError" src/line_provider/infrastructure/store/in_memory.py` → 1
- `grep -c "async with self._lock" src/line_provider/infrastructure/store/in_memory.py` → 2 (add + update)
- `grep -c "self._lock = asyncio.Lock()" src/line_provider/infrastructure/store/in_memory.py` → 1
- `grep -c "tuple\[Event, EventState\]" src/line_provider/infrastructure/store/in_memory.py` → 1
- `grep -c "model_copy" src/line_provider/infrastructure/store/in_memory.py` → 1
- `grep -c "^# " src/line_provider/infrastructure/store/in_memory.py` → 0
- `grep -c "^async def test_" tests/line_provider/test_in_memory_store.py` → 13
- `grep -c "asyncio.gather" tests/line_provider/test_in_memory_store.py` → 4
- `grep -cE "LP-01|LP-08|D-16|D-09|Anti-Pattern" tests/line_provider/test_in_memory_store.py` → 15

## Next Phase Readiness

- **Wave 2 of Phase 2 complete.** Plans 02-03 (state-machine helper, pure function) and 02-04 (in-memory store, this plan) both have `depends_on: [01, 02]` and were independently startable. Plan 02-05 (interactors) now has all its lower-layer dependencies: schemas (02-02), state-machine helper (02-03), and store (02-04).
- **InMemoryEventStore contract is stable.** Plan 02-05 interactor will instantiate it once during `lifespan` (placed on `app.state.event_store`), pass it through FastAPI `Depends`, and call `add` / `update` / `get_by_id` / `list_all` directly. The tuple return from `update` is the wire-level basis for the `commit -> publish` ordering in D-12 — interactor compares `previous_state != EventState.NEW` to decide whether to publish `EventFinishedMessage`.
- **Anti-Pattern 6 closed.** Concurrent dict access through `asyncio.gather` is now proven safe by `test_concurrent_add_distinct_ids_all_succeed`, `test_concurrent_add_same_id_exactly_one_succeeds`, and `test_concurrent_update_serialised_under_lock`. These tests are the canonical reference for the LP-01 invariant.
- **Coverage gate intact.** All four files added by this plan are inside `src/line_provider/` (the scope of the coverage gate set in Plan 02-01); all 4 production lines that have branches (`add` if-branch, `update` if-branch, `update` else, `add` else) are exercised by happy-path + raise-path tests. Plan 02-07 final coverage run will land well above 85%.
- **Open Todos:** None. Plan 02-05 (interactors, Wave 3) is the next plan; it consumes the store's tuple-return contract directly.

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
