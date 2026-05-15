---
phase: 02-line-provider-domain
plan: 03
subsystem: line-provider/helpers/state-machine
tags: [line-provider, state-machine, helper, pure-function, wave-2]

requires:
  - phase: 02-line-provider-domain
    plan: 01
    provides: tests/line_provider conftest LifespanManager fixtures, coverage gate (src/line_provider, fail_under=85), REQUIREMENTS LP-02 UUID4
  - phase: 02-line-provider-domain
    plan: 02
    provides: EventState enum (NEW, FINISHED_WIN, FINISHED_LOSE) in src/line_provider/schemas/events.py
provides:
  - src/line_provider/helpers/state_machine.py — is_transition_allowed(current, new) -> bool, ALLOWED_TRANSITIONS frozenset, TransitionForbiddenError exception
  - tests/line_provider/test_state_machine.py — 12 unit tests (9 parametrized truth table + 3 standalone)
affects:
  - 02-05-interactors (consumes is_transition_allowed + TransitionForbiddenError in set_event_state interactor)
  - 02-07-routes (TransitionForbiddenError surfaced as HTTP 422 per D-08)

tech-stack:
  added: []
  patterns:
    - "Pure-function helper with module-level frozenset constant — O(1) lookup, immutable contract, zero DI. Mirrors src/config/time.py style (Excerpt F in 02-PATTERNS.md)."
    - "No-op transition (current == new) handled before frozenset lookup — implements D-09 (PUT with current state succeeds without publishing AMQP)."
    - "TransitionForbiddenError carries structured attributes (.current, .new) plus a human-readable message exact-formatted as 'state transition X->Y not allowed' (D-08 wording)."

key-files:
  created:
    - src/line_provider/helpers/state_machine.py
    - tests/line_provider/test_state_machine.py
  modified: []

key-decisions:
  - "Conditional ordering: `if current == new: return True` runs BEFORE frozenset lookup. Reason: explicit no-op handling matches D-09 semantics (no-op == allowed at validator level, publish-skip is interactor's concern) and avoids putting 3 self-loops into ALLOWED_TRANSITIONS — the constant stays minimal (exactly 2 forward transitions) so the test `len(ALLOWED_TRANSITIONS) == 2` is meaningful."
  - "Single import dependency — `from line_provider.schemas.events import EventState` is the only line above the body. No structlog, no DI, no config.time. State-machine is the smallest possible domain helper in the phase."

requirements-completed: [LP-08]

duration: 1min47s
completed: 2026-05-15
---

# Phase 02 Plan 03: line-provider State Machine Summary

**Pure-function state-machine helper for line-provider events — `is_transition_allowed(current, new) -> bool` + `ALLOWED_TRANSITIONS` frozenset + `TransitionForbiddenError`. No DI, no I/O, O(1) lookup. Plan 02-05 (set_event_state interactor) will import the function to decide between mutate-then-publish vs raise 422; Plan 02-07 (routes) will catch the error and surface HTTP 422 with `state transition X->Y not allowed`.**

## Performance

- **Duration:** ~1 min 47 s (2 tasks, autonomous, no checkpoints)
- **Started:** 2026-05-15T08:24:26Z
- **Completed:** 2026-05-15T08:26:13Z
- **Tasks:** 2 / 2
- **Files created:** 2 (1 production + 1 test)
- **Tests added:** 12 (9 parametrized truth-table cases + 3 standalone)
- **Full suite after this plan:** 38 passed (26 baseline + 12 new)

## Accomplishments

- `src/line_provider/helpers/state_machine.py` exports three names: `ALLOWED_TRANSITIONS` (frozenset of exactly two tuples — `(NEW, FINISHED_WIN)` and `(NEW, FINISHED_LOSE)`), `TransitionForbiddenError` (Exception subclass that takes `(current, new)` and stores them as `.current` / `.new` plus formats `str(err) == "state transition X->Y not allowed"`), and `is_transition_allowed(current, new) -> bool` (returns True for no-op self-loops and for the two forward transitions, False for every other pair). No structlog, no FastAPI, no config — only the EventState enum from `line_provider.schemas.events`.
- `tests/line_provider/test_state_machine.py` covers all three exported names: the parametrized truth-table walks every cell of the 3x3 cartesian product (9 cases — 5 True and 4 False), a separate test asserts `ALLOWED_TRANSITIONS` is a frozenset of size 2 containing the two forward tuples (immutability + content), a third test constructs `TransitionForbiddenError(FINISHED_WIN, NEW)` and asserts `.current`, `.new`, and that `str(err)` contains `"FINISHED_WIN"`, `"NEW"`, and `"not allowed"`, and a fourth test uses `pytest.raises(TransitionForbiddenError)` to confirm raisability. All 12 tests are synchronous (pure function, no coroutines) and live under `asyncio_mode = "auto"` without warnings.
- Module docstring on the test file cites LP-08, D-08, D-09 for grep-traceability per P1 convention (Excerpt H in 02-PATTERNS.md).

