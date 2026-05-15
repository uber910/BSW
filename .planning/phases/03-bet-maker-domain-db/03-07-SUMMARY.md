---
phase: 03-bet-maker-domain-db
plan: "07"
subsystem: bet-maker
tags: [bet-maker, interactor, selectors, business-logic, wave-4]
dependency_graph:
  requires:
    - 03-06 (AsyncUnitOfWork + BetRepository + EventLookup + DI providers)
    - 03-05 (create_engine_and_sessionmaker)
    - 03-04 (Bet ORM model + Alembic migration)
    - 03-03 (BetCreate / BetRead / BetStatus / quantize_amount)
  provides:
    - place_bet interactor (write path: validate -> insert -> BetRead)
    - EventNotBettable exception with .reason attribute
    - list_bets selector (GET /bets, DESC ordering)
    - get_bet_by_id selector (GET /bet/{id}, BetRead | None)
  affects:
    - 03-08 (routes will import place_bet, list_bets, get_bet_by_id)
tech_stack:
  patterns:
    - "validate-before-UoW: all 3 EventNotBettable checks raised before async with uow: — no DB connection acquired on fail"
    - "A1 mitigation: BetRead.model_validate(bet, from_attributes=True) called inside async with uow: after flush+refresh"
    - "Anti-Pattern 5: all 3 production files return BetRead DTO, never raw Bet ORM"
    - "autouse truncate_bets isolation wired in bet_maker conftest via _auto_truncate wrapper"
key_files:
  created:
    - src/bet_maker/interactors/__init__.py
    - src/bet_maker/interactors/place_bet.py
    - src/bet_maker/selectors/__init__.py
    - src/bet_maker/selectors/list_bets.py
    - src/bet_maker/selectors/get_bet.py
  modified:
    - tests/bet_maker/test_place_bet.py
    - tests/bet_maker/test_selectors.py
    - tests/bet_maker/conftest.py
decisions:
  - "EventNotBettable named without Error suffix (ruff N818) — suppressed via noqa: N818; plan requires exact class name as artifact/test contract"
  - "autouse truncate_bets activated in bet_maker conftest via wrapper fixture (Rule 2 deviation — root conftest defined truncate_bets but did not wire autouse)"
metrics:
  duration: "~10 min"
  completed: "2026-05-15"
  tasks: 4
  files: 8
requirements: [BM-05, BM-06, BM-07, BM-13]
---

# Phase 3 Plan 07: Interactor place_bet + Selectors Summary

Business-logic layer: single write use-case (place_bet) and two read selectors (list_bets, get_bet_by_id). Routes (Plan 03-08) will consume all three.

## What Was Built

### Task 1: `src/bet_maker/interactors/place_bet.py`

`place_bet(uow, *, event_id, amount, event_lookup) -> BetRead` with 3-branch validation outside UoW:

```
snapshot = await event_lookup.get_event(event_id)
if snapshot is None: raise EventNotBettable("event not found")
if snapshot.deadline <= utc_now(): raise EventNotBettable("deadline passed")
if snapshot.state != EventState.NEW: raise EventNotBettable("event not active")
async with uow:
    ...flush+refresh...
    return BetRead.model_validate(bet, from_attributes=True)  # inside session
```

`EventNotBettable(Exception)` exposes `.reason` attribute with one of exactly 3 strings.

### Task 2: `src/bet_maker/selectors/list_bets.py` + `get_bet.py`

- `list_bets(session) -> list[BetRead]` — `select(Bet).order_by(Bet.created_at.desc())`
- `get_bet_by_id(session, bet_id) -> BetRead | None` — `scalar_one_or_none()`

Both use `BetRead.model_validate(row, from_attributes=True)` (Anti-Pattern 5 mitigation).

### Task 3: `tests/bet_maker/test_place_bet.py` — 7 tests

