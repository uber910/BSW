---
phase: "05"
plan: "02"
subsystem: "schema-contracts"
tags: [schema-duplication, pydantic, routing-keys, contract-test, d-28, d-05, d-17]
dependency_graph:
  requires: [05-01]
  provides: [bet_maker.schemas.messages, bet_maker.schemas.settle, bet_maker.messaging.routing, line_provider.messaging.routing, contract-test]
  affects: [05-04, 05-05, 05-06, 05-07, 05-08, 05-09]
tech_stack:
  added: []
  patterns: ["byte-for-byte schema duplication (D-28)", "Final[str] routing-key constants (D-05/R5)", "model_json_schema() contract testing (D-29)"]
key_files:
  created:
    - src/bet_maker/schemas/messages.py
    - src/bet_maker/schemas/settle.py
    - src/bet_maker/messaging/__init__.py
    - src/bet_maker/messaging/routing.py
    - src/line_provider/messaging/__init__.py
    - src/line_provider/messaging/routing.py
  modified:
    - tests/contract/test_event_finished_message_schema.py
decisions:
  - "D-28: EventFinishedMessage duplicated byte-for-byte in bet_maker — no cross-service imports across either service"
  - "D-05: Final[str] routing-key constants in both messaging/routing.py modules — symmetric (all 3 constants on both sides)"
  - "D-17: SettleResult uses frozen=True + extra=forbid, imports EventTerminalState from same-service bet_maker.schemas.messages"
  - "Task 4 committed as test(05-02) per TDD convention — contract test is the 'green' gate confirming byte-equality holds"
metrics:
  duration: "~5 min"
  completed_date: "2026-05-18"
  tasks_completed: 4
  files_created: 6
  files_modified: 1
---

# Phase 05 Plan 02: Schema Duplication & Routing Summary

**One-liner:** EventFinishedMessage byte-for-byte duplicated into bet_maker (D-28), SettleResult DTO (D-17) added, Final[str] routing-key constants (D-05) in both service messaging/ packages, contract test promoted to 3-assertion model_json_schema() equality check.

## What Was Built

### Task 1 — Duplicate EventFinishedMessage (commit 4725f01)

Created `src/bet_maker/schemas/messages.py` as a byte-for-byte copy of `src/line_provider/schemas/messages.py`. Docstring added noting D-28 intent. No cross-service imports.

**Byte-equality verification:**
```
uv run python -c "import json; from line_provider.schemas.messages import EventFinishedMessage as L; from bet_maker.schemas.messages import EventFinishedMessage as B; assert json.dumps(L.model_json_schema(), sort_keys=True) == json.dumps(B.model_json_schema(), sort_keys=True), 'drift'; print('ok')"
# Output: ok
```

### Task 2 — SettleResult DTO (commit 045fcd5)

Created `src/bet_maker/schemas/settle.py` with `SettleResult(BaseModel)`:
- `model_config = ConfigDict(frozen=True, extra="forbid")`
- Fields: `event_id`, `terminal_state`, `settled_count`, `settled_bet_ids`, `settled_via: Literal["consumer", "reconciler"]`, `settled_at`
- Imports `EventTerminalState` from `bet_maker.schemas.messages` (same-service, D-28)

### Task 3 — Routing-key constants (commit 7e0d304)

Created 4 files:

| File | Role |
|------|------|
| `src/bet_maker/messaging/__init__.py` | empty package marker |
| `src/bet_maker/messaging/routing.py` | consumer-side constants |
| `src/line_provider/messaging/__init__.py` | empty package marker |
| `src/line_provider/messaging/routing.py` | publisher-side constants |

**Routing-key constants table:**

| Constant | Value |
|----------|-------|
| `EVENT_FINISHED_WIN` | `"event.finished.win"` |
| `EVENT_FINISHED_LOSE` | `"event.finished.lose"` |
| `EVENT_FINISHED_WILDCARD` | `"event.finished.*"` |

All three `Final[str]` constants present in both files. Module docstrings differ ("consumer side" vs "publisher side").

### Task 4 — Contract test promoted to real assertions (commit 50ba98e)

Replaced `tests/contract/test_event_finished_message_schema.py` stub (1 `pytest.skip`) with 3 real synchronous tests:

1. `test_schemas_are_identical` — `model_json_schema(sort_keys=True)` equality; fails on any field addition/reorder/rename in either copy
2. `test_schema_version_field_is_present_with_default_one` — both copies expose `schema_version` with default `1`
3. `test_extra_forbid_is_set_on_both` — both copies have `extra="forbid"` in model_config

```
uv run pytest tests/contract/test_event_finished_message_schema.py -x -q
# Output: 3 passed
```

## Overall Verification

- `uv run python -c "import line_provider.schemas.messages, bet_maker.schemas.messages, bet_maker.schemas.settle, bet_maker.messaging.routing, line_provider.messaging.routing"` → exit 0
- `uv run pytest tests/ -q` → **256 passed, 6 skipped** (wave 0 stubs for later plans)
- `uv run mypy src` → Success: no issues found in 77 source files
- `uv run ruff check src tests` → All checks passed
- `grep -rn "^from line_provider" src/bet_maker/` → no matches (no cross-service imports)
- `grep -rn "^from bet_maker" src/line_provider/` → no matches

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints or auth paths introduced. All changes are pure schema/constant modules (no runtime HTTP or AMQP surface). T-05-02-01 (Tampering via AMQP payload) mitigated by `frozen=True + extra="forbid"` on both `EventFinishedMessage` copies. T-05-02-03 (schema drift) mitigated by contract test in CI (D-29).

## Self-Check: PASSED

- `src/bet_maker/schemas/messages.py` — FOUND
- `src/bet_maker/schemas/settle.py` — FOUND
- `src/bet_maker/messaging/__init__.py` — FOUND
- `src/bet_maker/messaging/routing.py` — FOUND
- `src/line_provider/messaging/__init__.py` — FOUND
- `src/line_provider/messaging/routing.py` — FOUND
- `tests/contract/test_event_finished_message_schema.py` — FOUND (stub replaced)
- commit 4725f01 — FOUND (feat(05-02): duplicate EventFinishedMessage)
- commit 045fcd5 — FOUND (feat(05-02): add SettleResult DTO)
- commit 7e0d304 — FOUND (feat(05-02): add messaging/routing.py constants)
- commit 50ba98e — FOUND (test(05-02): promote contract test stub)
