---
phase: 02-line-provider-domain
plan: 02
subsystem: line-provider/schemas
tags: [line-provider, schemas, pydantic, decimal, uuid, aware-datetime, wave-1]

requires:
  - phase: 02-line-provider-domain
    plan: 01
    provides: tests/line_provider/conftest.py lifespan-aware fixtures, REQUIREMENTS LP-02 UUID4 sync, coverage gate (src/line_provider, fail_under=85)
provides:
  - src/line_provider/schemas/events.py — EventState, EventCreate, EventUpdate, Event (frozen), EventRead, Coefficient, FutureDeadline
  - src/line_provider/schemas/messages.py — EventTerminalState, EventFinishedMessage (frozen, schema_version=1, extra=forbid)
  - src/line_provider/helpers/money.py — quantize_coefficient(Decimal) -> Decimal (2dp, ROUND_HALF_UP)
  - tests/line_provider/test_schemas.py — 22 unit tests across 6 classes (Quantize, EventCreate, EventUpdate, Event, EventRead, EventFinishedMessage)
affects:
  - 02-03-state-machine (consumes EventState)
  - 02-04-store (consumes Event, EventCreate)
  - 02-05-interactors (consumes EventCreate, EventUpdate, Event, EventFinishedMessage, EventTerminalState)
  - 02-06-selectors (consumes Event, EventRead)
  - 02-07-routes (consumes EventCreate, EventUpdate, EventRead)

tech-stack:
  added: []
  patterns:
    - "Quantize-on-input via Annotated[Decimal, Field(...), AfterValidator(_quantize)] — fixes Pitfall 3 (Pydantic v2 decimal_places=2 validates upper bound only, '10' would round-trip as '10' not '10.00'). Helper is one source of truth (helpers/money.quantize_coefficient) shared by EventCreate.coefficient and EventUpdate.coefficient."
    - "(str, Enum) instead of StrEnum for Python 3.10 compatibility — StrEnum landed in 3.11; the plan's example code assumed 3.11 but the project pins 3.10.20 (CLAUDE.md). Behaviourally equivalent for Pydantic — both accept string inputs and serialise as strings."
    - "FutureDeadline = Annotated[AwareDatetime, AfterValidator(_deadline_in_future)] applied only to EventCreate.deadline; EventUpdate / Event / EventRead use bare AwareDatetime (D-07: PUT and stored events allow past deadlines)."
    - "Defence-in-depth on AMQP boundary: EventFinishedMessage uses frozen=True + extra='forbid' + schema_version (Field(ge=1), default=1) to make schema drift refusal explicit at the consumer (P5)."

key-files:
  created:
    - src/line_provider/schemas/__init__.py
    - src/line_provider/schemas/events.py
    - src/line_provider/schemas/messages.py
    - src/line_provider/helpers/__init__.py
    - src/line_provider/helpers/money.py
    - tests/line_provider/test_schemas.py
  modified: []

key-decisions:
  - "Replaced StrEnum with (str, Enum) base class because the project targets Python 3.10.20 — StrEnum requires 3.11+. Behaviour identical for Pydantic v2 serialisation and equality comparisons (covered by test_terminal_state_values_match_event_state). Tracked as Rule 1 deviation."
  - "quantize_coefficient lives in helpers/money.py (not in schemas/events.py) so that future bet-amount schemas in bet-maker can reuse the same 2dp normalisation without importing line-provider's schema module."
  - "AfterValidator(_quantize) sits AFTER Pydantic's Field(decimal_places=2) gate — so '10.123' is rejected as >2dp BEFORE the helper runs, and '10' is accepted then quantised to '10.00'. Both behaviours verified by tests."

requirements-completed: [LP-02, LP-04]
requirements-partial: [LP-08]

duration: 3min30s
completed: 2026-05-15
---

# Phase 02 Plan 02: line-provider Schemas Summary

**Pydantic v2 schema layer for line-provider — EventState enum, EventCreate/EventUpdate/Event/EventRead HTTP and domain models with quantize-on-input Decimal normalisation, plus the AMQP-side EventFinishedMessage (frozen + schema_version + extra=forbid) ready to be consumed without changes by Plan 02-05 (interactors) and Phase 5 (RabbitEventBus).**

## Performance