## Task Commits

1. **Task 1: helpers/state_machine.py (pure function + frozenset + TransitionForbiddenError)** — `c51d333` (feat)
2. **Task 2: tests/line_provider/test_state_machine.py (parametrized 9-case truth table + 3 standalone)** — `5d5523a` (test)

## Files Created/Modified

- `src/line_provider/helpers/state_machine.py` — `ALLOWED_TRANSITIONS: frozenset[tuple[EventState, EventState]]` (2 entries), `class TransitionForbiddenError(Exception)` with `.current`/`.new` attributes and `f"state transition {current.value}->{new.value} not allowed"` message, `def is_transition_allowed(current: EventState, new: EventState) -> bool` (no-op short-circuit + frozenset membership test).
- `tests/line_provider/test_state_machine.py` — 6 imports, 1 parametrize fixture (9 cases), 4 test functions: `test_is_transition_allowed_table` (9 truth-table cells via parametrize), `test_allowed_transitions_is_frozenset_with_two_entries`, `test_transition_forbidden_error_carries_states_and_message`, `test_transition_forbidden_error_is_exception_subclass`.

## Decisions Made

- **No-op short-circuit comes before frozenset lookup.** `if current == new: return True` then `return (current, new) in ALLOWED_TRANSITIONS`. Reason: keeps the public frozenset minimal — it lists only forward transitions (D-08), not self-loops. Test `len(ALLOWED_TRANSITIONS) == 2` is therefore semantically meaningful ("exactly two forward transitions"). Alternative — inlining 3 self-loops into the frozenset — was rejected because it conflates "allowed forward transitions" with "no-op identity" and makes the truth-table test less precise.
- **One-import file.** Only `from line_provider.schemas.events import EventState`. No structlog (the helper does not log — Plan 02-05 interactor will log when it raises the error), no `config.time` (no time dependence), no facades. This is the smallest possible domain helper.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Style] Removed double blank line between imports**
- **Found during:** Task 1 ruff check
- **Issue:** `ruff` I001 flagged the import block as un-sorted/un-formatted because of a double blank line between `from line_provider.schemas.events import EventState` and `ALLOWED_TRANSITIONS = ...`. The plan's example code had two blank lines; ruff (pep8 standard) wants one between top-level imports and module body in a small file.
- **Fix:** Removed the extra blank line.
- **Files modified:** `src/line_provider/helpers/state_machine.py`
- **Commit:** Folded into Task 1 (`c51d333`).

**2. [Pre-commit auto-format] `ruff format` collapsed multi-line `super().__init__(...)` call**
- **Found during:** Task 1 commit (ruff format)
- **Issue:** `ruff format` rewrote the multi-line `super().__init__(\n    f"state transition ..."\n)` into a single-line form because it fits within the 100-char limit. Pure cosmetic.
- **Fix:** Re-staged the formatter's output.
- **Files modified:** `src/line_provider/helpers/state_machine.py`
- **Commit:** Folded into Task 1 (`c51d333`).

**3. [Pre-commit auto-format] `ruff format` collapsed parametrize signature**
- **Found during:** Task 2 commit (ruff format)
- **Issue:** `ruff format` collapsed `def test_is_transition_allowed_table(\n    current: EventState, new: EventState, allowed: bool\n) -> None:` into single-line form (fits within 100-char limit).
- **Fix:** Re-staged the formatter's output.
- **Files modified:** `tests/line_provider/test_state_machine.py`
- **Commit:** Folded into Task 2 (`5d5523a`).

## Threat Model Compliance

All four threats from the plan's `<threat_model>` addressed:

- **T-03-01 (Tampering / ALLOWED_TRANSITIONS mutated at runtime):** mitigated. `ALLOWED_TRANSITIONS` is a `frozenset[tuple[EventState, EventState]]` declared as a module-level constant. Frozenset is immutable by Python language guarantee. Test `test_allowed_transitions_is_frozenset_with_two_entries` asserts `isinstance(ALLOWED_TRANSITIONS, frozenset)` and `len(...) == 2` — any future PR that swaps frozenset for set or adds entries fails CI.
- **T-03-02 (Repudiation / 422 message does not reflect actual transition):** mitigated. `TransitionForbiddenError.__init__` formats `f"state transition {current.value}->{new.value} not allowed"` literally — both enum values appear in the message. Test `test_transition_forbidden_error_carries_states_and_message` asserts both `FINISHED_WIN` and `NEW` substrings are present plus the verb `"not allowed"`.
- **T-03-03 (Information Disclosure / 422 leaks internal state):** accepted per plan. Message contains only public enum names (NEW / FINISHED_WIN / FINISHED_LOSE), no PII, no internals.
- **T-03-04 (DoS / infinite validation loop):** accepted per plan. Pure function, O(1) lookup, no recursion, no I/O.

