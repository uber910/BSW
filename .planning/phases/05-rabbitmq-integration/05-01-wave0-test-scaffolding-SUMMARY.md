---
phase: "05"
plan: "01"
subsystem: "test-infrastructure"
tags: [testcontainers, rabbitmq, pika, fixtures, stubs, wave0]
dependency_graph:
  requires: []
  provides: [rabbitmq_container, amqp_url, wave0-stubs]
  affects: [05-02, 05-04, 05-05, 05-06, 05-07, 05-09]
tech_stack:
  added: ["pika>=1.3,<2 (dev-only)"]
  patterns: ["session-scoped testcontainer fixture", "pytest.skip stub pattern"]
key_files:
  created:
    - tests/contract/__init__.py
    - tests/contract/test_event_finished_message_schema.py
    - tests/bet_maker/test_messaging.py
    - tests/bet_maker/test_settle.py
    - tests/bet_maker/test_e2e_rabbitmq.py
    - tests/line_provider/test_lifespan.py
    - tests/line_provider/test_event_bus.py
  modified:
    - pyproject.toml
    - uv.lock
    - tests/conftest.py
decisions:
  - "pika added to [dependency-groups.dev] only (not [project.dependencies]) — dev-only per RESEARCH.md Pitfall 3"
  - "rabbitmq_container fixture uses rabbitmq:4.2-management-alpine matching docker-compose.yml production target"
  - "amqp_url derives credentials from container instance properties (username/password/vhost) at session startup"
  - "stub tests use pytest.skip (not pytest.mark.xfail) — skip shows clearly in output without import of non-existent production code"
metrics:
  duration: "~5 min"
  completed_date: "2026-05-18"
  tasks_completed: 3
  files_created: 7
  files_modified: 3
---

# Phase 05 Plan 01: Wave 0 Test Scaffolding Summary

**One-liner:** pika dev-dep + session-scoped RabbitMqContainer fixtures + 8 collectable Wave 0 stub tests for all Phase 5 plans.

## What Was Built

### Task 1 — pika dev-dep (commit 86a8abc)

Added `"pika>=1.3,<2"` to `[dependency-groups.dev]` in `pyproject.toml`. `uv lock` resolved `pika 1.4.0`. This unblocks `from testcontainers.rabbitmq import RabbitMqContainer` without `ModuleNotFoundError` on the `pika.BlockingConnection` readiness probe.

**pyproject.toml diff (relevant):**
```
[dependency-groups]
dev = [
    ...
    "respx>=0.22,<0.23",
+   "pika>=1.3,<2",
]
```

### Task 2 — RabbitMQ fixtures in tests/conftest.py (commit bc072be)

Two session-scoped fixtures appended after `truncate_bets`:

```python
@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer("rabbitmq:4.2-management-alpine") as rmq:
        yield rmq

@pytest.fixture(scope="session")
def amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
    host = rabbitmq_container.get_container_host_ip()
    port = rabbitmq_container.get_exposed_port(5672)
    user = rabbitmq_container.username
    password = rabbitmq_container.password
    vhost = rabbitmq_container.vhost
    return f"amqp://{user}:{password}@{host}:{port}/{vhost}"
```

Mirrors the existing `postgres_container` / `pg_dsn` pattern. mypy clean (72 files).

### Task 3 — Wave 0 stub files (commit 755ab93)

7 new files created, 8 stub tests collected:

| File | Tests | Implementing Plan |
|------|-------|-------------------|
| `tests/contract/__init__.py` | — | — |
| `tests/contract/test_event_finished_message_schema.py` | 1 | 05-02 |
| `tests/bet_maker/test_messaging.py` | 2 | 05-05 |
| `tests/bet_maker/test_settle.py` | 2 | 05-04 |
| `tests/bet_maker/test_e2e_rabbitmq.py` | 1 | 05-09 |
| `tests/line_provider/test_lifespan.py` | 1 | 05-07 |
| `tests/line_provider/test_event_bus.py` | 1 | 05-06 |

All tests: `8 skipped, 0 failed`. No production code imported in stubs.

## Overall Verification

- `uv run python -c "from testcontainers.rabbitmq import RabbitMqContainer; print('ok')"` → `ok`
- `uv run pytest tests/ -q` → **253 passed, 8 skipped** (zero regressions)
- `uv run mypy src tests/conftest.py` → `Success: no issues found in 72 source files`
- `uv run ruff check src tests` → all checks passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff I001 import sorting in 6 stub files**
- **Found during:** Task 3 pre-commit hook
- **Issue:** ruff required blank line between `from __future__ import annotations` and `import pytest` (isort rule I001)
- **Fix:** `uv run ruff check --fix` + ruff-format hook on second commit attempt — auto-corrected
- **Files modified:** all 6 stub test files
- **Commit:** 755ab93

## Threat Surface Scan

No new production network endpoints, auth paths, or schema changes introduced. All changes are dev-only (pyproject.toml dev group, test files, test fixtures). Threat T-05-01-03 (testcontainers session leak) mitigated by existing `TESTCONTAINERS_RYUK_DISABLED=true` env setting in conftest.py.

## Known Stubs

All stubs are intentional Wave 0 scaffolding — each references the specific plan that will implement the real test. No production functionality is stubbed.

## Self-Check: PASSED

- `tests/contract/__init__.py` — FOUND
- `tests/contract/test_event_finished_message_schema.py` — FOUND
- `tests/bet_maker/test_messaging.py` — FOUND
- `tests/bet_maker/test_settle.py` — FOUND
- `tests/bet_maker/test_e2e_rabbitmq.py` — FOUND
- `tests/line_provider/test_lifespan.py` — FOUND
- `tests/line_provider/test_event_bus.py` — FOUND
- commit 86a8abc — FOUND (chore(05-01): add pika)
- commit bc072be — FOUND (feat(05-01): rabbitmq fixtures)
- commit 755ab93 — FOUND (feat(05-01): Wave 0 stubs)