- **Duration:** ~3 min 30 s (3 tasks, autonomous, no checkpoints)
- **Started:** 2026-05-15T08:16:10Z
- **Completed:** 2026-05-15T08:19:33Z
- **Tasks:** 3 / 3
- **Files created:** 6 (4 production + 1 test + 2 empty package markers)
- **Tests added:** 22 across 6 classes
- **Full suite after this plan:** 26 passed (4 P1 baseline + 22 new)

## Accomplishments

- `src/line_provider/schemas/events.py` exports `EventState` (3 members), `EventCreate`, `EventUpdate`, `Event` (frozen + extra=forbid), `EventRead`, and the two reusable annotated types `Coefficient` (Decimal, gt=0, max_digits=8, decimal_places=2, AfterValidator quantises to 2dp) and `FutureDeadline` (AwareDatetime with AfterValidator ensuring `deadline > utc_now()`). All four models declare `model_config = ConfigDict(extra="forbid")`; `Event` adds `frozen=True` so setattr raises `ValidationError`.
- `src/line_provider/schemas/messages.py` exports `EventTerminalState` (2 members, subset of EventState) and `EventFinishedMessage` (`frozen=True`, `extra="forbid"`, `schema_version: int = 1` with `Field(ge=1)`, `event_id: UUID`, `new_state: EventTerminalState`, `coefficient: Decimal(gt=0, max_digits=8, decimal_places=2)`, `occurred_at: AwareDatetime`, `correlation_id: str`). Schema is the contract Plan 02-05 will publish and Phase 5 RabbitEventBus / Phase 3 bet-maker consumer will deserialise — no further schema edits required across boundaries.
- `src/line_provider/helpers/money.py` contains the single `quantize_coefficient(value: Decimal) -> Decimal` helper backed by `Decimal("0.01")` and `ROUND_HALF_UP`. Single source of truth for 2dp normalisation, reusable by bet-maker amount schemas in P3 / P4.
- `tests/line_provider/test_schemas.py` covers every validator branch: quantize (pad, keep, round), EventCreate happy path + 8 rejection cases (non-UUID, zero, negative, >2dp, naive deadline, past deadline, extra field) + 1 quantize round-trip, EventUpdate (happy path, past-deadline acceptance per D-07, event_id rejection per D-04), Event frozen, EventRead cross-model conversion, and the full EventFinishedMessage matrix (happy path, frozen, schema_version=0 rejection, extra-field rejection, EventTerminalState ↔ EventState value parity). All 22 tests are sync (Pydantic is sync); pytest-asyncio asyncio_mode=auto does not interfere.

## Task Commits

1. **Task 1: schemas/events.py + helpers/money.py + package markers** — `750b614` (feat)
2. **Task 2: schemas/messages.py (EventFinishedMessage + EventTerminalState)** — `64b0d1f` (feat)
3. **Task 3: Unit tests — tests/line_provider/test_schemas.py** — `e301d50` (test)

## Files Created/Modified

- `src/line_provider/schemas/__init__.py` — empty package marker
- `src/line_provider/schemas/events.py` — EventState (3 members), Coefficient + FutureDeadline annotated types, EventCreate, EventUpdate, Event (frozen), EventRead; imports `from config.time import utc_now` and `from line_provider.helpers.money import quantize_coefficient` (single source of truth across input validators)
- `src/line_provider/schemas/messages.py` — EventTerminalState (2 members), EventFinishedMessage with frozen + extra=forbid + schema_version=1 + UUID event_id
- `src/line_provider/helpers/__init__.py` — empty package marker
- `src/line_provider/helpers/money.py` — quantize_coefficient helper (Decimal → 2dp, ROUND_HALF_UP)
- `tests/line_provider/test_schemas.py` — 22 unit tests across 6 classes, all REQ-IDs cited in docstrings (LP-02, LP-04, LP-08, D-04, D-07, D-13, D-17 — 23 references via grep)

## Decisions Made