## Threat Flags

None — no new security-relevant surface introduced. State-machine is a pure in-memory predicate with no network, no auth, no schema mutation outside `EventState`.

## Known Stubs

None — `is_transition_allowed` is fully wired and ready for Plan 02-05 (set_event_state interactor) to consume without modification. `TransitionForbiddenError` is ready for Plan 02-07 (routes) to catch and translate to HTTP 422.

## Issues Encountered

None beyond the three auto-fixes above (all pure cosmetic, no semantic change). All verify blocks (`uv run python -c "..."`, `uv run mypy --strict`, `uv run ruff check`, `uv run pytest -q`) passed on first or second attempt (second attempt only because of `ruff format` collapsing line breaks during pre-commit).

## User Setup Required

None — no external service configuration, no auth gates, no manual verification steps.

## Self-Check: PASSED

**Files verified:**
- `src/line_provider/helpers/state_machine.py` — FOUND (contains `ALLOWED_TRANSITIONS`, `TransitionForbiddenError`, `is_transition_allowed`, single import of `EventState`)
- `tests/line_provider/test_state_machine.py` — FOUND (contains 1 `pytest.mark.parametrize`, 4 test functions, REQ-ID `LP-08` cited in module docstring + test docstrings)

**Commits verified:**
- `c51d333` — FOUND (feat(02-03): add state-machine helper for line-provider events)
- `5d5523a` — FOUND (test(02-03): add unit tests for line-provider state-machine helper)

**Verification commands re-run:**
- `uv run pytest tests/line_provider/test_state_machine.py -q` → 12 passed
- `uv run pytest -q` → 38 passed (26 baseline + 12 new)
- `uv run mypy --strict src/line_provider/helpers/state_machine.py tests/line_provider/test_state_machine.py` → Success: no issues found in 2 source files
- `uv run ruff check src/line_provider/helpers tests/line_provider/test_state_machine.py` → All checks passed!
- `grep -c "^# " src/line_provider/helpers/state_machine.py` → 0 (no comments per project hard rule)
- `grep -q "ALLOWED_TRANSITIONS: frozenset" src/line_provider/helpers/state_machine.py` → match
- `grep -q "class TransitionForbiddenError" src/line_provider/helpers/state_machine.py` → match
- `grep -q "def is_transition_allowed" src/line_provider/helpers/state_machine.py` → match
- `grep -q "from line_provider.schemas.events import EventState" src/line_provider/helpers/state_machine.py` → match
- `grep -c "EventState.NEW, EventState.FINISHED" src/line_provider/helpers/state_machine.py` → 2 (exactly two forward transitions in frozenset)
- `grep -c "pytest.mark.parametrize" tests/line_provider/test_state_machine.py` → 1
- `grep -c "(EventState.NEW, EventState." tests/line_provider/test_state_machine.py` → 5 (>=3 required: NEW→NEW, NEW→WIN, NEW→LOSE + 2 more)
- `grep -c "(EventState.FINISHED" tests/line_provider/test_state_machine.py` → 8 (>=6 required: FIN_WIN x 3 + FIN_LOSE x 3 + 2 more)
- `grep -q "LP-08" tests/line_provider/test_state_machine.py` → match (REQ-ID traceability)

## Next Phase Readiness

- **Wave 2 (Plan 02-03 state-machine) complete.** Plan 02-05 (interactors) is unblocked on its `02-03` dependency — `set_event_state.py` will `from line_provider.helpers.state_machine import is_transition_allowed, TransitionForbiddenError` and use them verbatim, no further state-machine work needed downstream.
- **Plan 02-04 (in-memory store) is independent.** Both 02-03 and 02-04 had `depends_on: [01, 02]` and no cross-file conflicts — 02-04 can run in parallel or sequentially without coordination.
- **D-08 / D-09 contract locked.** The exact message format (`state transition X->Y not allowed`) is now part of the production interface and is tested. Plan 02-07 integration tests can assert HTTP 422 body contains that exact string without further re-engineering.
- **Threat T-03-01 closed by test invariant.** Any future change that demotes `ALLOWED_TRANSITIONS` from frozenset to set or alters its size triggers `test_allowed_transitions_is_frozenset_with_two_entries` — schema drift is mechanically prevented.
- **No new dependencies** — Plan 02-03 introduced zero packages. uv.lock unchanged.

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
