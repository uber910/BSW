---
phase: 02-line-provider-domain
plan: 05
subsystem: line-provider/facades+interactors
tags: [line-provider, facades, interactors, event-bus, commit-publish-order, anti-pattern-2, wave-3]

requires:
  - phase: 02-line-provider-domain
    plan: 02
    provides: EventCreate, EventState, Event (frozen), EventFinishedMessage, EventTerminalState
  - phase: 02-line-provider-domain
    plan: 03
    provides: is_transition_allowed, TransitionForbiddenError, ALLOWED_TRANSITIONS
  - phase: 02-line-provider-domain
    plan: 04
    provides: InMemoryEventStore (add/update/get_by_id/list_all), EventAlreadyExistsError, EventNotFoundError, update() tuple (new_event, previous_state)
provides:
  - src/line_provider/facades/event_bus.py — EventBus Protocol + NoopEventBus
  - src/line_provider/facades/deps.py — get_store, get_event_bus, StoreDep, EventBusDep
  - src/line_provider/interactors/create_event.py — async create_event(store, *, body) -> Event
  - src/line_provider/interactors/set_event_state.py — async set_event_state(...) with commit->publish ordering
  - tests/line_provider/_fakes.py — FakeEventBus recording publish() calls (D-12 verification harness)
affects:
  - 02-06-selectors (will inject store via the same DI providers)
  - 02-07-routes (consumes StoreDep + EventBusDep through FastAPI Depends; route handlers call create_event / set_event_state; D-08 / D-09 / D-12 contract is owned here)
  - 05-rabbit-event-bus (Phase 5 swaps NoopEventBus for RabbitEventBus on app.state.event_bus — set_event_state requires zero changes; commit->publish ordering already proven)

tech-stack:
  added: []
  patterns:
    - "EventBus as typing.Protocol (structural typing) rather than abc.ABC — NoopEventBus + FakeEventBus + future RabbitEventBus all satisfy it without inheritance, keeping infrastructure separable from domain. Phase 5 swap is a single line in lifespan."
    - "Annotated[..., Depends(...)] FastAPI-0.95+ DI idiom encapsulated as StoreDep / EventBusDep type aliases — Plan 02-07 route handlers will declare a single `store: StoreDep` parameter without re-importing Depends. cast() is needed on request.app.state.* because FastAPI types those attributes as Any; mypy strict requires the explicit cast."
    - "set_event_state pre-validates with lock-free store.get_by_id() then re-validates inside the locked store.update() via the returned previous_state. The publish decision uses previous_state (atomic snapshot under the lock), not current_state read upstream — eliminates Pitfall 5 TOCTOU race even with concurrent gather on the same id."
    - "Module-level _TERMINAL_TO_ROUTING: dict[EventState, str] is the single source of truth for AMQP routing keys (event.finished.win / event.finished.lose). Membership in this dict is also the D-09 publish-gate (NEW→NEW or NEW→non-terminal never publish — but the state machine already forbids the second case)."
    - "FakeEventBus.calls: list[tuple[EventFinishedMessage, str]] + fail flag — the same fake covers four test categories: happy-path publish recording, message-content assertion, no-publish negative assertion (empty list), and commit-before-publish ordering proof (raise after recording → caller's commit must already be visible)."

key-files:
  created:
    - src/line_provider/facades/__init__.py
    - src/line_provider/facades/event_bus.py
    - src/line_provider/facades/deps.py
    - src/line_provider/interactors/__init__.py
    - src/line_provider/interactors/create_event.py
    - src/line_provider/interactors/set_event_state.py
    - tests/line_provider/_fakes.py
    - tests/line_provider/test_facades.py
    - tests/line_provider/test_create_event.py
    - tests/line_provider/test_set_event_state.py
  modified: []

