---
phase: 05
plan: 05
subsystem: bet_maker/entrypoints
tags: [rabbitmq, faststream, consumer, manual-ack, dlx, dlq, tenacity, tdd]
dependency_graph:
  requires: [05-02, 05-04]
  provides: [RabbitRouter, on_event_finished, UnsupportedSchemaVersion, RabbitBrokerDep]
  affects: [05-07-lifespan, 05-08-health, 05-09-e2e]
tech_stack:
  added: []
  patterns:
    - RabbitRouter (FastAPI integration) with Channel(prefetch_count=10) per F2/D-26
    - AckPolicy.MANUAL on @router.subscriber per R1/F1/D-07
    - routing_key on RabbitQueue (not on decorator) per RESEARCH F1
    - DLX wiring via RabbitQueue.arguments dict per D-04
    - tenacity 3-retry wrap on settle_bets_for_event (TRANSIENT only) per D-08
    - msg.ack() only after async with uow exits cleanly per R2/F4/D-11
    - A7 structlog clear/bind/finally-clear per D-27
    - set_sessionmaker() module-level pin for lifespan wiring
    - RabbitBrokerDep via late import provider (avoids circular import)
    - TestRabbitBroker in-memory unit tests (6 classes, 9 tests)
key_files:
  created:
    - src/bet_maker/entrypoints/messaging.py
    - tests/bet_maker/test_messaging.py (replaced Wave 0 stub)
  modified:
    - src/bet_maker/facades/deps.py
decisions:
  - "RabbitMessage import from faststream.rabbit.fastapi (not faststream.rabbit.annotations) -- required for RabbitRouter FastAPI integration with TestRabbitBroker"
  - "DecodeError does not exist in faststream 0.6.7 (RESEARCH A4 assumption was wrong) -- removed from POISON branch; ValidationError covers malformed payloads"
  - "set_sessionmaker() module-level pin chosen over FastStream Depends injection (simpler, lifespan sets it before consumers start)"
  - "get_rabbit_broker() uses late import of router to avoid circular dependency chain"
metrics:
  duration: ~15 min
  completed: "2026-05-18"
  tasks_completed: 3
  files_created: 2
  files_modified: 1
---

# Phase 5 Plan 05: Messaging Entrypoint Summary

**One-liner:** bet-maker AMQP consumer with RabbitRouter + AckPolicy.MANUAL + tenacity retry + DLX/DLQ wiring; RabbitBrokerDep for health; 9 TestRabbitBroker unit tests covering all D-30 branches.

## What Was Built

### Task 1 — messaging.py (commit 1f88171)

`src/bet_maker/entrypoints/messaging.py` — 185 LOC, the single consumer entrypoint for bet-maker.

**Locked API forms (all verified against faststream 0.6.7):**

```python
from faststream import AckPolicy
from faststream.rabbit.fastapi import RabbitMessage, RabbitRouter
from faststream.rabbit.schemas import Channel, ExchangeType, RabbitExchange, RabbitQueue

router = RabbitRouter(str(_settings.rabbitmq_url), default_channel=Channel(prefetch_count=10))

@router.subscriber(
    queue=RabbitQueue(
        "bet_maker.events.finished",
        durable=True,
        routing_key=EVENT_FINISHED_WILDCARD,
        arguments={"x-dead-letter-exchange": "bsw.events.dlx", "x-dead-letter-routing-key": "bet_maker.events.finished"},
    ),
    exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
    ack_policy=AckPolicy.MANUAL,
)
async def on_event_finished(payload: EventFinishedMessage, msg: RabbitMessage) -> None: ...
```

**Manual-ack ladder (D-09/D-10/D-11):**
- POISON (ValidationError, UnsupportedSchemaVersion, IntegrityError) -> `reject(requeue=False)` -> DLQ
- TRANSIENT exhausted (default Exception) -> `reject(requeue=False)` -> DLQ
- Happy path -> `await msg.ack()` AFTER `async with uow:` exits cleanly (R2/F4)
- `nack(requeue=True)` NEVER called (R7)

**Subscribers introspection:**
```
uv run python -c "from bet_maker.entrypoints.messaging import router; from faststream import AckPolicy; assert any(s.ack_policy == AckPolicy.MANUAL for s in router.broker.subscribers)"
# exits 0
```

### Task 2 — deps.py extension (commit cff3f79)

