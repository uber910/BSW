---
phase: 09-uow-repository-removal
fixed_at: 2026-05-19T08:30:00Z
review_path: .planning/phases/09-uow-repository-removal/09-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-05-19T08:30:00Z
**Source review:** `.planning/phases/09-uow-repository-removal/09-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01 + WR-01..WR-04; IN-01..IN-03 deferred per orchestrator scope)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: Двойной вход в `PostgresUnitOfWork` в AMQP-хендлере ломает manual-ack ladder

**Files modified:** `src/bet_maker/api/messaging.py`, `tests/bet_maker/test_messaging.py`
**Commit:** `eaaf3f1`
**Applied fix:** Removed the outer `async with PostgresUnitOfWork(sessionmaker) as uow:` block in `on_event_finished`. The interactor `settle_bets_for_event` already opens its own `async with uow:` (`src/bet_maker/interactors/settle_bets_for_event.py:63`) -- the handler now constructs an un-entered UoW and passes it through, mirroring the `jobs/reconciler.py:113-129` pattern. The handler `ack`s after `_settle_with_retry` returns. The module docstring (line 10) was rewritten to reflect the new ladder ("after `_settle_with_retry(uow, ...)` returns -- UoW context owned by interactor"). Two regression tests added in `tests/bet_maker/test_messaging.py`: (1) `TestInvariants.test_handler_does_not_open_uow_context` -- static guard that `async with PostgresUnitOfWork` MUST NOT appear in `messaging.py`; (2) `TestCR01HandlerOwnsNoUoWContext.test_handler_enters_uow_exactly_once_on_happy_path` -- behavioural net using `TestRabbitBroker` + real PG + a counting `PostgresUnitOfWork` subclass; asserts exactly one `__aenter__` per message. Both tests verified by re-introducing the bug and confirming they fail.

### WR-01: Reconciler открывает транзакционный UoW для чисто read-only селектора

**Files modified:** `src/bet_maker/jobs/reconciler.py`
**Commit:** `7bb6f74`
**Applied fix:** Replaced `async with PostgresUnitOfWork(sessionmaker) as uow:` in `_run_tick` with `async with sessionmaker() as session:` for the work-list read. `get_pending_event_ids` is a single `SELECT DISTINCT` with no `FOR UPDATE`; D-05 explicitly says selectors take `AsyncSession` directly (no UoW knowledge). The new pattern avoids the empty `COMMIT` that `async_sessionmaker.begin()` would send every reconciliation tick. Mirrors `facades/deps.py::get_session` for read-only routes. Per-event UoW inside `_reconcile_event` unchanged.

### WR-02: Module-level mutable global `_sessionmaker` в `messaging.py`

**Files modified:** `src/bet_maker/api/messaging.py`, `tests/bet_maker/test_messaging.py`, `pyproject.toml`
**Commit:** `ac752f4` _(requires human verification)_
**Applied fix:** Removed the module-level `_sessionmaker: async_sessionmaker | None = None`, the `global _sessionmaker` statement (and its `# noqa: PLW0603` suppression), and the `_require_sessionmaker()` helper. `set_sessionmaker(sm)` now pins the sessionmaker into the FastStream router context: `router.context.set_global(_SESSIONMAKER_CONTEXT_KEY, sm)`. The handler reads it via FastStream's `Context(_SESSIONMAKER_CONTEXT_KEY)` DI marker -- same architectural principle as `jobs/reconciler.py` reading from `app.state.sessionmaker`. The FastStream `Context()` is the handler-scope analog of FastAPI `Request.app.state` because subscribers run outside the FastAPI request cycle. Added `[tool.ruff.lint.flake8-bugbear].extend-immutable-calls = ["fastapi.Depends", "faststream.Context", "faststream.rabbit.fastapi.Context"]` to `pyproject.toml` so the B008 false positive on the idiomatic DI default does NOT require a per-line `# noqa`. Test suite continues to use the public `set_sessionmaker` API; the existing autouse fixture works unchanged. **Marked as "requires human verification"** because the change introduces a new FastStream API surface (`Context` injection on the FastAPI integration variant) that the project hasn't used before -- worth a one-pass review even though all tests pass and mypy strict is clean.

