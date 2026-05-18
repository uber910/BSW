---
phase: 06-reconciliation-job
plan: 02
type: execute
wave: 0
depends_on: []
files_modified:
  - tests/bet_maker/jobs/__init__.py
  - tests/bet_maker/jobs/test_reconciler_tick.py
  - tests/bet_maker/jobs/test_reconciler_cancellation.py
  - tests/bet_maker/repositories/__init__.py
  - tests/bet_maker/repositories/test_get_pending_event_ids.py
  - tests/bet_maker/interactors/__init__.py
  - tests/bet_maker/interactors/test_cancel_bets_for_event.py
  - tests/bet_maker/migrations/__init__.py
  - tests/bet_maker/migrations/test_0003_cancelled.py
  - tests/bet_maker/config/__init__.py
  - tests/bet_maker/config/test_settings_reconciler.py
  - tests/bet_maker/test_lifespan_reconciler.py
  - tests/bet_maker/test_health_reconciler.py
  - tests/bet_maker/integration/__init__.py
  - tests/bet_maker/integration/test_reconciler_consumer_race.py
  - tests/bet_maker/integration/test_reconciler_drop_publish.py
  - tests/bet_maker/e2e/__init__.py
  - tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
autonomous: true
requirements: [BM-12, QA-08]
tags: [test-scaffolding, wave-0, nyquist, reconciliation]

must_haves:
  truths:
    - "All eleven Wave-0 stub test files exist and are collected by pytest"
    - "Every stub test currently fails with pytest.fail / xfail / NotImplementedError so it cannot accidentally pass before its target plan executes"
    - "Each stub references the target plan number (06-NN) and requirement IDs in its module docstring"
    - "Test directory layout mirrors VALIDATION.md per-task verify map exactly"
  artifacts:
    - path: "tests/bet_maker/jobs/test_reconciler_tick.py"
      provides: "Stub for Plan 06-07-01 (reconciler tick body)"
      contains: "06-07"
    - path: "tests/bet_maker/jobs/test_reconciler_cancellation.py"
      provides: "Stub for Plan 06-07-02 (CancelledError propagation)"
      contains: "CancelledError"
    - path: "tests/bet_maker/repositories/test_get_pending_event_ids.py"
      provides: "Stub for Plan 06-05 (DISTINCT query)"
      contains: "get_pending_event_ids"
    - path: "tests/bet_maker/interactors/test_cancel_bets_for_event.py"
      provides: "Stub for Plan 06-06 (404 → CANCELLED interactor)"
      contains: "cancel_bets_for_event"
    - path: "tests/bet_maker/migrations/test_0003_cancelled.py"
      provides: "Stub for Plan 06-03 (Alembic ALTER TYPE)"
      contains: "0003"
    - path: "tests/bet_maker/config/test_settings_reconciler.py"
      provides: "Stub for Plan 06-04 (new settings fields)"
      contains: "line_provider_reconciler_attempts"
    - path: "tests/bet_maker/test_lifespan_reconciler.py"
      provides: "Stub for Plan 06-08 (lifespan ordering)"
      contains: "reconciliation_task"
    - path: "tests/bet_maker/test_health_reconciler.py"
      provides: "Stub for Plan 06-08 (/health task.done() → 503)"
      contains: "reconciler"
    - path: "tests/bet_maker/integration/test_reconciler_consumer_race.py"
      provides: "Stub for Plan 06-09 (concurrent settle)"
      contains: "FOR UPDATE SKIP LOCKED"
    - path: "tests/bet_maker/integration/test_reconciler_drop_publish.py"
      provides: "Stub for Plan 06-09 (respx drop-publish)"
      contains: "drop"
    - path: "tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py"
      provides: "Stub for Plan 06-10 (real-RMQ e2e — SC#5 / QA-08)"
      contains: "e2e"
  key_links:
    - from: "tests/bet_maker/jobs/test_reconciler_tick.py"
      to: "src/bet_maker/jobs/reconciler.py (created in Plan 06-07)"
      via: "stub imports the target module — once Plan 06-07 lands, the import succeeds and pytest.fail is replaced with real assertions"
      pattern: "from bet_maker.jobs.reconciler"
    - from: "tests/bet_maker/__init__.py-style subpackages"
      to: "pyproject.toml `pythonpath = ['src']` + `asyncio_mode = 'auto'`"
      via: "pytest collection — `pytest --collect-only` finds every stub via auto-discovery"
      pattern: "test_.*\\.py"
