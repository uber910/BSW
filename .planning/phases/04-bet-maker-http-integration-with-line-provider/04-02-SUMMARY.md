---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 02
subsystem: schemas
tags: [pydantic, dto, service-boundary, bet-maker, event-read]

requires:
  - phase: 03-bet-maker-domain-db
    provides: "EventState enum (D-12 duplicated) in bet_maker/schemas/events.py"
  - phase: 02-line-provider-core-api
    provides: "LP GET /events payload contract (shape that EventRead deserialises)"
provides:
  - "EventRead DTO for bet-maker side (frozen=True + extra='forbid')"
  - "TestEventRead with 4 behaviour tests + invariant test on TestExtraForbid"
  - "Mirror of P3 D-12 service-boundary duplication pattern (now extended to EventRead per D-13)"
affects: [04-06 list_active_events selector, 04-08 GET /events route]

tech-stack:
  added: []
  patterns:
    - "Service-boundary duplication for shared DTOs (D-13 mirrors P3 D-12)"
    - "frozen=True on read-only DTOs (Pattern D — no mid-pipeline mutation)"
    - "extra='forbid' as drift sentinel — adding a field in line_provider fails loud in bet_maker tests"

key-files:
  created: []
  modified:
    - "src/bet_maker/schemas/events.py"
    - "tests/bet_maker/test_schemas.py"

key-decisions:
  - "EventRead uses plain Decimal (not LP's Coefficient Annotated alias) — bet-maker only deserialises, never normalises"
  - "EventRead uses plain datetime (not AwareDatetime) — Pydantic v2 parses ISO-8601 with tz natively from the LP payload"
  - "frozen=True is non-negotiable — Pattern D: read DTOs are immutable mid-pipeline"

patterns-established:
  - "D-13 service-boundary duplication: bet-maker NEVER imports from line_provider.schemas.events; both sides own their own EventRead class"
  - "Decimal serialises as JSON string ('2.50'), not float — Pitfall A4 mitigation, mirrored from BetRead test pattern"

requirements-completed: []
requirements-progressed: [BM-04]

duration: 3min
completed: 2026-05-17
---

# Phase 04 / Plan 02: EventRead DTO in bet_maker — Summary

**Added the bet-maker-side `EventRead` Pydantic schema that downstream P4 selectors and routes will return — service-boundary discipline preserved by intentional duplication (D-13), the second time this pattern is applied after `EventState` (P3 D-12).**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-17
- **Completed:** 2026-05-17
- **Tasks:** 2 (both TDD)
- **Files modified:** 2

## Accomplishments

- `class EventRead(BaseModel)` added to `src/bet_maker/schemas/events.py` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `event_id: UUID`, `coefficient: Decimal`, `deadline: datetime`, `state: EventState`. Module docstring updated to reference D-13 alongside the existing D-12 EventState mention.
- `class TestEventRead` added to `tests/bet_maker/test_schemas.py` with 4 behaviour tests — parses LP payload, rejects extra fields, is frozen, serialises Decimal as JSON string `"2.50"` (mirror of existing TestBetRead pattern).
- `class TestExtraForbid` extended with `test_eventread_extra_forbid` invariant assertion mirroring the existing BetCreate/BetRead checks.
- 198 tests passing (193 baseline from Plan 04-01 + 5 new); `mypy --strict` clean (67 source files); `ruff check` + `ruff format` clean.

## Task Commits

1. **Task 1: Add EventRead schema** — `6944724` (feat — schema implementation)
2. **Task 2: Add TestEventRead class + TestExtraForbid invariant** — `9dabe80` (test)

**Plan metadata:** _to be committed by this wrap-up_ (docs — STATE/ROADMAP/SUMMARY)

## Files Created/Modified

- `src/bet_maker/schemas/events.py` — extended module docstring (D-13 reference added) + new imports (`datetime`, `Decimal`, `UUID`, `BaseModel`, `ConfigDict`) + `class EventRead`.
- `tests/bet_maker/test_schemas.py` — extended import line (`EventRead` added), new `class TestEventRead` (4 tests) inserted between `TestBetRead` and `TestEnums`, `class TestExtraForbid` extended with `test_eventread_extra_forbid`.

## Decisions Made

None new — the plan dictated the verbatim spec for both the schema and tests (PROJECT-level decision D-13 was the source). Implementation followed the spec exactly.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Schema Diff (key bits)