### WR-03: Reconciler теряет per-event `event_id` контекст в логах ошибок

**Files modified:** `src/bet_maker/jobs/reconciler.py`
**Commit:** `24bff5b`
**Applied fix:** Wrapped the per-event work block inside `_run_tick` in `structlog.contextvars.bound_contextvars(event_id=str(event_id))` so child logs in selectors, interactors, and the HTTP client inherit the `event_id` automatically. Mirrors the consumer-handler pattern in `api/messaging.py:154-194`. The `_log.exception("reconciler.event.failed")` call drops the redundant explicit `event_id=str(event_id)` kwarg (now inherited from contextvars). `_reconcile_event` retains its explicit `event_id` kwargs in inner log calls because integration tests (`test_reconciler_consumer_race`, `test_reconciler_drop_publish`) invoke it directly without the loop wrapper -- harmless duplication when called via the loop (same key/value in JSON), no regression elsewhere.

### WR-04: `EventTerminalState(snapshot.state.value)` бросает ValueError на не-терминальном состоянии

**Files modified:** `src/bet_maker/jobs/reconciler.py`
**Commit:** `c98eeb8`
**Applied fix:** Replaced `EventTerminalState(snapshot.state.value)` with an explicit `match snapshot.state:` whitelist in `_reconcile_event`. FINISHED_WIN/FINISHED_LOSE map to the terminal state and proceed to settle; NEW logs `reconciler.event.still_new` and returns (moved here from the prior pre-match `if snapshot.state == NEW`); the `_` wildcard logs `reconciler.event.unexpected_state` at warning level and returns. If `EventState` is extended in v2 with another non-terminal state (`CANCELLED_BY_LP`, `POSTPONED`, etc.), the wildcard catches it cleanly -- no `ValueError` noise mixed with real DB/HTTP transients in `reconciler.event.failed` logs.

---

## Skipped Issues

None.

---

## Phase-Gate Validation Output

After all fixes:

```
$ uv run pytest -q --cov=src --cov-fail-under=85
...
355 passed, 26 warnings in 27.04s
Required test coverage of 85% reached. Total coverage: 94.25%
```

```
$ uv run mypy --strict src tests
Success: no issues found in 153 source files
```

```
$ uv run ruff check src tests
All checks passed!

$ uv run ruff format --check src tests
153 files already formatted
```

### Suppression Counters vs Phase 9 Closure Baseline

| Counter        | Phase 9 baseline | Phase 9 post-fix | Delta |
| -------------- | ---------------: | ---------------: | ----: |
| `type: ignore` |               55 |               55 |     0 |
| `# noqa`       |               56 |               55 |   -1  |

REFACTOR-05 quality bar held: no new `# type: ignore`, no new `# noqa` (the only delta is one removed `# noqa: PLW0603` that was guarding the now-deleted `global _sessionmaker`).

### Test Count Delta

| Metric             | Phase 9 closure | Phase 9 post-fix | Delta |
| ------------------ | --------------: | ---------------: | ----: |
| Passing tests      |             353 |              355 |    +2 |
| Coverage           |          94.54% |           94.25% | -0.29 |

The +2 tests are the CR-01 regression net (one static, one behavioural). Coverage is slightly lower because the new tests use the established TestRabbitBroker pattern (broad coverage reuse), but the handler module gains the explicit regression net at the manual-ack ladder.

---

## Commits

| Finding | Commit    | Files                                                                 |
| ------- | --------- | --------------------------------------------------------------------- |
| CR-01   | `eaaf3f1` | `src/bet_maker/api/messaging.py`, `tests/bet_maker/test_messaging.py` |
| WR-01   | `7bb6f74` | `src/bet_maker/jobs/reconciler.py`                                    |
| WR-02   | `ac752f4` | `src/bet_maker/api/messaging.py`, `tests/bet_maker/test_messaging.py`, `pyproject.toml` |
| WR-03   | `24bff5b` | `src/bet_maker/jobs/reconciler.py`                                    |
| WR-04   | `c98eeb8` | `src/bet_maker/jobs/reconciler.py`                                    |

---

_Fixed: 2026-05-19T08:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