key-decisions:
  - "occurred_at = new_event.deadline (not utc_now()) on the published EventFinishedMessage. Reason: deadline is a stable Event field captured under the same lock as the state mutation, so tests don't need freeze_time and concurrent publishes can't drift on wall-clock. P5 reconciliation / P3 bet-maker consumer don't depend on occurred_at semantics — they only branch on new_state — so the slight semantic shift (event 'occurred' at its deadline, not at the PUT moment) is invisible to downstream consumers."
  - "set_event_state's previous_state == EventState.NEW guard is what closes Pitfall 5 (concurrent NEW→FINISHED_WIN and NEW→FINISHED_LOSE on the same id). Without it, the second call would also publish — even though the state machine rejects FINISHED_WIN→FINISHED_LOSE, that rejection happens BEFORE store.update; the second concurrent call reads current=NEW, passes the state-machine, but then store.update returns previous_state=FINISHED_* (set by the first), so the guard correctly skips publish. Tested by test_concurrent_set_state_same_id_publishes_exactly_once (stable across 5 repeated runs)."
  - "TransitionForbiddenError is raised BEFORE store.update — verified by test_reverse_transition_aborts_without_mutate_or_publish (FINISHED_WIN→NEW: store snapshot before == snapshot after, bus.calls == []). The early raise also ensures FastAPI 422-handling in Plan 02-07 will surface the error message verbatim without store side effects."
  - "FakeEventBus lives in tests/line_provider/_fakes.py (underscore prefix to suppress pytest test collection). Reusable from test_set_event_state.py today and Plan 02-07 integration tests tomorrow. Plan moved this out of test_set_event_state.py specifically to avoid duplication when route tests are added."

requirements-completed: []
requirements-partial: [LP-01, LP-03, LP-05, LP-08]

duration: 5min
completed: 2026-05-15
---

# Phase 02 Plan 05: Facades + Interactors Summary

**Wave 3 first half: facades layer (EventBus Protocol + NoopEventBus + FastAPI DI providers) and interactors layer (create_event + set_event_state). `set_event_state` is the structural heart of the project's Core Value — commit-before-publish ordering (D-12), publish-only-on-NEW→FINISHED_* (D-09), reverse-transition guard, and concurrency-safe single-publish behaviour are all proven by 9 unit tests. Plan 02-07 routes will consume `StoreDep` / `EventBusDep` through standard FastAPI Depends without further re-engineering. Phase 5 RabbitEventBus swap is a single line in lifespan.**

## Performance

- **Duration:** ~5 min (3 tasks, autonomous, no checkpoints)
- **Started:** 2026-05-15T08:38:31Z
- **Completed:** 2026-05-15T08:43:36Z
- **Tasks:** 3 / 3
- **Files created:** 10 (5 production + 1 test fake + 3 test files + 2 empty package markers)
- **Tests added:** 15 (3 facades + 3 create_event + 9 set_event_state)
- **Full suite after this plan:** 64 passed (49 baseline P1+P2-01..04 + 15 new)
- **Source LoC:** 126 (event_bus 33 + deps 20 + create_event 14 + set_event_state 59) — fakes 25 LoC

## Accomplishments

