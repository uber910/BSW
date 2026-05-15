---
phase: 03-bet-maker-domain-db
plan: 03
subsystem: bet-maker/schemas + bet-maker/helpers
tags: [bet-maker, schemas, pydantic-v2, decimal-validation, helpers, wave-1]

requires:
  - phase: 03-bet-maker-domain-db
    provides: "Plan 03-02: Wave 0 test scaffolding + 11 stub files"

provides:
  - "src/bet_maker/schemas/events.py: EventState(str, Enum) with 3 members — intentional D-12 duplication"
  - "src/bet_maker/schemas/bets.py: BetStatus, Amount Annotated alias, BetCreate, BetRead"
  - "src/bet_maker/helpers/money.py: quantize_amount(Decimal) -> Decimal ROUND_HALF_UP 2dp"
  - "src/bet_maker/helpers/status.py: event_state_to_bet_status NotImplementedError stub for P5"
  - "tests/bet_maker/test_schemas.py: 20 tests in 6 classes replacing Wave 0 stub"

affects: [03-04, 03-06, 03-07, 03-08]

tech-stack:
  added: []
  patterns:
    - "Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2), AfterValidator(quantize_amount)] pattern"
    - "BetRead.model_config = ConfigDict(extra='forbid', from_attributes=True) for ORM bridge"
    - "EventState intentional duplication pattern per D-12 (service-boundary isolation)"

key-files:
  created:
    - "src/bet_maker/schemas/__init__.py"
    - "src/bet_maker/schemas/events.py"
    - "src/bet_maker/schemas/bets.py"
    - "src/bet_maker/helpers/__init__.py"
    - "src/bet_maker/helpers/money.py"
    - "src/bet_maker/helpers/status.py"
  modified:
    - "tests/bet_maker/test_schemas.py"

decisions:
  - "status.py imports from schemas/ (one-directional helpers -> schemas dependency) — clean layering"
  - "LpEventState import at module top-level to satisfy ruff PLC0415 (no inline imports in test methods)"
  - "datetime.now() at top-level import instead of __import__() inline — cleaner code per ruff conventions"

metrics:
  duration: "~3.5 min"
  completed: "2026-05-15"
  tasks: 3
  files: 7
---

# Phase 3 Plan 03: Pydantic Schemas + Helpers Summary

**Bet-maker domain primitives — EventState(str,Enum) D-12 duplication, BetStatus, Amount Annotated Decimal (gt=0, max_digits=12, decimal_places=2, AfterValidator quantize_amount ROUND_HALF_UP), BetCreate+BetRead with extra='forbid', quantize_amount helper, status stub, 20 unit tests**

## Performance

- **Duration:** ~3.5 min
- **Started:** 2026-05-15T15:08:28Z
- **Completed:** 2026-05-15T15:11:58Z
- **Tasks:** 3
- **Files modified:** 7 (6 created + 1 replaced stub)

## Accomplishments

- `src/bet_maker/helpers/money.py` — `quantize_amount(Decimal) -> Decimal` with `_TWO_PLACES = Decimal("0.01")` + `ROUND_HALF_UP`; mirrors `line_provider/helpers/money.py` pattern exactly
- `src/bet_maker/helpers/status.py` — `event_state_to_bet_status` stub raises `NotImplementedError("Implemented in P5 ...")` per D-30; SOC pre-wire for Phase 5
- `src/bet_maker/schemas/events.py` — `EventState(str, Enum)` with `NEW / FINISHED_WIN / FINISHED_LOSE` — intentional duplication per D-12 (service-boundary isolation); value-parity enforced by test
- `src/bet_maker/schemas/bets.py` — `BetStatus(str, Enum)` with `PENDING/WON/LOST`; `Amount = Annotated[Decimal, Field(gt=Decimal("0"), max_digits=12, decimal_places=2), AfterValidator(quantize_amount)]`; `BetCreate(extra='forbid')`; `BetRead(extra='forbid', from_attributes=True)`
- `tests/bet_maker/test_schemas.py` — Wave 0 stub replaced with 20 tests in 6 classes; REQ-ID docstrings on all methods; mypy strict + ruff clean
- Full suite: 117 passed (97 baseline + 20 new), 1 deprecation warning (pre-existing FastAPI HTTP_422 — not this plan)

## Task Commits

1. **Task 1: helpers/money.py + helpers/status.py + __init__.py** — `789452e` (feat)
2. **Task 2: schemas/events.py + schemas/bets.py + __init__.py** — `76e027f` (feat)
3. **Task 3: tests/bet_maker/test_schemas.py — replace Wave 0 stub** — `1c2ceca` (feat)

## Files Created/Modified