- **`StrEnum` → `(str, Enum)`** — Plan example code used `from enum import StrEnum`, but `StrEnum` is a Python 3.11+ addition; the project pins 3.10.20 (`.python-version`, CLAUDE.md tech stack). Replaced with the canonical `class EventState(str, Enum)` idiom — equivalent for Pydantic v2 (string serialisation, equality with raw strings) and for the cross-enum value comparison test `EventTerminalState.FINISHED_WIN.value == EventState.FINISHED_WIN.value`. No behaviour change.
- **Cross-file helper location** — `quantize_coefficient` placed in `src/line_provider/helpers/money.py` rather than inlined in `schemas/events.py`. Reason: bet-maker will need exactly the same 2dp normalisation for `bet.amount` in P3/P4; keeping the helper in its own module (and `helpers/__init__.py` as a future-proof package marker) avoids a forward import of schemas from bet-maker.
- **AfterValidator order** — `Coefficient = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2), AfterValidator(_quantize)]`. Pydantic v2 applies Field constraints first; AfterValidator runs only on values that already passed gt=0 and ≤2dp. Outcome: `Decimal("10.123")` is rejected (>2dp) BEFORE quantize runs, but `Decimal("10")` (=0dp, satisfies ≤2dp) is then quantised to `Decimal("10.00")`. Both branches covered by tests (`test_rejects_more_than_two_decimal_places`, `test_quantizes_int_string_input`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Replaced `StrEnum` with `(str, Enum)` for Python 3.10 compatibility**
- **Found during:** Task 1 verify step (`uv run python -c "from line_provider.schemas.events import EventState..."`)
- **Issue:** `ImportError: cannot import name 'StrEnum' from 'enum'`. The plan's example code used `from enum import StrEnum`, but `StrEnum` was added in Python 3.11. CLAUDE.md tech stack and `.python-version` both pin 3.10.20.
- **Fix:** `from enum import Enum` and `class EventState(str, Enum):` / `class EventTerminalState(str, Enum):`. Behaviour identical for Pydantic v2 (string-valued enum members, JSON serialised as strings, `.value` equality works for the cross-enum test).
- **Files modified:** `src/line_provider/schemas/events.py`, `src/line_provider/schemas/messages.py`
- **Commit:** Folded into Task 1 (`750b614`) and Task 2 (`64b0d1f`) commits.

**2. [Rule 1 — Bug] Rephrased docstring in `helpers/money.py` to satisfy ruff RUF002 (Cyrillic-Latin homoglyph)**
- **Found during:** Task 1 ruff check
- **Issue:** Docstring contained `ТЗ` (Cyrillic T+Z) inside an otherwise English sentence — `ruff` RUF002 flagged ambiguous characters.
- **Fix:** Rephrased to fully English: `«ТЗ requires «ровно 2 знака»;»` → `«The spec requires exactly two decimal places;»`. No semantic change.
- **Files modified:** `src/line_provider/helpers/money.py`
- **Commit:** Folded into Task 1 (`750b614`).

**3. [Rule 1 — Bug] Shortened one test docstring to satisfy ruff E501 (line >100)**
- **Found during:** Task 3 ruff check
- **Issue:** `test_accepts_past_deadline` docstring was 101 chars long.
- **Fix:** Rephrased from `«…deadline pinned once to avoid clock drift…»` → `«…pinned once, no clock drift…»`. No semantic change.
- **Files modified:** `tests/line_provider/test_schemas.py`
- **Commit:** Folded into Task 3 (`e301d50`).

**4. [Pre-commit auto-format] `ruff format` reformatted three `model_validate({...})` blocks**
- **Found during:** Task 3 commit (pre-commit hook)
- **Issue:** `ruff format` rewrote inline dict literals into multi-line bodies for `EventCreate.model_validate({...})`, `EventUpdate.model_validate({...})`, and `EventFinishedMessage.model_validate({...})`.
- **Fix:** Re-staged the formatter's output and re-committed. No semantic change.
- **Files modified:** `tests/line_provider/test_schemas.py`
- **Commit:** Folded into Task 3 (`e301d50`).

## Threat Surface Scan

No new surface beyond the plan's `<threat_model>` (T-02-01..T-02-07 all addressed):

- T-02-01 (Tampering / EventCreate body): `extra="forbid"` on all four schemas + AwareDatetime + FutureDeadline + Coefficient(gt=0, ≤2dp, quantize) all in place.
- T-02-02 (Information Disclosure / 422 detail): accepted per plan; FastAPI default Pydantic-error format used.
- T-02-03 (DoS / unbounded coefficient): `max_digits=8` caps Decimal at 999999.99.
- T-02-04 (Repudiation / EventFinishedMessage schema drift): schema_version=1 (Field(ge=1)) + extra="forbid" + frozen=True.
- T-02-05 (Spoofing / naive datetime): AwareDatetime rejects naive everywhere; explicit test `test_rejects_naive_deadline`.
- T-02-06 (Information Disclosure / Decimal serialisation): quantize-on-input ensures `Decimal("10")` round-trips as `Decimal("10.00")`; tested.
- T-02-07 (Authorization): accepted out-of-scope per ТЗ.

## Known Stubs

None. All schemas are fully wired with their validators and are consumed-ready by downstream P2 plans.

## Issues Encountered

None beyond the four auto-fixed deviations above. All happened on the first verify cycle of their respective tasks; no architectural changes (Rule 4) required.

## User Setup Required

None — no external service configuration, no auth gates, no manual verification steps.

## Self-Check: PASSED

**Files verified:**
- `src/line_provider/schemas/__init__.py` — FOUND
- `src/line_provider/schemas/events.py` — FOUND (EventState, Coefficient, FutureDeadline, EventCreate, EventUpdate, Event, EventRead)
- `src/line_provider/schemas/messages.py` — FOUND (EventTerminalState, EventFinishedMessage with frozen + schema_version + UUID event_id)
- `src/line_provider/helpers/__init__.py` — FOUND
- `src/line_provider/helpers/money.py` — FOUND (quantize_coefficient + _TWO_PLACES)
- `tests/line_provider/test_schemas.py` — FOUND (6 test classes, 22 tests, 23 REQ-ID references)

**Commits verified:**
- `750b614` — FOUND (feat(02-02): add line-provider events schemas and coefficient helper)
- `64b0d1f` — FOUND (feat(02-02): add EventFinishedMessage AMQP schema and EventTerminalState)
- `e301d50` — FOUND (test(02-02): add unit tests for line-provider schemas and money helper)

**Verification commands re-run:**
- `uv run pytest tests/line_provider/test_schemas.py -q` → 22 passed
- `uv run pytest -q` → 26 passed (2 P1 health + 2 new test pass count + ... actual: 4 P1 + 22 new = 26 ✓)
- `uv run mypy --strict src/line_provider/schemas src/line_provider/helpers tests/line_provider/test_schemas.py` → Success: no issues found in 6 source files
- `uv run ruff check src/line_provider/schemas src/line_provider/helpers tests/line_provider/test_schemas.py` → All checks passed!
- `grep -c "class EventState" src/line_provider/schemas/events.py` → 1
- `grep -c "frozen=True" src/line_provider/schemas/events.py` → 1
- `grep -c 'extra="forbid"' src/line_provider/schemas/events.py` → 4
- `grep -c "class EventFinishedMessage" src/line_provider/schemas/messages.py` → 1
- `grep -c "event_id: UUID" src/line_provider/schemas/messages.py` → 1
- `grep -c "^class Test" tests/line_provider/test_schemas.py` → 6

## Next Phase Readiness

- **Wave 1 (Plan 02-02 schemas) complete.** Plan 02-03 (state-machine helper, pure function) and Plan 02-04 (in-memory store) are unblocked. They both `depends_on: [01, 02]` and can run in parallel — no cross-file conflicts between them.
- **Schema layer is the single source of truth for HTTP and AMQP contracts.** Plan 02-05 (interactors) will import `EventCreate`, `EventUpdate`, `Event`, `EventState`, `EventFinishedMessage`, `EventTerminalState` directly. Plan 02-07 (routes) will import `EventCreate`, `EventUpdate`, `EventRead`. Phase 5 (RabbitEventBus) will reuse `EventFinishedMessage` verbatim.
- **Pitfall 3 (Decimal serialisation) closed.** `quantize_coefficient` guarantees that any `Decimal` round-tripping through `Coefficient` lands at exactly 2dp; the AMQP `coefficient` field will inherit this normalised value (Plan 02-05 builds `EventFinishedMessage` from `Event.coefficient`, which already passed through Coefficient).
- **Coverage gate active.** Plan 02-07 final task will run `uv run pytest --cov` against `src/line_provider`; schemas + helpers are well-covered by the 22 new tests (every branch of every validator is hit at least once).

---
*Phase: 02-line-provider-domain*
*Completed: 2026-05-15*