| Class | Test | Coverage |
|-------|------|----------|
| TestHappyPath | test_returns_betread_with_pending_status | BM-05, A1 mitigation (created_at not None) |
| TestHappyPath | test_amount_quantized_to_two_places | D-04/D-19, Risk Axis 1 |
| TestHappyPath | test_persists_to_db | UoW commit-on-success |
| TestRejections | test_event_not_found_raises | "event not found" |
| TestRejections | test_deadline_passed_raises | "deadline passed" |
| TestRejections | test_state_not_new_raises | "event not active" |
| TestRejections | test_no_db_write_on_validation_fail | validate-before-UoW invariant |

### Task 4: `tests/bet_maker/test_selectors.py` — 6 tests

| Class | Test | Coverage |
|-------|------|----------|
| TestListBets | test_returns_empty_list_when_no_bets | empty table |
| TestListBets | test_orders_by_created_at_desc | Risk Axis 9 — DESC ordering |
| TestListBets | test_returns_betread_dto_not_orm | Anti-Pattern 5 |
| TestGetBetById | test_returns_betread_for_existing | BM-13 happy path |
| TestGetBetById | test_returns_none_for_missing | D-08 None → 404 |
| TestGetBetById | test_amount_is_decimal_with_two_places | D-19 / Risk Axis 1 |

## Test Counts

- `test_place_bet.py`: 7 tests (all passed)
- `test_selectors.py`: 6 tests (all passed)
- Full suite: **170 passed** (was 157 before this plan)

## EventNotBettable Reason Strings (exact match verification)

- "event not found" — triggered when `event_lookup.get_event()` returns None
- "deadline passed" — triggered when `snapshot.deadline <= utc_now()`
- "event not active" — triggered when `snapshot.state != EventState.NEW`

All 3 strings verified by `test_event_not_found_raises`, `test_deadline_passed_raises`, `test_state_not_new_raises`.

## Critical Risk Axes Coverage

- **Risk Axis 1 (Decimal precision)**: `test_amount_quantized_to_two_places` (Decimal("10") → "10.00") + `test_amount_is_decimal_with_two_places` (str(amount) == "10.00")
- **Risk Axis 9 (GET /bets ordering under server_default created_at)**: `test_orders_by_created_at_desc` inserts 3 bets with asyncio.sleep(0.01) between commits, verifies `[b.id for b in bets] == list(reversed(inserted_ids))`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] autouse truncate_bets not wired**

- **Found during:** Task 3 — `test_no_db_write_on_validation_fail` failed with `count == 3` (prior happy-path tests' committed rows visible)
- **Issue:** `truncate_bets` fixture defined in root conftest (with teardown TRUNCATE) was not wired as autouse for bet_maker tests. Root conftest comment said "autouse is declared in tests/bet_maker/conftest.py" but it wasn't.
- **Fix:** Added `_auto_truncate(truncate_bets)` fixture with `autouse=True` to `tests/bet_maker/conftest.py`
- **Files modified:** `tests/bet_maker/conftest.py`
- **Commit:** 1c6c556

**2. [Rule 1 - Bug] ruff N818 on EventNotBettable class name**

- **Found during:** Task 1 verification
- **Issue:** ruff rule N818 requires Exception subclasses to use `Error` suffix; plan requires exact name `EventNotBettable` (artifacts + test contracts)
- **Fix:** Added `# noqa: N818` on class definition line. Plan name takes precedence (test contracts reference `EventNotBettable` by exact name)
- **Files modified:** `src/bet_maker/interactors/place_bet.py`
- **Commit:** 11325ef

## Self-Check

Verified created files exist:
- `src/bet_maker/interactors/__init__.py` — FOUND
- `src/bet_maker/interactors/place_bet.py` — FOUND
- `src/bet_maker/selectors/__init__.py` — FOUND
- `src/bet_maker/selectors/list_bets.py` — FOUND
- `src/bet_maker/selectors/get_bet.py` — FOUND

Verified commits:
- 11325ef — feat(03-07): place_bet interactor + EventNotBettable
- e100971 — feat(03-07): list_bets (DESC) + get_bet_by_id selectors
- 1c6c556 — test(03-07): replace test_place_bet Wave 0 stub — 7 tests
- 5938747 — test(03-07): replace test_selectors Wave 0 stub — 6 tests

## Self-Check: PASSED