---

<objective>
Build the Wave-0 test scaffolding so every downstream production-code task (Plans 06-03..06-10) has a pre-existing failing test to pass. This is the Nyquist safety net: no Phase 6 task may go green by accident because its test did not yet exist.

Purpose: VALIDATION.md §Wave 0 Requirements lists eleven stub files. This plan creates them all in one pass, plus the `__init__.py` files for the four new test sub-packages (`jobs/`, `repositories/`, `interactors/`, `migrations/`, `config/`, `integration/`, `e2e/` — note `tests/bet_maker/__init__.py` already exists). Each stub fails with a clear marker referencing the target plan, and contains the imports + class skeleton the future implementer can fill in.

Output: 11 new stub `.py` files + 7 new `__init__.py` files under `tests/bet_maker/`. `pytest --collect-only tests/bet_maker/` discovers all stubs. Running the suite returns failing tests (not collection errors) for every stub.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@.planning/phases/06-reconciliation-job/06-VALIDATION.md
@tests/bet_maker/conftest.py
@tests/conftest.py
@tests/bet_maker/test_settle.py
</context>

<interfaces>
Existing fixtures (do not redefine — re-use):

From `tests/conftest.py` (session-scoped):
```python
postgres_container: PostgresContainer
pg_dsn: str
apply_migrations: None  # runs alembic upgrade head twice
async_engine: AsyncEngine
session_factory: async_sessionmaker[AsyncSession]
truncate_bets: None  # function-scope, autoused per bet_maker test via _auto_truncate
rabbitmq_container: RabbitMqContainer
amqp_url: str
```

From `tests/bet_maker/conftest.py` (session-scoped, already loaded by every bet_maker test):
```python
app: FastAPI               # lifespan-driven, PG+RMQ wired
client: AsyncClient        # ASGITransport against `app`
seed_event: Callable[..., UUID]
line_provider_app: FastAPI # for cross-service e2e
_auto_truncate (autouse)
_clear_event_lookup (autouse, swaps StubEventLookup)
```