```python
# src/bet_maker/schemas/events.py — new class at bottom of file

class EventRead(BaseModel):
    """LP GET /events payload item, observed at bet-maker boundary.

    D-13: intentionally duplicated from line_provider.schemas.events.EventRead
    (service-boundary discipline, mirror of EventState duplication per P3 D-12).
    bet-maker uses plain Decimal (not LP's `Coefficient` Annotated alias) --
    we only deserialise, never construct/normalise.
    frozen=True because the bet-maker side only reads these -- they
    should never be mutated mid-pipeline (Pattern D in PATTERNS.md).
    extra='forbid' guards against LP schema drift -- adding a new field
    in line-provider would fail loud in bet-maker tests rather than
    silently dropping data.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    coefficient: Decimal
    deadline: datetime
    state: EventState
```

## Duplication Pattern Enforcement (D-13)

The bet-maker side of `EventRead` is **structurally** but **deliberately not nominally** equivalent to `line_provider.schemas.events.EventRead`. Differences:

| Aspect | line_provider.EventRead | bet_maker.EventRead | Why |
|--------|-------------------------|---------------------|-----|
| `coefficient` type | `Coefficient` (Annotated Decimal w/ AfterValidator + Field(gt=0, max_digits=8, decimal_places=2)) | plain `Decimal` | bet-maker only deserialises; the data has already passed LP validation upstream |
| `deadline` type | `AwareDatetime` | plain `datetime` | Pydantic v2 parses ISO-8601 with tz natively at deserialisation |
| `model_config` | `extra="forbid"` | `frozen=True, extra="forbid"` | bet-maker treats reads as immutable mid-pipeline (Pattern D) |
| Import line in service code | `from line_provider.schemas.events import EventRead` | `from bet_maker.schemas.events import EventRead` | Service-boundary discipline — bet-maker NEVER imports from line_provider |

Drift is caught by:
- `extra="forbid"` — LP adds a new field → bet-maker `model_validate` raises `ValidationError`, test fails loud.
- Existing `test_eventstate_value_parity_with_line_provider` (test_schemas.py:153) already enforces enum-value parity for the duplicated `EventState`. The same byte-for-byte parity for `EventRead` itself is enforced implicitly: any LP-side schema change that adds/removes/renames a field surfaces immediately at the bet-maker boundary.

## Test Inventory

New tests added (5 total):

1. `TestEventRead.test_event_read_parses_lp_payload` — canonical LP payload shape parses to typed fields (UUID, Decimal, aware datetime, EventState.NEW).
2. `TestEventRead.test_event_read_extra_forbid` — extra field `"unknown": "x"` raises `ValidationError`.
3. `TestEventRead.test_event_read_frozen` — `read.event_id = uuid4()` after construction raises `ValidationError`.
4. `TestEventRead.test_event_read_decimal_serializes_as_string` — `model_dump_json()` emits `"coefficient":"2.50"` as string (Pitfall A4).
5. `TestExtraForbid.test_eventread_extra_forbid` — `EventRead.model_config.get("extra") == "forbid"` invariant.

## What Comes Next

- Plan 04-03 (Wave 2 parallel branch) — `BetMakerSettings` two new fields (`line_provider_http_attempts`, `line_provider_http_backoff_max_s`).
- Plan 04-06 (Wave 4) — `selectors/list_active_events.py` will return `list[EventRead]` using the schema added here.
- Plan 04-08 (Wave 6) — `entrypoints/api/events.py` `GET /events` route will use `response_model=list[EventRead]`.

## Acceptance Criteria — All Passed

- `grep -c "class EventRead(BaseModel):" src/bet_maker/schemas/events.py` → 1
- `grep -c "frozen=True" src/bet_maker/schemas/events.py` → 2 (D-13 docstring reference + ConfigDict)
- `grep -c 'extra="forbid"' src/bet_maker/schemas/events.py` → 1
- 4 required fields (`event_id`/`coefficient`/`deadline`/`state`) → 4
- `EventState` enum still has exactly 3 members → 3 (preserved verbatim)
- `class TestEventRead` exists with 4 `test_event_read_*` methods → 4
- `test_eventread_extra_forbid` in `TestExtraForbid` → 1
- `uv run pytest tests/bet_maker -q -x` → 103 passed
- Full repo suite `uv run pytest -q` → 198 passed
- `uv run mypy src` → 67 files clean
- `uv run ruff check` → clean