| File | Change | Notes |
|------|--------|-------|
| `src/bet_maker/helpers/__init__.py` | created | Package marker (empty) |
| `src/bet_maker/helpers/money.py` | created | quantize_amount ROUND_HALF_UP 2dp |
| `src/bet_maker/helpers/status.py` | created | event_state_to_bet_status NotImplementedError stub |
| `src/bet_maker/schemas/__init__.py` | created | Package marker (empty) |
| `src/bet_maker/schemas/events.py` | created | EventState(str, Enum) D-12 duplication |
| `src/bet_maker/schemas/bets.py` | created | BetStatus, Amount, BetCreate, BetRead |
| `tests/bet_maker/test_schemas.py` | replaced | Wave 0 stub → 20 real tests in 6 classes |

## Test Results

```
uv run pytest tests/bet_maker/test_schemas.py -q --no-cov
20 passed in 0.04s

uv run pytest -q --no-cov
117 passed, 1 warning in 0.39s
```

Test distribution (6 classes, 20 tests total):
- `TestQuantize` — 3 tests (pad_zeros, keep_two_places, round_half_up)
- `TestBetCreate` — 9 tests (happy_path_quantizes, string_input_quantizes, three_decimal_places_rejected, zero_rejected, negative_rejected, invalid_uuid_rejected, extra_field_rejected, missing_amount_rejected, oversized_amount_rejected)
- `TestBetRead` — 2 tests (from_attributes_accepts_orm_like, decimal_serializes_as_string)
- `TestEnums` — 3 tests (eventstate_has_three_members, eventstate_value_parity_with_line_provider, betstatus_has_three_members)
- `TestStatusStub` — 1 test (raises_for_p5)
- `TestExtraForbid` — 2 tests (betcreate_extra_forbid, betread_extra_forbid)

EventState value-parity test imports `from line_provider.schemas.events import EventState as LpEventState` at module top-level; import succeeded, test passed.

## Decisions Made

- **status.py helper-to-schemas dependency**: `helpers/status.py` imports from `schemas/bets.py` and `schemas/events.py` — this is the correct one-directional layering (helpers depend on schemas, not vice versa). Created after schemas to avoid pre-commit mypy failure on missing modules.
- **Commit order forced by mypy**: Task 1 (helpers) could not be committed standalone before Task 2 (schemas) because pre-commit mypy runs on entire `src/` and `status.py` imports from `schemas/` which didn't exist yet. Solution: create schemas files first, then commit Task 1 and Task 2 separately (schemas staged but uncommitted during Task 1 commit pre-check via stashing).
- **Top-level imports in test file**: ruff PLC0415 requires `import` at top-level; moved `import json`, `from datetime import datetime`, and `from line_provider.schemas.events import EventState as LpEventState` to module top-level (deviation from plan template which used inline imports in test methods).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-commit mypy failure on helpers/status.py before schemas created**
- **Found during:** Task 1 commit attempt
- **Issue:** `status.py` imports `BetStatus` and `EventState` from `schemas/`, which didn't exist yet; pre-commit mypy `import-not-found` blocked commit
- **Fix:** Created schemas/ files (Task 2) before committing Task 1; committed in order Task 1 → Task 2 (both already ready, just staged separately)
- **Files modified:** No extra files; commit order adjusted
- **Impact:** Zero semantic change; plan executed correctly

**2. [Rule 1 - Bug] ruff PLC0415 on inline imports in test methods**
- **Found during:** Task 3 ruff check
- **Issue:** Plan template had `import json` and `from line_provider... import ...` inside test method bodies; ruff rule PLC0415 forbids non-top-level imports
- **Fix:** Moved all imports to module top-level; also extracted `__import__("datetime").datetime.now()` to use `from datetime import datetime` at top and `datetime.now()` inline
- **Files modified:** `tests/bet_maker/test_schemas.py`
- **Commit:** `1c2ceca`

## Known Stubs

- `src/bet_maker/helpers/status.py` — `event_state_to_bet_status` raises `NotImplementedError` intentionally per D-30; will be implemented in Plan 03-07/Phase 5. This is a designed stub, not a defect.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes at trust boundaries introduced. All files are pure domain/schema layer with no I/O. T-03-1 and T-03-3 mitigations verified by tests (decimal_max_places, greater_than, extra_forbidden).

## Self-Check: PASSED

- src/bet_maker/helpers/__init__.py: FOUND
- src/bet_maker/helpers/money.py: FOUND
- src/bet_maker/helpers/status.py: FOUND
- src/bet_maker/schemas/__init__.py: FOUND
- src/bet_maker/schemas/events.py: FOUND
- src/bet_maker/schemas/bets.py: FOUND
- tests/bet_maker/test_schemas.py: FOUND (20 tests, 6 classes)
- 789452e (feat 03-03 helpers): FOUND in git log
- 76e027f (feat 03-03 schemas): FOUND in git log
- 1c2ceca (feat 03-03 test suite): FOUND in git log

---
*Phase: 03-bet-maker-domain-db*
*Completed: 2026-05-15*
