---
phase: 05
plan: 08
subsystem: bet_maker/entrypoints/api
tags: [health, rabbitmq, faststream, tdd, sc5, d-20]
dependency_graph:
  requires: [05-05, 05-07]
  provides: [health-rmq-check, health-subscriber-check, health-and-gate]
  affects: [bet_maker.entrypoints.api.health, tests.bet_maker.test_health]
tech_stack:
  added: []
  patterns:
    - "AND-gate /health: pg_ok AND rmq_ok AND subs_ok -> 200; any False -> 503"
    - "broker.ping(timeout=1.0) — bounded broker latency check (T-05-08-01)"
    - "len(broker.subscribers) > 0 — import-error guard via subscriber count (T-05-08-02 / R6)"
    - "PropertyMock for @property patching on FastStream RabbitBroker base class"
key_files:
  modified:
    - src/bet_maker/entrypoints/api/health.py
    - tests/bet_maker/test_health.py
decisions:
  - "broker.subscribers is a @property on faststream Registrator base class — requires PropertyMock via patch.object(type(broker), ...) not instance patch"
  - "No exception catching around broker.ping — FastStream returns False on timeout/error per API contract; unhandled exceptions propagate as 500 (correct behaviour)"
  - "conftest.py app fixture already updated in Plan 05-07 — Task 2 was pre-completed"
metrics:
  duration: "~12 min"
  completed: "2026-05-18"
  tasks_completed: 3
  files_modified: 2
---

# Phase 5 Plan 08: Health Upgrade Summary

**One-liner:** /health AND-gate extended with broker.ping(timeout=1.0) + len(broker.subscribers) > 0 — SC#5 closed; 6 health tests green via TDD RED/GREEN cycle.

## What Was Built

### Extended /health handler (commit dde1763)

`src/bet_maker/entrypoints/api/health.py` — extended with two new checks:

```python
@router.get("/health")
async def health(engine: EngineDep, broker: RabbitBrokerDep) -> JSONResponse:
    pg_ok = await ping_postgres(engine)
    rmq_ok = await broker.ping(timeout=1.0)
    subs_ok = len(broker.subscribers) > 0

    if pg_ok and rmq_ok and subs_ok:
        return JSONResponse(200, {"status": "ok", "checks": {
            "postgres": "ok", "rabbitmq": "ok", "rabbitmq_consumer": "ok"
        }})
    return JSONResponse(503, {"status": "degraded", "checks": {
        "postgres": "ok" if pg_ok else "down",
        "rabbitmq": "ok" if rmq_ok else "down",
        "rabbitmq_consumer": "ok" if subs_ok else "no subscribers",
    }})
```

**Sample 200 (happy path):**
```json
{
  "status": "ok",
  "checks": {
    "postgres": "ok",
    "rabbitmq": "ok",
    "rabbitmq_consumer": "ok"
  }
}
```

**Sample 503 (broker.ping returns False):**
```json
{
  "status": "degraded",
  "checks": {
    "postgres": "ok",
    "rabbitmq": "down",
    "rabbitmq_consumer": "ok"
  }
}
```

**Sample 503 (no subscribers):**
```json
{
  "status": "degraded",
  "checks": {
    "postgres": "ok",
    "rabbitmq": "ok",
    "rabbitmq_consumer": "no subscribers"
  }
}
```

### Tests (commit 7af7a75 RED + dde1763 GREEN)

`tests/bet_maker/test_health.py` — 6 total (3 existing + 3 new):

| Test | Coverage |
|------|----------|
| `test_health_returns_status_ok` | Updated: asserts all 3 checks ok |
| `test_health_echoes_request_id_header` | Unchanged INFR-08 |
| `test_health_returns_503_when_pg_down` | Unchanged BM-08 |
| `test_health_returns_503_when_rmq_down` | NEW: broker.ping False -> 503 |
| `test_health_returns_503_when_no_subscribers` | NEW: empty subscribers -> 503 |
| `test_health_returns_200_includes_rabbitmq_checks` | NEW: happy path all 3 ok |

**broker.subscribers public API form used:** `len(router.broker.subscribers) > 0` — the only form per RESEARCH §6.

## Task 2: conftest.py (pre-completed by Plan 05-07)

`tests/bet_maker/conftest.py` app fixture already accepted `amqp_url: str` and injected `BET_MAKER_RABBITMQ_URL` as part of Plan 05-07 lifespan composition. Task 2 was confirmed pre-completed; no changes required.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] broker.subscribers is a @property — instance patch raises AttributeError**
- **Found during:** Task 1/3 combined GREEN verification
- **Issue:** Plan specified `patch.object(router.broker, "subscribers", new=[])` but `subscribers` is a `@property` on `faststream._internal.broker.registrator.Registrator` base class. `patch.object` on instance raises `AttributeError: can't set attribute 'subscribers'`.
- **Fix:** Changed to `patch.object(type(router.broker), "subscribers", new_callable=PropertyMock, return_value=[])` which patches the property descriptor at the class level. Added `PropertyMock` import.
- **Files modified:** `tests/bet_maker/test_health.py`
- **Commit:** dde1763 (combined with implementation)

## Threat Model Coverage

| Threat | Mitigation | Status |
|--------|-----------|--------|
| T-05-08-01 (broker.ping hangs) | `timeout=1.0` explicit; FastStream returns False on timeout | MITIGATED |
| T-05-08-02 (/health green while no consumer) | `len(broker.subscribers) > 0`; import-time error leaves subscribers=[]; SC#5 enforces 503 | MITIGATED |
| T-05-08-03 (info disclosure) | Status strings bounded to {ok/down/no subscribers}; no PII | ACCEPTED |
| T-05-08-04 (health probe reveals failure mode) | /health intentionally public for docker-compose healthcheck | ACCEPTED |

## Self-Check: PASSED

Files modified:
- `src/bet_maker/entrypoints/api/health.py` — FOUND
- `tests/bet_maker/test_health.py` — FOUND

Commits:
- `7af7a75` test(05-08): add failing health tests — FOUND
- `dde1763` feat(05-08): extend /health with RMQ + subscriber checks — FOUND

Acceptance criteria:
- `grep -q 'test_health_returns_503_when_rmq_down'` — FOUND
- `grep -q 'test_health_returns_503_when_no_subscribers'` — FOUND
- `grep -q 'test_health_returns_200_includes_rabbitmq_checks'` — FOUND
- `grep -q '"no subscribers"' tests/bet_maker/test_health.py` — FOUND
- `grep -q 'await broker.ping(timeout=1.0)'` — FOUND
- `grep -q 'len(broker.subscribers)'` — FOUND
- `grep -q 'pg_ok and rmq_ok and subs_ok'` — FOUND
- `uv run pytest tests/bet_maker/test_health.py` — 6 passed
- `uv run pytest -q` — 293 passed, 1 skipped
- `uv run mypy src/bet_maker/entrypoints/api/health.py` — Success
- `uv run ruff check src/bet_maker/entrypoints/api/health.py` — passed
