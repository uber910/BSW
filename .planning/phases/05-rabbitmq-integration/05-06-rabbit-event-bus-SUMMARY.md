---
phase: 05
plan: 06
subsystem: line-provider
tags: [rabbitmq, publisher, event-bus, routing-constants, correlation-id]
dependency_graph:
  requires: [05-02]
  provides: [RabbitEventBus, line_provider_messaging_router]
  affects: [05-07, line_provider_set_event_state]
tech_stack:
  added: [FastStream RabbitBroker.publish, RabbitExchange TOPIC, AsyncMock spec=RabbitBroker]
  patterns: [EventBus Protocol structural implementation, singleton RabbitRouter, constants single-source D-05]
key_files:
  created:
    - src/line_provider/entrypoints/messaging.py
    - tests/line_provider/test_event_bus.py (replaced Wave 0 stub)
  modified:
    - src/line_provider/facades/event_bus.py
    - src/line_provider/interactors/set_event_state.py
    - tests/line_provider/test_set_event_state.py
decisions:
  - "RabbitEventBus wraps router.broker.publish — no second broker instance (F5/Anti-Pattern 5)"
  - "correlation_id propagated from EventFinishedMessage.correlation_id — Pitfall 6 fixed"
  - "persist=True on every publish — T-05-06-03 mitigation"
  - "AsyncMock(spec=RabbitBroker) used in tests — no real broker needed for unit assertions"
  - "Import E402 auto-fixed: moved from line_provider.messaging.routing import to file top"
metrics:
  duration: ~8min
  completed: "2026-05-18"
  tasks_completed: 5
  files_changed: 5
---

# Phase 05 Plan 06: RabbitEventBus (line-provider publisher) Summary

**One-liner:** RabbitEventBus publishes EventFinishedMessage to bsw.events topic exchange via FastStream RabbitBroker with persist=True and correlation_id propagation (Pitfall 6 fixed).

## What Was Built

### RabbitEventBus class (`src/line_provider/facades/event_bus.py`)

New class added alongside existing `NoopEventBus` and `EventBus` Protocol. Implements the Protocol structurally (no inheritance).

```python
class RabbitEventBus:
    def __init__(self, broker: RabbitBroker) -> None: ...
    async def publish(self, message: EventFinishedMessage, *, routing_key: str) -> None: ...
```

Key properties:
- `_exchange = RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)` — shared instance, constructed once in `__init__`
- `broker.publish(..., persist=True, correlation_id=message.correlation_id)` — both invariants always present
- `NoopEventBus` and `EventBus` Protocol untouched — Phase 2 tests continue working

### line-provider RabbitRouter (`src/line_provider/entrypoints/messaging.py`)

Publisher-only module:
```python
router = RabbitRouter(str(_settings.rabbitmq_url))
```

No `@router.subscriber` decorators — line-provider only publishes. Lifespan (Plan 07) will call `router.broker.connect()` and wire `app.state.event_bus = RabbitEventBus(router.broker)`.

### set_event_state.py rewired (`src/line_provider/interactors/set_event_state.py`)

`_TERMINAL_TO_ROUTING` dict changed from inline string literals to constants:

Before:
```python
_TERMINAL_TO_ROUTING: dict[EventState, str] = {
    EventState.FINISHED_WIN: "event.finished.win",
    EventState.FINISHED_LOSE: "event.finished.lose",
}
```

After:
```python
from line_provider.messaging.routing import EVENT_FINISHED_LOSE, EVENT_FINISHED_WIN

_TERMINAL_TO_ROUTING: dict[EventState, str] = {
    EventState.FINISHED_WIN: EVENT_FINISHED_WIN,
    EventState.FINISHED_LOSE: EVENT_FINISHED_LOSE,
}
```

Commit-before-publish ordering (Phase 2 D-12) untouched.

## Test Counts

| File | Tests | Status |
|------|-------|--------|
| `tests/line_provider/test_event_bus.py` | 3 | All green |
| `tests/line_provider/test_set_event_state.py` | 11 (9 existing + 2 new) | All green |
| Full suite (excluding e2e) | 283 | All green |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `2e495f6` | feat | Add RabbitEventBus to event_bus.py |
| `0ac3645` | feat | Create messaging.py with singleton RabbitRouter |
| `99a8ad8` | feat | Rewire set_event_state.py to routing constants |
| `aee4fac` | test | Implement test_event_bus.py (3 tests) |
| `36f5f90` | test | Add TestRoutingConstantsWiring to test_set_event_state.py |

## Success Criteria Verification

- [x] `RabbitEventBus` implements `EventBus` Protocol structurally
- [x] `persist=True` on every publish
- [x] `correlation_id=message.correlation_id` propagated (Pitfall 6 fixed)
- [x] `RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)`
- [x] `NoopEventBus` preserved
- [x] `messaging.py` declares singleton `router` with no subscribers
- [x] `set_event_state.py` imports routing constants, no inline strings
- [x] Phase 2 D-12 commit-before-publish ordering unchanged
- [x] 14 tests green (3 new event_bus + 11 set_event_state including 2 new)
- [x] mypy strict clean (121 files)
- [x] ruff clean

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] E402 module level import not at top of file**
- **Found during:** Task 5 pre-commit hook
- **Issue:** Plan 05 task 5 code snippet placed `from line_provider.messaging.routing import ...` between function definitions rather than at the top of the file
- **Fix:** Moved import to file header alongside other imports; removed duplicate inline import from the class body
- **Files modified:** `tests/line_provider/test_set_event_state.py`
- **Commit:** `36f5f90`

## Threat Model Coverage

| Threat | Mitigation | Verified |
|--------|-----------|---------|
| T-05-06-01: wrong/missing correlation_id | `broker.publish(correlation_id=message.correlation_id)` | `test_publish_propagates_correlation_id_from_message` |
| T-05-06-02: publish before store mutation | Phase 2 D-12 invariant preserved | existing `test_commit_happens_before_publish_failing_bus` |
| T-05-06-03: message lost on broker restart | `persist=True` always | `test_persist_is_always_true` |
| T-05-06-04: multiple RabbitBroker instances | single `RabbitRouter` in `messaging.py` | `test -c 'assert len(router.broker.subscribers) == 0'` |

## Self-Check: PASSED

- [x] `src/line_provider/facades/event_bus.py` — contains `class RabbitEventBus`
- [x] `src/line_provider/entrypoints/messaging.py` — created, contains `router = RabbitRouter`
- [x] `src/line_provider/interactors/set_event_state.py` — contains `EVENT_FINISHED_WIN`
- [x] `tests/line_provider/test_event_bus.py` — 3 tests pass
- [x] `tests/line_provider/test_set_event_state.py` — 11 tests pass
- [x] Commits `2e495f6`, `0ac3645`, `99a8ad8`, `aee4fac`, `36f5f90` exist in git log