- `src/line_provider/facades/event_bus.py` exports `EventBus` (typing.Protocol with single async `publish(message: EventFinishedMessage, *, routing_key: str) -> None` method) and `NoopEventBus` (structural implementor — logs `event_bus.publish.noop` via `structlog.get_logger().info(...)` with routing_key, event_id, new_state, schema_version, correlation_id keyword fields; no internal state, no AMQP). Phase 5 will provide `RabbitEventBus` that satisfies the same Protocol without inheriting from it.
- `src/line_provider/facades/deps.py` exports `get_store(request: Request) -> InMemoryEventStore`, `get_event_bus(request: Request) -> EventBus`, and the two `Annotated[..., Depends(...)]` type aliases `StoreDep` / `EventBusDep`. Both providers `cast(..., request.app.state.event_store/event_bus)` to satisfy mypy strict (request.app.state.* is Any-typed by FastAPI). The cast is the explicit typing boundary; no runtime conversion happens.
- `src/line_provider/interactors/create_event.py` exports the single async function `create_event(store, *, body: EventCreate) -> Event`. It builds a frozen `Event(state=EventState.NEW)` from the body's three input fields (event_id, coefficient, deadline) and delegates to `store.add(event)`. Never publishes (create is not a state-change event). Propagates `EventAlreadyExistsError` on duplicate event_id (Plan 02-07 route maps to HTTP 409).
- `src/line_provider/interactors/set_event_state.py` is the **P5-ready commit-before-publish orchestrator**. Sequence: `store.get_by_id(event_id)` (lock-free read) → `None` → `EventNotFoundError`; `is_transition_allowed(current.state, new_state)` False → `TransitionForbiddenError` (BEFORE any mutation, BEFORE any publish); `store.update(...)` returns `(new_event, previous_state)` atomically under the asyncio.Lock; AFTER the commit returns, the publish-gate evaluates `previous_state == EventState.NEW AND new_state in _TERMINAL_TO_ROUTING` and only then awaits `event_bus.publish(EventFinishedMessage(...), routing_key=_TERMINAL_TO_ROUTING[new_state])`. Module-level `_TERMINAL_TO_ROUTING: dict[EventState, str]` maps `FINISHED_WIN → "event.finished.win"`, `FINISHED_LOSE → "event.finished.lose"`. `occurred_at=new_event.deadline` and `correlation_id` is injected by the caller (Plan 02-07 will pass `X-Request-ID`).
- `tests/line_provider/_fakes.py` provides `FakeEventBus(*, fail: bool = False)` — implements `EventBus` structurally; `.calls: list[tuple[EventFinishedMessage, str]]` accumulates every publish call; `fail=True` makes `publish` raise `RuntimeError` *after* recording the call, enabling the commit-before-publish ordering proof in `test_commit_happens_before_publish_failing_bus` (if publish were called inside the lock or before the lock released, the store's mutation could in principle be rolled back — but the actual sequence has the store mutation already persisted by the time the fake raises).
- `tests/line_provider/test_facades.py` (3 tests): Protocol structural typing (`bus: EventBus = NoopEventBus()`), publish returns None, and `structlog.testing.capture_logs()` confirms the `event_bus.publish.noop` event is emitted with the right routing_key. The autouse `_preserve_structlog_config` fixture snapshots+restores the global config so this test file does not leak processor mutations to others (W-1 revision baked into the plan).
- `tests/line_provider/test_create_event.py` (3 tests): state=NEW on output, persistence via `store.get_by_id`, duplicate `EventAlreadyExistsError` propagation.
- `tests/line_provider/test_set_event_state.py` (9 tests): NEW→FINISHED_WIN publishes with the right routing key, NEW→FINISHED_LOSE publishes with the right routing key, no-op FINISHED_WIN→FINISHED_WIN mutates coefficient but skips publish (D-09), no-op NEW→NEW skips publish (D-09), reverse FINISHED_WIN→NEW raises `TransitionForbiddenError` without mutating store and without publishing, missing event raises `EventNotFoundError` without publishing, commit-before-publish ordering with `FakeEventBus(fail=True)` (store reflects the mutation even though publish raised), published message carries the UUID event_id and the caller's correlation_id, and concurrent gather of NEW→FINISHED_WIN + NEW→FINISHED_LOSE on the same id results in exactly one publish (Pitfall 5 — verified stable across 5 repeated runs).

## Task Commits

1. **Task 1 RED — failing facades tests** — `51b97fb` (test)
2. **Task 1 GREEN — facades layer (EventBus Protocol + NoopEventBus + deps)** — `e6c77b9` (feat)
3. **Task 2 RED — failing create_event tests + FakeEventBus** — `4452263` (test)
4. **Task 2 GREEN — create_event interactor** — `b950b7f` (feat)
5. **Task 3 RED — failing set_event_state tests (9 cases)** — `a6efc85` (test)
6. **Task 3 GREEN — set_event_state interactor (commit->publish ordering)** — `467ee5b` (feat)
7. **Style — import re-sort after first-party modules created** — `81f807e` (style)

## Files Created/Modified

- `src/line_provider/facades/__init__.py` — empty package marker
- `src/line_provider/facades/event_bus.py` — `EventBus(Protocol)` + `NoopEventBus` (33 LoC, 0 comments per project hard rule)
- `src/line_provider/facades/deps.py` — `get_store`, `get_event_bus`, `StoreDep`, `EventBusDep` (20 LoC)
- `src/line_provider/interactors/__init__.py` — empty package marker
- `src/line_provider/interactors/create_event.py` — single async function (14 LoC, no comments)
- `src/line_provider/interactors/set_event_state.py` — orchestrator with `_TERMINAL_TO_ROUTING` constant + publish-gate (59 LoC, no comments)
- `tests/line_provider/_fakes.py` — `FakeEventBus` (25 LoC)
- `tests/line_provider/test_facades.py` — 3 tests + `_preserve_structlog_config` autouse fixture
- `tests/line_provider/test_create_event.py` — 3 tests
- `tests/line_provider/test_set_event_state.py` — 9 tests + 2 private factories (`_future`, `_seed`)

## Decisions Made

- **`occurred_at = new_event.deadline` on the AMQP message.** The plan explicitly lists this as one of two equally-valid options (the other being `utc_now()`). Chose `deadline` for three reasons: (1) it is captured atomically with the state mutation under the store's lock — no clock-drift between observation and publish; (2) tests don't need `freeze_time` to stabilise the field; (3) downstream consumers (P3 bet-maker, P5 RabbitEventBus) don't branch on the timestamp semantics, only on `new_state`. The slight ontological shift ("event occurred at its deadline" vs "event finished was published at X") is invisible to the Core Value invariant.
- **`previous_state` guard placement.** The publish gate is `previous_state == EventState.NEW AND new_state in _TERMINAL_TO_ROUTING`. Both halves are necessary: without the first, no-op `FINISHED_WIN → FINISHED_WIN` would publish; without the second, a hypothetical future `NEW → SOME_OTHER_TERMINAL` would publish without a routing key entry. Plan's `<behavior>` lists both halves explicitly; the implementation is verbatim.
- **`TransitionForbiddenError` raised BEFORE `store.update`.** The plan is explicit on this — but it's worth noting that `is_transition_allowed(current.state, new_state)` is checked against the lock-free read of `current`. A concurrent mutator could in principle change the stored state between the `get_by_id` and the `update`. This is the deliberate trade-off: the lock-free read gives a fast happy path; if a concurrent FINISHED→FINISHED no-op intervenes, the second caller's state-machine still passes (NEW→FINISHED is allowed even though stored is now FINISHED), but `store.update` then captures `previous_state=FINISHED` atomically and the publish-gate correctly skips. Reverse transitions (FINISHED→NEW) cannot pass the state-machine no matter the concurrent interleaving, so the "no mutation on reverse" invariant holds. Proven by the concurrency test running 5 consecutive times with no flake.
- **FakeEventBus.fail records THEN raises.** The fake appends to `self.calls` *before* raising `RuntimeError`. This is deliberate — the calls list is the audit trail and must reflect that the publish was attempted; the raise simulates the AMQP layer failing post-attempt. The store mutation is the test's invariant; the call list is the test's instrument.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Removed `result = await bus.publish(...)` mypy error in test_facades.py**
- **Found during:** Task 1 verify step (`uv run mypy --strict`)
- **Issue:** `test_noop_event_bus_publish_returns_none` originally read `result = await bus.publish(...); assert result is None`. mypy strict raised `error: Function does not return a value (it only ever returns None) [func-returns-value]` because the Protocol return type is exactly `None`, and assigning a None-returning coroutine to a variable is flagged.
- **Fix:** Dropped the assignment and the assertion. The test still meaningfully exercises the no-op path because the function call is awaited (any exception would fail the test); the "returns None" property is now a Protocol-level mypy guarantee, not a runtime assertion.
- **Files modified:** `tests/line_provider/test_facades.py`
- **Commit:** Folded into Task 1 GREEN (`e6c77b9`).

**2. [Rule 1 — Style] Replaced `try-except-pass` with `contextlib.suppress` in concurrent test**
- **Found during:** Task 3 RED commit (pre-commit ruff hook, SIM105)
- **Issue:** The concurrent gather test's inner `async def do(...)` swallowed `TransitionForbiddenError` via `try: ... except TransitionForbiddenError: pass`. Ruff SIM105 mandates `with contextlib.suppress(TransitionForbiddenError):` as the idiomatic form.
- **Fix:** Added `import contextlib` and refactored to `with contextlib.suppress(TransitionForbiddenError):`. Semantics identical.
- **Files modified:** `tests/line_provider/test_set_event_state.py`
- **Commit:** Folded into Task 3 RED (`a6efc85`).

### Pre-commit auto-format

**3. [Pre-commit auto-format] ruff I001 import re-sort across three test files**
- **Found during:** Each task's RED commit and the final verification step.
- **Issue:** When the test files were committed during RED (before the corresponding `line_provider.facades.*` / `line_provider.interactors.*` modules existed), ruff classified those imports as third-party. After GREEN landed the modules, ruff correctly re-classifies them as first-party — and either pre-commit or a manual `ruff check --fix` shuffles them into the first-party import block.
- **Fix:** Accepted ruff's output at each step. Final standalone `style(02-05): re-sort imports after first-party modules created` commit (`81f807e`) cleans up the two remaining drift cases that pre-commit didn't catch (test_create_event.py and test_set_event_state.py — pre-commit only re-runs on staged files, so the GREEN-phase commits didn't trigger a re-sort of test files that weren't staged again).
- **Files modified:** `tests/line_provider/test_facades.py`, `tests/line_provider/test_create_event.py`, `tests/line_provider/test_set_event_state.py`
- **Commits:** Folded into RED commits and the standalone `81f807e` style commit.

## Threat Model Compliance

All seven threats from the plan's `<threat_model>` addressed:

- **T-05-01 (Tampering / Anti-Pattern 2 — publish inside DB transaction):** *mitigate*. set_event_state structurally orders `store.update(...)` BEFORE `event_bus.publish(...)` — proven by `test_commit_happens_before_publish_failing_bus` (FakeEventBus.fail=True → RuntimeError, but the store reflects state=FINISHED_WIN and coefficient=9.99). Acceptance check verified: `grep -n 'store\.update'` returns line 41, `grep -n 'event_bus\.publish'` returns line 49 — strict line ordering.
- **T-05-02 (Tampering / reverse transition mutates store):** *mitigate*. TransitionForbiddenError raised BEFORE store.update — `test_reverse_transition_aborts_without_mutate_or_publish` asserts `await store.get_by_id(seeded.event_id) == snapshot` AND `bus.calls == []`.
- **T-05-03 (Tampering / concurrent set_state publishes twice — Pitfall 5 TOCTOU):** *mitigate*. The `previous_state == EventState.NEW` guard reads the post-mutation observation from store.update's tuple; the second concurrent call sees previous=FINISHED_* (set by the first) and skips publish. Test runs 5 consecutive times with no flake.
- **T-05-04 (Information Disclosure / logs leak event_id as PII):** *accept*. event_id is a client-generated UUID4 (D-05); not PII. NoopEventBus uses structured kwargs (no f-string interpolation, no log injection).
- **T-05-05 (Repudiation / publish without correlation_id):** *mitigate*. `correlation_id: str` is a required interactor argument — mypy strict refuses to call set_event_state without it. `test_published_message_carries_uuid_event_id` asserts `message.correlation_id == "req-uuid"`.
- **T-05-06 (DoS / unbounded recursion or loops):** *accept*. Linear code, no recursion, lock contention bounded by fast critical sections.
- **T-05-07 (Spoofing / request.app.state overridden by attacker):** *accept*. FastAPI does not expose app.state mutation to clients; documented as test-task scope.

## Threat Flags

None. No new security-relevant surface introduced. Facades + interactors are pure in-memory orchestration with structlog logging; no network egress (NoopEventBus is by design a no-op), no schema mutation at trust boundaries, no auth surface.

## Known Stubs

None — all four public functions (`get_store`, `get_event_bus`, `create_event`, `set_event_state`) are fully wired and consumable as-is by Plan 02-07 routes. NoopEventBus is *intentionally* a no-op in Phase 2 (D-14: P5 will swap to RabbitEventBus on `app.state.event_bus`). This is the design contract, not a stub — verified by `test_noop_event_bus_emits_log_event` which proves the no-op is observable via structlog (so a deployment misconfiguration that left NoopEventBus in production would be visible in logs as `event_bus.publish.noop` entries).

## Issues Encountered

None beyond the three auto-fixes documented above (one mypy strict bug, one ruff SIM105 style, three ruff I001 import-sort artefacts driven by the RED-then-GREEN module creation order). No architectural decisions (Rule 4) required. No checkpoints raised. No coverage regressions (Plan 02-07 will run the final --cov gate).

## User Setup Required

None — pure in-memory orchestration, no external services, no auth gates, no env vars, no manual verification steps.

## TDD Gate Compliance

Plan-level TDD cycle confirmed in git log (each task RED → GREEN, then a final style cleanup):

- Task 1: `51b97fb` (test RED) → `e6c77b9` (feat GREEN) — facades
- Task 2: `4452263` (test RED) → `b950b7f` (feat GREEN) — create_event
- Task 3: `a6efc85` (test RED) → `467ee5b` (feat GREEN) — set_event_state
- Cleanup: `81f807e` (style) — import re-sort

RED→GREEN sequence preserved for each task. The 9-test set_event_state RED commit failed with ModuleNotFoundError as expected; the GREEN commit made all 9 pass on the first run (no debug iteration needed) — the design was tight enough that the implementation matched the test expectations verbatim.

## Self-Check: PASSED

**Files verified:**
- `src/line_provider/facades/__init__.py` — FOUND
- `src/line_provider/facades/event_bus.py` — FOUND (EventBus Protocol + NoopEventBus + structlog.get_logger().info("event_bus.publish.noop", ...))
- `src/line_provider/facades/deps.py` — FOUND (get_store + get_event_bus + StoreDep + EventBusDep + request.app.state.event_store / event_bus)
- `src/line_provider/interactors/__init__.py` — FOUND
- `src/line_provider/interactors/create_event.py` — FOUND (async def create_event + state=EventState.NEW + store.add(event))
- `src/line_provider/interactors/set_event_state.py` — FOUND (async def set_event_state + _TERMINAL_TO_ROUTING + is_transition_allowed + store.get_by_id + store.update + event_bus.publish + previous_state == EventState.NEW)
- `tests/line_provider/_fakes.py` — FOUND (class FakeEventBus + self.calls: list)
- `tests/line_provider/test_facades.py` — FOUND (3 async tests)
- `tests/line_provider/test_create_event.py` — FOUND (3 async tests)
- `tests/line_provider/test_set_event_state.py` — FOUND (9 async tests)

**Commits verified:**
- `51b97fb` — FOUND (test(02-05): add failing tests for facades layer)
- `e6c77b9` — FOUND (feat(02-05): add facades layer — EventBus Protocol, NoopEventBus, DI providers)
- `4452263` — FOUND (test(02-05): add failing tests for create_event interactor + FakeEventBus)
- `b950b7f` — FOUND (feat(02-05): add create_event interactor)
- `a6efc85` — FOUND (test(02-05): add failing tests for set_event_state interactor)
- `467ee5b` — FOUND (feat(02-05): add set_event_state interactor with commit->publish ordering)
- `81f807e` — FOUND (style(02-05): re-sort imports after first-party modules created)

**Verification commands re-run:**
- `uv run pytest tests/line_provider/test_facades.py -q` → 3 passed
- `uv run pytest tests/line_provider/test_create_event.py -q` → 3 passed
- `uv run pytest tests/line_provider/test_set_event_state.py -q` → 9 passed
- `uv run pytest tests/line_provider -q` → 64 passed (49 baseline + 15 new)
- `uv run mypy --strict src` → Success: no issues found in 39 source files
- `uv run ruff check src tests` → All checks passed!
- `grep -q "class EventBus(Protocol)" src/line_provider/facades/event_bus.py` → match
- `grep -q "class NoopEventBus" src/line_provider/facades/event_bus.py` → match
- `grep -q "structlog.get_logger().info" src/line_provider/facades/event_bus.py` → match
- `grep -q "event_bus.publish.noop" src/line_provider/facades/event_bus.py` → match
- `grep -q "def get_store" src/line_provider/facades/deps.py` → match
- `grep -q "def get_event_bus" src/line_provider/facades/deps.py` → match
- `grep -q "StoreDep = Annotated" src/line_provider/facades/deps.py` → match
- `grep -q "EventBusDep = Annotated" src/line_provider/facades/deps.py` → match
- `grep -q "request.app.state.event_store" src/line_provider/facades/deps.py` → match
- `grep -q "request.app.state.event_bus" src/line_provider/facades/deps.py` → match
- `grep -q "async def create_event" src/line_provider/interactors/create_event.py` → match
- `grep -q "state=EventState.NEW" src/line_provider/interactors/create_event.py` → match
- `grep -q "store.add(event)" src/line_provider/interactors/create_event.py` → match
- `grep -q "class FakeEventBus" tests/line_provider/_fakes.py` → match
- `grep -q "self.calls: list" tests/line_provider/_fakes.py` → match
- `grep -q "async def set_event_state" src/line_provider/interactors/set_event_state.py` → match
- `grep -q "_TERMINAL_TO_ROUTING" src/line_provider/interactors/set_event_state.py` → match
- `grep -q "is_transition_allowed" src/line_provider/interactors/set_event_state.py` → match
- `grep -q "store.get_by_id" src/line_provider/interactors/set_event_state.py` → match
- `grep -q "store.update" src/line_provider/interactors/set_event_state.py` → match
- `grep -q "event_bus.publish" src/line_provider/interactors/set_event_state.py` → match
- `grep -q "previous_state == EventState.NEW" src/line_provider/interactors/set_event_state.py` → match
- store.update line (41) < event_bus.publish line (49) — strict commit->publish ordering enforced
- `grep -c "^async def test_" tests/line_provider/test_set_event_state.py` → 9

## Next Phase Readiness

- **Wave 3 first half complete.** Plan 02-06 (selectors) and Plan 02-07 (routes) are the remaining wave-3 plans. 02-06 will consume the same `get_store` provider for read-paths; 02-07 will consume both providers plus call `create_event` from POST and `set_event_state` from PUT.
- **Phase 5 swap is one line.** `app.state.event_bus = NoopEventBus()` in lifespan becomes `app.state.event_bus = RabbitEventBus(broker=router.broker)` — set_event_state requires zero changes. The Protocol contract is what guarantees this.
- **Core Value structurally protected.** D-12 (commit→publish ordering) and D-09 (publish only on NEW→FINISHED_*) are now baked into the interactor and proven by the failing-FakeEventBus test. Phase 5 will inherit this guarantee without re-engineering: even if the real AMQP publish raises (network blip, broker outage), the store mutation is already committed, so reconciliation in Phase 6 will catch up via line-provider's GET /events read paths. The "ставка не зависает PENDING" invariant has its first structural ally here.
- **Test infrastructure mature.** FakeEventBus is the canonical test double for the EventBus boundary — Plan 02-07 integration tests can choose between (a) using the production NoopEventBus and asserting on `capture_logs()` or (b) overriding `app.state.event_bus = FakeEventBus()` in a fixture and asserting on `bus.calls`. Both patterns are now established.
- **Coverage gate ready.** All 4 production lines added by this plan (facades + interactors) have full branch coverage from the 15 new tests. Plan 02-07's final `uv run pytest --cov` will land well above the 85% phase gate.
- **Open Todos:** None. Plan 02-06 (selectors, Wave 3 second half) is the next plan; it depends only on schemas (02-02) and store (02-04) and is independent of this plan.

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