`src/bet_maker/facades/deps.py` extended with:
- `get_rabbit_broker(request: Request) -> RabbitBroker` — late import provider
- `RabbitBrokerDep = Annotated[RabbitBroker, Depends(get_rabbit_broker)]` alias

Available for Plan 05-08 `/health` extension and integration tests.

### Task 3 — test_messaging.py (commit d1f96e5)

`tests/bet_maker/test_messaging.py` — Wave 0 stub (2 skipped tests) replaced with 9 real tests:

| Class | Tests | D-30 Coverage |
|-------|-------|---------------|
| `TestSubscriberConfig` | 2 | AckPolicy.MANUAL registered; subscriber count > 0 (05-05-01) |
| `TestHappyPath` | 1 | Mock settle returns result -> called_once -> handler completes (05-05-02) |
| `TestPoison` | 2 | schema_version mismatch -> settle not called; IntegrityError -> caught (05-05-03) |
| `TestTransient` | 2 | Flaky settle retries then succeeds; exhausted -> caught (05-05-04/05) |
| `TestNoop` | 1 | 0 PENDING bets -> settle called once, no exception (05-05-02 variant) |
| `TestInvariants` | 1 | Static source check: msg.nack( not in code (R7) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `DecodeError` does not exist in faststream.exceptions**
- **Found during:** Task 1 import verification
- **Issue:** `from faststream.exceptions import DecodeError` raised `ImportError: cannot import name 'DecodeError'`. RESEARCH.md A4 assumption was incorrect — this class does not exist in faststream 0.6.7.
- **Fix:** Removed `DecodeError` import and removed it from the POISON except clause. FastStream's payload parser raises `pydantic.ValidationError` for malformed payloads, which is already caught in the POISON branch. The RESEARCH.md noted this as A4 with "If wrong, `ValidationError` IS caught in handler" — confirmed correct.
- **Files modified:** `src/bet_maker/entrypoints/messaging.py`
- **Commit:** Part of 1f88171

**2. [Rule 1 - Bug] Wrong `RabbitMessage` import for FastAPI integration**
- **Found during:** Task 3 test execution
- **Issue:** `from faststream.rabbit.annotations import RabbitMessage` uses `faststream.Context` internally, which raises `SetupError: Incorrect faststream.Context usage at on_event_finished. For FastAPI integration use faststream.[broker].fastapi.Context instead.` when `TestRabbitBroker` calls `patch_broker_calls`.
- **Fix:** Changed to `from faststream.rabbit.fastapi import RabbitMessage, RabbitRouter` — the FastAPI-compatible annotation that uses `fastapi.Depends` internally.
- **Files modified:** `src/bet_maker/entrypoints/messaging.py` (import line); `tests/bet_maker/test_messaging.py` (import removed — only needed messaging.py fix)
- **Commit:** d1f96e5

## Threat Surface Scan

All new surfaces are within the plan's threat model:
- T-05-05-01: Malformed payload MITIGATED by ValidationError in POISON branch (UnsupportedSchemaVersion/IntegrityError also covered)
- T-05-05-02: Lost message MITIGATED by AckPolicy.MANUAL + ack after UoW commit
- T-05-05-03: Poison-message loop MITIGATED by R7 guard (reject(requeue=False) only; static test in TestInvariants)
- T-05-05-04: Unbounded prefetch MITIGATED by Channel(prefetch_count=10)
- T-05-05-05: Exception info in DLQ MITIGATED by exc=str(exc)[:500] truncation
- T-05-05-06: structlog cross-task contamination MITIGATED by clear_contextvars at entry + finally
- T-05-05-07: Settled bet auditable via settled_via="consumer" + structlog settle.committed
- T-05-05-08: Unknown schema_version MITIGATED by explicit F7 check raising UnsupportedSchemaVersion

## Self-Check: PASSED

Files created/modified:
- `src/bet_maker/entrypoints/messaging.py` — FOUND
- `src/bet_maker/facades/deps.py` — FOUND
- `tests/bet_maker/test_messaging.py` — FOUND (stub replaced)

Commits:
- `1f88171` feat(05-05): implement RabbitRouter consumer entrypoint with manual-ack ladder — FOUND
- `cff3f79` feat(05-05): add RabbitBrokerDep to deps.py for /health and tests — FOUND
- `d1f96e5` test(05-05): replace stub test_messaging.py with full 7-branch TestRabbitBroker suite — FOUND

Full suite: 278 passed, 3 skipped (wave 0 stubs for later plans), 0 failed.
mypy: Success: no issues found in 120 source files.
ruff: All checks passed.