Stub modules the new tests will eventually import (created in later plans):
```python
# Plan 06-05
from bet_maker.repositories.bets import BetRepository
# Plan 06-06
from bet_maker.interactors.cancel_bets_for_event import cancel_bets_for_event
from bet_maker.schemas.settle import CancelResult
# Plan 06-07
from bet_maker.jobs.reconciler import reconciliation_loop, _run_tick, _reconcile_event  # noqa
# Plan 06-08
# app.state.reconciler_event_lookup, app.state.reconciliation_task
```
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Create unit-level stub test files (jobs/, repositories/, interactors/, migrations/, config/)</name>
  <files>
    tests/bet_maker/jobs/__init__.py,
    tests/bet_maker/jobs/test_reconciler_tick.py,
    tests/bet_maker/jobs/test_reconciler_cancellation.py,
    tests/bet_maker/repositories/__init__.py,
    tests/bet_maker/repositories/test_get_pending_event_ids.py,
    tests/bet_maker/interactors/__init__.py,
    tests/bet_maker/interactors/test_cancel_bets_for_event.py,
    tests/bet_maker/migrations/__init__.py,
    tests/bet_maker/migrations/test_0003_cancelled.py,
    tests/bet_maker/config/__init__.py,
    tests/bet_maker/config/test_settings_reconciler.py
  </files>
  <read_first>
    - tests/bet_maker/test_settle.py (the pytest-asyncio class style used everywhere)
    - tests/bet_maker/conftest.py (session-scoped app + autouse fixtures already in scope)
    - .planning/phases/06-reconciliation-job/06-VALIDATION.md §Per-Task Verification Map (matches each stub to a task ID)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Testing D-19..D-22
  </read_first>
  <action>
    For each `__init__.py` listed above: write a single line `"""Test sub-package — Wave 0 scaffolding for Phase 6."""` (empty module docstring is enough; pytest does not require this file to be empty for collection, but having it makes the import graph deterministic under strict mypy).

    For each test stub file: produce a module that

    - Has a docstring stating: "Wave-0 stub — Plan 06-NN. Target requirement(s): BM-12 (and/or BM-05/QA-08). Replace `pytest.fail(...)` with real assertions when Plan 06-NN executes."
    - Imports the *future* target module via `from __future__ import annotations` + a deferred local import inside each test, so collection succeeds even before the target module exists. **Do NOT** import the not-yet-existing module at module level (that would turn the stub into a collection error instead of a runtime test failure).
    - Declares a top-level `pytest.mark.asyncio(loop_scope="session")` class per scenario group (mirror `tests/bet_maker/test_settle.py`).
    - Each test method body is:
      ```python
      async def test_<name>(self) -> None:
          pytest.fail(
              "Wave-0 stub for Plan 06-NN — implement once <target module> exists"
          )
      ```
    - Use the exact test names listed below so VALIDATION.md per-task greps work without edits.

    **Stub file contents (exact test names — these are the public surface the validation map relies on):**

    1) `tests/bet_maker/jobs/test_reconciler_tick.py` — class `TestReconcilerTick`, tests:
       - `test_run_tick_settles_finished_win_events`
       - `test_run_tick_cancels_404_events`
       - `test_run_tick_skips_new_state_events`
       - `test_run_tick_noop_when_no_pending`
       - `test_per_event_exception_isolation`  (mock-lookup raises on one event_id; others still processed)
       - `test_sleep_before_first_tick`        (verifies `await asyncio.sleep(interval_s)` runs BEFORE first `_run_tick`)
       Class `TestReconcilerErrorIsolation` — required by VALIDATION.md row 06-07-02:
       - `test_loop_continues_after_tick_exception`
       - `test_loop_does_not_catch_basesystem_exits`  (verifies only `Exception` is caught, not `BaseException` — `SystemExit` propagates)

    2) `tests/bet_maker/jobs/test_reconciler_cancellation.py` — class `TestReconcilerCancellation`:
       - `test_cancelled_error_propagates_out_of_loop`
       - `test_task_cancel_then_await_terminates_cleanly`
       - `test_cancelled_error_logged_then_reraised`

    3) `tests/bet_maker/repositories/test_get_pending_event_ids.py` — class `TestGetPendingEventIds` (uses `session_factory`):
       - `test_returns_distinct_event_ids_for_pending_bets`
       - `test_excludes_won_lost_cancelled_bets`
       - `test_returns_empty_list_when_no_pending`
       - `test_no_commit_no_flush`  (read-only — Anti-Pattern 1)

    4) `tests/bet_maker/interactors/test_cancel_bets_for_event.py` — three classes (mirror `tests/bet_maker/test_settle.py` shape):
       Class `TestCancelHappyPath`:
       - `test_cancels_two_pending_bets_to_cancelled_status`
       - `test_settled_via_is_reconciler`
       - `test_settled_at_is_filled`
       Class `TestCancelNoop`:
       - `test_idempotent_second_call_returns_zero`
       - `test_noop_when_no_pending_for_event`
       - `test_noop_when_only_already_cancelled_exist`
       Class `TestCancelConcurrent`:
       - `test_concurrent_with_settle_no_double_update`  (asyncio.gather settle+cancel → only one succeeds)
       Class `TestCancelResultShape`:
       - `test_cancel_result_is_frozen`
       - `test_cancel_result_cancelled_at_is_utc_aware`

    5) `tests/bet_maker/migrations/test_0003_cancelled.py` — class `TestMigration0003` (uses `async_engine`):
       - `test_alter_type_adds_cancelled_value`     (post-`alembic upgrade head`, query `pg_enum` for 'cancelled')
       - `test_migration_is_idempotent_on_rerun`    (second `alembic upgrade head` is a no-op)
       - `test_autocommit_block_used`               (introspect migration source for `autocommit_block`)

    6) `tests/bet_maker/config/test_settings_reconciler.py` — class `TestReconcilerSettings`:
       - `test_default_line_provider_reconciler_attempts_is_5`
       - `test_default_line_provider_reconciler_backoff_max_s_is_10`
       - `test_attempts_validated_between_1_and_10`
       - `test_backoff_max_s_must_be_positive`
       - `test_env_var_override_via_BET_MAKER_LINE_PROVIDER_RECONCILER_ATTEMPTS`

    All stubs use the same body — `pytest.fail(...)` referencing the target plan number. Example:
    ```python
    # tests/bet_maker/jobs/test_reconciler_tick.py
    """Wave-0 stub — Plan 06-07. Target req: BM-12.

    Replace pytest.fail(...) with real assertions when Plan 06-07 implements
    src/bet_maker/jobs/reconciler.py.
    """
    from __future__ import annotations

    import pytest


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerTick:
        async def test_run_tick_settles_finished_win_events(self) -> None:
            pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

        async def test_run_tick_cancels_404_events(self) -> None:
            pytest.fail("Wave-0 stub for Plan 06-07 — _run_tick not yet implemented")

        # ... (one method per name listed above)


    @pytest.mark.asyncio(loop_scope="session")
    class TestReconcilerErrorIsolation:
        async def test_loop_continues_after_tick_exception(self) -> None:
            pytest.fail("Wave-0 stub for Plan 06-07 — reconciliation_loop not yet implemented")

        async def test_loop_does_not_catch_basesystem_exits(self) -> None:
            pytest.fail("Wave-0 stub for Plan 06-07 — reconciliation_loop not yet implemented")
    ```

    Use the same shape for every other stub. Do NOT make any of them xfail; they must show up as REGULAR FAILURES until the implementing plan replaces them.
  </action>
  <verify>
    <automated>uv run pytest --collect-only -q tests/bet_maker/jobs tests/bet_maker/repositories tests/bet_maker/interactors tests/bet_maker/migrations tests/bet_maker/config 2>&1 | grep -E "test_" | wc -l</automated>
  </verify>
  <acceptance_criteria>
    - All five `__init__.py` files exist (`test -f tests/bet_maker/jobs/__init__.py && test -f tests/bet_maker/repositories/__init__.py && test -f tests/bet_maker/interactors/__init__.py && test -f tests/bet_maker/migrations/__init__.py && test -f tests/bet_maker/config/__init__.py`)
    - `uv run pytest --collect-only -q tests/bet_maker/jobs tests/bet_maker/repositories tests/bet_maker/interactors tests/bet_maker/migrations tests/bet_maker/config` exits 0
    - Test count per file (run `uv run pytest --collect-only -q <file> 2>&1 | grep -c '::'`):
      - jobs/test_reconciler_tick.py: 8
      - jobs/test_reconciler_cancellation.py: 3
      - repositories/test_get_pending_event_ids.py: 4
      - interactors/test_cancel_bets_for_event.py: 9
      - migrations/test_0003_cancelled.py: 3
      - config/test_settings_reconciler.py: 5
    - Every stub asserts via `pytest.fail`: `grep -RE "pytest\.fail\(" tests/bet_maker/jobs tests/bet_maker/repositories tests/bet_maker/interactors tests/bet_maker/migrations tests/bet_maker/config | wc -l` ≥ 32 (32 stub test methods total)
    - No module-level imports of `bet_maker.jobs.reconciler` or `bet_maker.interactors.cancel_bets_for_event` (collection must not fail before Plan 06-06/06-07 land): `grep -rnE "^from bet_maker\.(jobs\.reconciler|interactors\.cancel_bets_for_event|schemas\.settle import CancelResult)" tests/bet_maker/jobs tests/bet_maker/interactors tests/bet_maker/repositories tests/bet_maker/migrations tests/bet_maker/config | grep -v '^#' | wc -l` returns 0
    - ruff clean: `uv run ruff check tests/bet_maker/jobs tests/bet_maker/repositories tests/bet_maker/interactors tests/bet_maker/migrations tests/bet_maker/config` exits 0
  </acceptance_criteria>
  <done>All five test sub-packages and their stub files exist; pytest collects 32 test methods; every stub is a `pytest.fail` placeholder referencing its target plan.</done>
</task>

<task type="auto">
  <name>Task 2: Create integration + e2e + top-level stub test files (lifespan, health, integration/, e2e/)</name>
  <files>
    tests/bet_maker/test_lifespan_reconciler.py,
    tests/bet_maker/test_health_reconciler.py,
    tests/bet_maker/integration/__init__.py,
    tests/bet_maker/integration/test_reconciler_consumer_race.py,
    tests/bet_maker/integration/test_reconciler_drop_publish.py,
    tests/bet_maker/e2e/__init__.py,
    tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py
  </files>
  <read_first>
    - tests/bet_maker/test_lifespan.py (existing class shape; new stubs mirror this)
    - tests/bet_maker/test_health.py (existing /health 503 mocking pattern)
    - tests/bet_maker/test_e2e_rabbitmq.py (existing e2e session-scope pattern)
    - .planning/phases/06-reconciliation-job/06-VALIDATION.md rows 06-08-01, 06-08-02, 06-09-01, 06-09-02, 06-10-01
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Testing D-21..D-24
  </read_first>
  <action>
    Same scaffolding pattern as Task 1 — `pytest.fail(...)` body, target-plan reference in docstring. Test names below are the source-of-truth for downstream plans' verify greps.

    1) `tests/bet_maker/test_lifespan_reconciler.py` — class `TestLifespanReconciler`:
       - `test_reconciler_event_lookup_pinned_on_state`
       - `test_reconciliation_task_pinned_on_state`
       - `test_task_name_is_reconciliation`
       - `test_task_started_after_broker_connect`         (introspect lifespan source for ordering)
       - `test_task_cancelled_first_in_shutdown_finally`  (introspect lifespan source for ordering)

    2) `tests/bet_maker/test_health_reconciler.py` — class `TestHealthReconciler`:
       - `test_health_200_when_reconciler_task_alive`
       - `test_health_503_when_reconciler_task_done`     (cancel task, await it, then GET /health)
       - `test_health_body_reports_reconciler_check_key` (response.checks.reconciler == 'ok' or 'dead')

    3) `tests/bet_maker/integration/__init__.py` — docstring stub.

    4) `tests/bet_maker/integration/test_reconciler_consumer_race.py` — class `TestReconcilerConsumerRace`:
       - `test_concurrent_settle_consumer_and_reconciler_no_double_update`
       - `test_for_update_skip_locked_one_winner_one_noop`

    5) `tests/bet_maker/integration/test_reconciler_drop_publish.py` — class `TestReconcilerDropPublish`:
       - `test_respx_mocked_lp_terminal_state_triggers_reconciler_settle`
       - `test_respx_mocked_lp_404_triggers_reconciler_cancel`
       - `test_reconciler_skip_when_lp_still_returns_new`

    6) `tests/bet_maker/e2e/__init__.py` — docstring stub.

    7) `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` — class `TestReconcilerDropPublishE2E`:
       - `test_consumer_happy_path_settles_won`           (SC#5 scenario a)
       - `test_drop_publish_reconciler_recovers_won`      (SC#5 scenario b — main QA-08 e2e)
       - `test_delete_event_reconciler_cancels_bet`       (SC#5 scenario c)

    Use the same `pytest.fail("Wave-0 stub for Plan 06-NN — ...")` body for every method. Reference the correct plan number:
    - test_lifespan_reconciler.py → "Plan 06-08"
    - test_health_reconciler.py → "Plan 06-08"
    - integration/test_reconciler_consumer_race.py → "Plan 06-09"
    - integration/test_reconciler_drop_publish.py → "Plan 06-09"
    - e2e/test_reconciler_drop_publish_e2e.py → "Plan 06-10"

    All stubs decorated with `@pytest.mark.asyncio(loop_scope="session")` at class level. No fixture parameters in the stub bodies — keep signatures `async def test_x(self) -> None:` so the failure message is the only visible behaviour.
  </action>
  <verify>
    <automated>uv run pytest --collect-only -q tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py tests/bet_maker/integration tests/bet_maker/e2e 2>&1 | grep -cE "::test_"</automated>
  </verify>
  <acceptance_criteria>
    - All files listed in `<files>` exist on disk.
    - `tests/bet_maker/integration/__init__.py` and `tests/bet_maker/e2e/__init__.py` exist (`test -f tests/bet_maker/integration/__init__.py && test -f tests/bet_maker/e2e/__init__.py`).
    - Total stub test methods collected across the 5 stub files == 16 (5 + 3 + 2 + 3 + 3). Verify with: `uv run pytest --collect-only -q tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py tests/bet_maker/integration tests/bet_maker/e2e 2>&1 | grep -cE "::test_"` returns 16.
    - Every stub method body is a single `pytest.fail(...)` call: `grep -RE "pytest\.fail\(" tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py tests/bet_maker/integration tests/bet_maker/e2e | wc -l` >= 16.
    - No collection errors: `uv run pytest --collect-only -q tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py tests/bet_maker/integration tests/bet_maker/e2e` exits 0.
    - ruff clean: `uv run ruff check tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py tests/bet_maker/integration tests/bet_maker/e2e` exits 0.
    - Grand total Wave 0 stubs across both tasks: pytest collects exactly 32 + 16 = 48 stub methods.
  </acceptance_criteria>
  <done>Lifespan, health, integration, and e2e stub files exist with correct test names; all 16 methods fail explicitly; pytest collects 48 Phase 6 stubs total.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| n/a | Test scaffolding only — no production code touched, no inputs traversed |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-02-01 | Tampering (false-green tests) | Wave-0 stubs | mitigate | Every stub uses `pytest.fail(...)` not `xfail`/`skip`, so any later plan that ships without writing real assertions is loud-failing |
| T-06-02-02 | Repudiation (test traceability) | Stub files | mitigate | Each module docstring names the target plan number; per-task verify map in VALIDATION.md cross-references file paths exactly |
</threat_model>

<verification>
- `uv run pytest --collect-only -q tests/bet_maker/ 2>&1 | tail -5` ends with a count >= prior Phase-5 count + 48.
- No stub fails at collection time (only at runtime): `uv run pytest --collect-only tests/bet_maker/jobs tests/bet_maker/repositories tests/bet_maker/interactors tests/bet_maker/migrations tests/bet_maker/config tests/bet_maker/integration tests/bet_maker/e2e tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py 2>&1 | grep -E "(error|ERROR)" | wc -l` returns 0.
- All stubs visibly fail when actually run: `uv run pytest -x tests/bet_maker/jobs/test_reconciler_tick.py 2>&1 | grep -c "FAILED"` >= 1.
</verification>

<success_criteria>
- 18 new files (11 stubs + 7 `__init__.py`).
- `pytest --collect-only tests/bet_maker/` discovers 48 new Phase 6 test methods.
- `ruff check` clean; no module-level imports of yet-to-be-created production modules.
- Every Wave 0 row in VALIDATION.md §Wave 0 Requirements has its corresponding file on disk.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-02-SUMMARY.md` listing the 18 new files with their test-method counts, and a single `uv run pytest --collect-only tests/bet_maker/ 2>&1 | tail -3` snippet showing the total count.
</output>

## Decision Coverage

- D-19: Unit-stubs `test_cancel_bets_for_event.py` scaffolded here.
- D-20: Unit-stubs `test_reconciler_tick.py` / `test_reconciler_cancellation.py` scaffolded here.
- D-21: Integration-stub `test_health_reconciler.py` scaffolded here.
- D-22: Concurrent-stub `test_reconciler_consumer_race.py` scaffolded here.
- D-23: E2E-stub `test_reconciler_drop_publish_e2e.py` scaffolded here.
