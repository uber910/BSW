---
phase: 06-reconciliation-job
plan: 08
type: execute
wave: 3
depends_on: [07]
files_modified:
  - src/bet_maker/facades/deps.py
  - src/bet_maker/entrypoints/lifespan.py
  - src/bet_maker/entrypoints/api/health.py
  - tests/bet_maker/test_lifespan_reconciler.py
  - tests/bet_maker/test_health_reconciler.py
autonomous: true
requirements: [BM-12]
tags: [lifespan, asyncio-task, deps, health, shutdown-order]

must_haves:
  truths:
    - "Lifespan creates app.state.reconciler_event_lookup = HttpEventLookup(http_client, attempts=settings.line_provider_reconciler_attempts, max_backoff=settings.line_provider_reconciler_backoff_max_s)"
    - "Lifespan creates app.state.reconciliation_task = asyncio.create_task(reconciliation_loop(app, interval_s=settings.reconciliation_interval_s), name='reconciliation')"
    - "create_task is called AFTER router.broker.connect() and AFTER all app.state pins (route-layer event_lookup + reconciler_event_lookup)"
    - "Shutdown finally: reconciliation_task.cancel() + suppress(CancelledError): await — runs FIRST (before broker.close, http_client.aclose, engine.dispose)"
    - "GET /health 4th check: reconciler == 'ok' when not task.done(); 'dead' otherwise"
    - "/health returns 503 when any of {pg, rmq, subscribers, reconciler} is down"
    - "deps.py exposes ReconcilerEventLookupDep and ReconciliationTaskDep"
  artifacts:
    - path: "src/bet_maker/entrypoints/lifespan.py"
      provides: "Extended lifespan with reconciler create_task + shutdown cancel-first"
      contains: "reconciliation_task"
    - path: "src/bet_maker/entrypoints/api/health.py"
      provides: "/health 4th check on reconciler.done()"
      contains: "reconciler"
    - path: "src/bet_maker/facades/deps.py"
      provides: "ReconciliationTaskDep + ReconcilerEventLookupDep aliases"
      contains: "ReconciliationTaskDep"
  key_links:
    - from: "src/bet_maker/entrypoints/lifespan.py"
      to: "src/bet_maker/jobs/reconciler.py::reconciliation_loop"
      via: "asyncio.create_task call"
      pattern: "create_task\\(.*reconciliation_loop"
    - from: "src/bet_maker/entrypoints/api/health.py"
      to: "src/bet_maker/facades/deps.py::ReconciliationTaskDep"
      via: "FastAPI Depends injection"
      pattern: "ReconciliationTaskDep"
---

<objective>
Wire the reconciler into the FastAPI app lifecycle:

1. **Lifespan startup** (CONTEXT.md D-15): after the existing app.state pins, also pin `app.state.reconciler_event_lookup` (separate `HttpEventLookup` with reconciler-retry params, sharing the singleton `httpx.AsyncClient`) and `app.state.reconciliation_task` (created via `asyncio.create_task(reconciliation_loop(app, interval_s=...), name="reconciliation")`).

2. **Lifespan shutdown** (CONTEXT.md D-16): in the existing `finally` block, **first** cancel the reconciliation task and await it via `with suppress(asyncio.CancelledError)`. Only after the task is collected do we proceed with the existing cascade `broker.close → http_client.aclose → engine.dispose`. Cancel-first is non-negotiable: if we closed `http_client` before cancel-await, an in-flight reconciler HTTP call would crash with `RuntimeError: AsyncClient is closed`.

3. **/health** (CONTEXT.md D-13): extend the existing 3-check endpoint (pg / rmq / subscribers) with a fourth check `reconciler = "ok" if not task.done() else "dead"`. 503 fires when ANY of the four checks is bad. Use `not task.done()` (NOT `task.exception()` — that raises `InvalidStateError` while the task is still running).

4. **deps.py**: add two new providers (and their `Annotated` aliases) for the reconciler-related app.state attributes, following the established `get_X` / `XDep` pattern.

5. Replace the Wave-0 stubs `test_lifespan_reconciler.py` (5 tests) and `test_health_reconciler.py` (3 tests) with real assertions.

Purpose: This is the **integration plan** — production code touches three core files (lifespan, health, deps) and one new instance of an existing class (HttpEventLookup), but no new business logic. All the new behaviour is the orchestration around the building blocks shipped by Plans 06-03..06-07.

Output: Lifespan + health + deps each gain ~10-15 lines; two Wave-0 stub files become 8 real tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@src/bet_maker/entrypoints/lifespan.py
@src/bet_maker/entrypoints/api/health.py
@src/bet_maker/facades/deps.py
@src/bet_maker/jobs/reconciler.py
@src/bet_maker/facades/http_event_lookup.py
@src/bet_maker/settings/config.py
@tests/bet_maker/test_lifespan.py
@tests/bet_maker/test_health.py
@tests/bet_maker/test_lifespan_reconciler.py
@tests/bet_maker/test_health_reconciler.py
</context>

<interfaces>
Existing lifespan startup order (P5 D-21 — Plan 05-07 final state):
```
1. configure_structlog
2. create engine + sessionmaker (create_engine_and_sessionmaker)
3. wait_for_postgres (tenacity)
4. httpx.AsyncClient singleton (line_provider_http_client)
5. router.broker.connect()
6. declare DLX + DLQ + binding
7. set_sessionmaker on messaging module
8. app.state pins: settings, engine, sessionmaker, line_provider_http_client, event_lookup
9. yield
```

Extension to land in this plan (after step 8 — new step 8.5 + step 9.0):
```
8.5. app.state.reconciler_event_lookup = HttpEventLookup(http_client, attempts=settings.line_provider_reconciler_attempts, max_backoff=settings.line_provider_reconciler_backoff_max_s)
9.0. app.state.reconciliation_task = asyncio.create_task(reconciliation_loop(app, interval_s=settings.reconciliation_interval_s), name="reconciliation")
9.5. yield (existing)
```

Existing shutdown finally (P5 / P4 D-20 nested try/finally cascade):
```python
finally:
    log.info("bet_maker.shutdown")
    try:
        await rabbit_router.broker.close()
    finally:
        try:
            await http_client.aclose()
        finally:
            await engine.dispose()
```

Extension (D-16 — cancel FIRST, then the existing cascade):
```python
finally:
    log.info("bet_maker.shutdown")
    reconciliation_task.cancel()
    with suppress(asyncio.CancelledError):
        await reconciliation_task
    try:
        await rabbit_router.broker.close()
    finally:
        try:
            await http_client.aclose()
        finally:
            await engine.dispose()
```

Existing /health body (Plan 05-08 final state):
```python
pg_ok = await ping_postgres(engine)
rmq_ok = await broker.ping(timeout=1.0)
subs_ok = len(broker.subscribers) > 0
if pg_ok and rmq_ok and subs_ok:
    return JSONResponse(200, {"status": "ok", "checks": {"postgres": "ok", "rabbitmq": "ok", "rabbitmq_consumer": "ok"}})
return JSONResponse(503, {"status": "degraded", "checks": {...}})
```

Extension:
- Inject `task: ReconciliationTaskDep`.
- Compute `reconciler_ok = not task.done()`.
- 200 only if `pg_ok and rmq_ok and subs_ok and reconciler_ok`.
- 503 body includes `"reconciler": "ok" if reconciler_ok else "dead"`.

deps.py extension (P3 D-13 pattern):
```python
def get_reconciler_event_lookup(request: Request) -> HttpEventLookup:
    return cast(HttpEventLookup, request.app.state.reconciler_event_lookup)

def get_reconciliation_task(request: Request) -> "asyncio.Task[None]":
    return cast("asyncio.Task[None]", request.app.state.reconciliation_task)

ReconcilerEventLookupDep = Annotated[HttpEventLookup, Depends(get_reconciler_event_lookup)]
ReconciliationTaskDep = Annotated["asyncio.Task[None]", Depends(get_reconciliation_task)]
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend deps.py with reconciler providers + lifespan with create_task + cancel-first shutdown</name>
  <files>src/bet_maker/facades/deps.py, src/bet_maker/entrypoints/lifespan.py, tests/bet_maker/test_lifespan_reconciler.py</files>
  <read_first>
    - src/bet_maker/facades/deps.py (full file — to add to the end)
    - src/bet_maker/entrypoints/lifespan.py (full file — to extend startup + shutdown blocks)
    - src/bet_maker/jobs/reconciler.py (just shipped — confirm `reconciliation_loop` signature)
    - tests/bet_maker/test_lifespan.py (existing pattern: shared `app` fixture, source-introspection for ordering, broker mocking)
    - tests/bet_maker/test_lifespan_reconciler.py (Wave-0 stub — 5 method names locked by Plan 06-02)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-06, D-07, D-14, D-15, D-16
  </read_first>
  <behavior>
    Lifespan:
    - After existing `app.state.event_lookup = HttpEventLookup(...)` line, also set `app.state.reconciler_event_lookup = HttpEventLookup(http_client=http_client, attempts=settings.line_provider_reconciler_attempts, max_backoff=settings.line_provider_reconciler_backoff_max_s)`.
    - Immediately before `yield`, create the task and pin it: `reconciliation_task = asyncio.create_task(reconciliation_loop(app, interval_s=settings.reconciliation_interval_s), name="reconciliation")`, then `app.state.reconciliation_task = reconciliation_task`.
    - In the `finally` block: the FIRST statement after `log.info("bet_maker.shutdown")` is `reconciliation_task.cancel(); with suppress(asyncio.CancelledError): await reconciliation_task`. Only after this does the existing broker→http→engine cascade run.

    deps.py:
    - Two new provider functions + two `Annotated` aliases, mirroring existing `get_event_lookup` / `EventLookupDep` style.
    - `ReconciliationTaskDep` is `Annotated["asyncio.Task[None]", Depends(get_reconciliation_task)]` (string forward-ref for Python 3.10 mypy strict — Task is generic).

    Tests (TestLifespanReconciler):
    - `test_reconciler_event_lookup_pinned_on_state` — `isinstance(app.state.reconciler_event_lookup, HttpEventLookup)`.
    - `test_reconciliation_task_pinned_on_state` — `isinstance(app.state.reconciliation_task, asyncio.Task)`; `not task.done()` at fixture time.
    - `test_task_name_is_reconciliation` — `app.state.reconciliation_task.get_name() == "reconciliation"`.
    - `test_task_started_after_broker_connect` — introspect `inspect.getsource(lifespan)` and assert the substring `create_task(reconciliation_loop` appears AFTER `await rabbit_router.broker.connect()`.
    - `test_task_cancelled_first_in_shutdown_finally` — introspect the lifespan source; in the chunk after `log.info("bet_maker.shutdown")`, the index of `reconciliation_task.cancel()` is BEFORE `rabbit_router.broker.close()`.
  </behavior>
  <action>
    Step A — Edit `src/bet_maker/facades/deps.py`. Add to the imports near the top (in alphabetical order):
    - `import asyncio` (if not already present — currently not in file)
    - `from bet_maker.facades.http_event_lookup import HttpEventLookup`

    Then APPEND at the END of the file (after the existing `RabbitBrokerDep = ...` line):

    ```python
    def get_reconciler_event_lookup(request: Request) -> HttpEventLookup:
        """D-06 / Plan 06-08: HttpEventLookup configured with reconciler retry profile.

        Distinct from `get_event_lookup` (route-layer profile, 3 attempts /
        2s backoff); reconciler profile is 5 attempts / 10s max backoff.
        Shares the singleton `line_provider_http_client` — no second pool.
        """
        return cast(HttpEventLookup, request.app.state.reconciler_event_lookup)


    def get_reconciliation_task(request: Request) -> "asyncio.Task[None]":
        """D-14 / Plan 06-08: the background reconciler task pinned by lifespan.

        Used by /health to check `not task.done()` (D-13). Forward-string
        ref because asyncio.Task is generic and Python 3.10 mypy strict
        requires explicit parameterisation.
        """
        return cast("asyncio.Task[None]", request.app.state.reconciliation_task)


    ReconcilerEventLookupDep = Annotated[
        HttpEventLookup, Depends(get_reconciler_event_lookup)
    ]
    ReconciliationTaskDep = Annotated[
        "asyncio.Task[None]", Depends(get_reconciliation_task)
    ]
    ```

    Step B — Edit `src/bet_maker/entrypoints/lifespan.py`.

    1. Add to the imports (near the top, alphabetised):
       - `import asyncio`
       - `from contextlib import asynccontextmanager, suppress` (replace existing `from contextlib import asynccontextmanager` line)
       - `from bet_maker.jobs.reconciler import reconciliation_loop`

    2. Find the line `app.state.event_lookup = HttpEventLookup(http_client=http_client, attempts=settings.line_provider_http_attempts, max_backoff=settings.line_provider_http_backoff_max_s)` and IMMEDIATELY AFTER it, add:
       ```python
       app.state.reconciler_event_lookup = HttpEventLookup(
           http_client=http_client,
           attempts=settings.line_provider_reconciler_attempts,
           max_backoff=settings.line_provider_reconciler_backoff_max_s,
       )

       reconciliation_task: asyncio.Task[None] = asyncio.create_task(
           reconciliation_loop(app, interval_s=settings.reconciliation_interval_s),
           name="reconciliation",
       )
       app.state.reconciliation_task = reconciliation_task
       ```

    3. Locate the `try: yield` / `finally:` block. After `log.info("bet_maker.shutdown")`, INSERT the cancel-first sequence BEFORE the existing `try: await rabbit_router.broker.close()` line:
       ```python
       reconciliation_task.cancel()
       with suppress(asyncio.CancelledError):
           await reconciliation_task
       ```

    Final shutdown shape:
    ```python
    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
        reconciliation_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconciliation_task
        try:
            await rabbit_router.broker.close()
        finally:
            try:
                await http_client.aclose()
            finally:
                await engine.dispose()
    ```

    Step C — Replace `tests/bet_maker/test_lifespan_reconciler.py` with real assertions. Class name `TestLifespanReconciler`; 5 method names locked.

    ```python
    """Lifespan: reconciler_event_lookup + reconciliation_task wiring (Plan 06-08 / BM-12)."""

    from __future__ import annotations

    import asyncio
    import inspect

    import pytest
    from fastapi import FastAPI

    from bet_maker.entrypoints.lifespan import lifespan
    from bet_maker.facades.http_event_lookup import HttpEventLookup


    @pytest.mark.asyncio(loop_scope="session")
    class TestLifespanReconciler:
        async def test_reconciler_event_lookup_pinned_on_state(self, app: FastAPI) -> None:
            assert hasattr(app.state, "reconciler_event_lookup")
            assert isinstance(app.state.reconciler_event_lookup, HttpEventLookup)

        async def test_reconciliation_task_pinned_on_state(self, app: FastAPI) -> None:
            assert hasattr(app.state, "reconciliation_task")
            assert isinstance(app.state.reconciliation_task, asyncio.Task)
            assert not app.state.reconciliation_task.done(), (
                "reconciliation task died during lifespan startup — see logs"
            )

        async def test_task_name_is_reconciliation(self, app: FastAPI) -> None:
            assert app.state.reconciliation_task.get_name() == "reconciliation"

        async def test_task_started_after_broker_connect(self) -> None:
            """D-15: create_task must come AFTER router.broker.connect() in source order."""
            src = inspect.getsource(lifespan)
            broker_connect_pos = src.index("await rabbit_router.broker.connect()")
            create_task_pos = src.index("create_task(")
            assert broker_connect_pos < create_task_pos, (
                f"create_task ({create_task_pos}) must follow broker.connect ({broker_connect_pos})"
            )
            # And create_task wraps reconciliation_loop specifically
            assert "reconciliation_loop" in src[create_task_pos : create_task_pos + 200]

        async def test_task_cancelled_first_in_shutdown_finally(self) -> None:
            """D-16: in the finally block, task.cancel() precedes broker.close()."""
            src = inspect.getsource(lifespan)
            shutdown_marker = 'log.info("bet_maker.shutdown")'
            shutdown_start = src.index(shutdown_marker)
            shutdown_block = src[shutdown_start:]
            cancel_pos = shutdown_block.index("reconciliation_task.cancel()")
            broker_close_pos = shutdown_block.index(
                "await rabbit_router.broker.close()"
            )
            assert cancel_pos < broker_close_pos, (
                "reconciliation_task.cancel() must precede broker.close() in shutdown"
            )
    ```

    Notes:
    - The session-scoped `app` fixture starts the lifespan once for the whole test session; the reconciler task is running during these tests. Test 2 asserts `not task.done()` — the task should still be sleeping in its first `await asyncio.sleep(30.0)` cycle.
    - The introspection tests do NOT touch a database — purely static.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_lifespan.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "app.state.reconciler_event_lookup = HttpEventLookup" src/bet_maker/entrypoints/lifespan.py` == 1
    - `grep -c "asyncio.create_task" src/bet_maker/entrypoints/lifespan.py` == 1
    - `grep -c "name=\"reconciliation\"" src/bet_maker/entrypoints/lifespan.py` == 1
    - `grep -c "reconciliation_task.cancel" src/bet_maker/entrypoints/lifespan.py` == 1
    - `grep -c "with suppress(asyncio.CancelledError)" src/bet_maker/entrypoints/lifespan.py` == 1
    - `grep -c "from bet_maker.jobs.reconciler import reconciliation_loop" src/bet_maker/entrypoints/lifespan.py` == 1
    - The startup ordering check (introspection): `python -c "import inspect; from bet_maker.entrypoints.lifespan import lifespan; src = inspect.getsource(lifespan); a = src.index('await rabbit_router.broker.connect()'); b = src.index('create_task('); assert a < b, (a, b)"` exits 0
    - The shutdown ordering check: `python -c "import inspect; from bet_maker.entrypoints.lifespan import lifespan; src = inspect.getsource(lifespan); chunk = src[src.index('log.info(\"bet_maker.shutdown\")'):]; a = chunk.index('reconciliation_task.cancel()'); b = chunk.index('await rabbit_router.broker.close()'); assert a < b, (a, b)"` exits 0
    - `grep -c "ReconcilerEventLookupDep" src/bet_maker/facades/deps.py` == 1
    - `grep -c "ReconciliationTaskDep" src/bet_maker/facades/deps.py` == 1
    - `grep -c "get_reconciler_event_lookup\|get_reconciliation_task" src/bet_maker/facades/deps.py` == 2
    - `uv run pytest -x -q tests/bet_maker/test_lifespan_reconciler.py` reports 5 passed
    - `uv run pytest -x -q tests/bet_maker/test_lifespan.py` reports zero regressions (P5 lifespan tests still green)
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/` exits 0
  </acceptance_criteria>
  <done>Lifespan extended with cancel-first reconciler; deps providers added; 5 lifespan tests green; zero regression on P5 lifespan suite.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Extend /health with 4th reconciler check + replace Wave-0 health stub</name>
  <files>src/bet_maker/entrypoints/api/health.py, tests/bet_maker/test_health_reconciler.py</files>
  <read_first>
    - src/bet_maker/entrypoints/api/health.py (full file — current 3-check shape)
    - src/bet_maker/facades/deps.py (after Task 1 — confirm ReconciliationTaskDep is importable)
    - tests/bet_maker/test_health.py (existing patterns: AsyncMock + PropertyMock + dependency_overrides — copy directly)
    - tests/bet_maker/test_health_reconciler.py (Wave-0 stub — 3 method names locked)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-13
  </read_first>
  <behavior>
    /health body:
    - Inject `task: ReconciliationTaskDep` alongside the existing `engine: EngineDep` and `broker: RabbitBrokerDep`.
    - Compute `reconciler_ok = not task.done()`.
    - 200 only when `pg_ok and rmq_ok and subs_ok and reconciler_ok`.
    - 503 body's `checks` dict gains key `"reconciler": "ok" | "dead"`.

    Tests (TestHealthReconciler — 3 methods):
    - `test_health_200_when_reconciler_task_alive` — under the session-scoped `app` fixture (task still sleeping), `GET /health` returns 200, body has `checks.reconciler == "ok"`.
    - `test_health_503_when_reconciler_task_done` — use `app.dependency_overrides[get_reconciliation_task]` to inject a Mock task whose `.done()` returns True; `GET /health` returns 503 with `body.checks.reconciler == "dead"`. Clean up override in try/finally.
    - `test_health_body_reports_reconciler_check_key` — assert the key `"reconciler"` exists in the response `body["checks"]` (regardless of value).
  </behavior>
  <action>
    Step A — Edit `src/bet_maker/entrypoints/api/health.py`. Replace the function body to integrate the fourth check. Show full final shape:

    ```python
    from __future__ import annotations

    from fastapi import APIRouter
    from fastapi.responses import JSONResponse

    from bet_maker.facades.deps import (
        EngineDep,
        RabbitBrokerDep,
        ReconciliationTaskDep,
    )
    from bet_maker.infrastructure.db.pings import ping_postgres

    router = APIRouter(tags=["health"])


    @router.get("/health")
    async def health(
        engine: EngineDep,
        broker: RabbitBrokerDep,
        reconciler_task: ReconciliationTaskDep,
    ) -> JSONResponse:
        """GET /health — PG + RMQ + subscriber + reconciler check (D-13 / SC#3).

        Returns 200 only when all four are healthy:
          - ping_postgres(engine) returns True
          - broker.ping(timeout=1.0) returns True
          - len(broker.subscribers) > 0
          - not reconciler_task.done()  (Phase 6 / D-13 — `not task.done()`
            is sufficient liveness; task.exception() would raise InvalidStateError
            while the task is still running, per RESEARCH Pitfall 6)

        Returns 503 with per-check status string when any check fails.
        """
        pg_ok = await ping_postgres(engine)
        rmq_ok = await broker.ping(timeout=1.0)
        subs_ok = len(broker.subscribers) > 0
        reconciler_ok = not reconciler_task.done()

        if pg_ok and rmq_ok and subs_ok and reconciler_ok:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "checks": {
                        "postgres": "ok",
                        "rabbitmq": "ok",
                        "rabbitmq_consumer": "ok",
                        "reconciler": "ok",
                    },
                },
            )
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "checks": {
                    "postgres": "ok" if pg_ok else "down",
                    "rabbitmq": "ok" if rmq_ok else "down",
                    "rabbitmq_consumer": "ok" if subs_ok else "no subscribers",
                    "reconciler": "ok" if reconciler_ok else "dead",
                },
            },
        )
    ```

    Step B — Replace `tests/bet_maker/test_health_reconciler.py`:

    ```python
    """/health reconciler-check tests (Plan 06-08 / BM-12 / D-13)."""

    from __future__ import annotations

    import pytest
    from fastapi import FastAPI
    from httpx import AsyncClient


    @pytest.mark.asyncio(loop_scope="session")
    class TestHealthReconciler:
        async def test_health_200_when_reconciler_task_alive(
            self, client: AsyncClient
        ) -> None:
            """Under the session-scoped `app` fixture the reconciler task is
            sleeping (default interval 30s); /health should return 200 and
            checks.reconciler should be 'ok'."""
            response = await client.get("/health")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["checks"]["reconciler"] == "ok"

        async def test_health_503_when_reconciler_task_done(
            self, app: FastAPI, client: AsyncClient
        ) -> None:
            """Override the reconciliation task with a stub whose .done() is True;
            GET /health returns 503 + reconciler: 'dead'."""
            from unittest.mock import MagicMock  # noqa: PLC0415

            from bet_maker.facades.deps import get_reconciliation_task  # noqa: PLC0415

            fake_done_task = MagicMock()
            fake_done_task.done.return_value = True
            app.dependency_overrides[get_reconciliation_task] = lambda: fake_done_task  # noqa: PLW0108
            try:
                response = await client.get("/health")
            finally:
                app.dependency_overrides.pop(get_reconciliation_task, None)
            assert response.status_code == 503
            body = response.json()
            assert body["status"] == "degraded"
            assert body["checks"]["reconciler"] == "dead"

        async def test_health_body_reports_reconciler_check_key(
            self, client: AsyncClient
        ) -> None:
            """The `reconciler` key is always present in the checks dict."""
            response = await client.get("/health")
            body = response.json()
            assert "reconciler" in body["checks"]
    ```

    Notes:
    - `app.dependency_overrides[get_reconciliation_task] = lambda: fake_done_task` — ruff PLW0108 may flag the lambda; if it does, add `# noqa: PLW0108` (same pattern as `tests/bet_maker/test_bet_routes.py::TestPostBet503`).
    - Cleanup via try/finally pops the override so the next test sees the real task again.
    - `fake_done_task = MagicMock()` returns a configurable mock; `.done.return_value = True` makes `task.done()` return True without needing a real asyncio.Task.
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/test_health_reconciler.py tests/bet_maker/test_health.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "ReconciliationTaskDep" src/bet_maker/entrypoints/api/health.py` == 1
    - `grep -c "reconciler_ok = not reconciler_task.done()" src/bet_maker/entrypoints/api/health.py` == 1
    - `grep -c "\"reconciler\":" src/bet_maker/entrypoints/api/health.py` == 2 (200 body + 503 body)
    - `grep -c "task.exception" src/bet_maker/entrypoints/api/health.py` == 0 (must NOT use exception() per Pitfall 6)
    - `uv run pytest -x -q tests/bet_maker/test_health_reconciler.py` reports 3 passed
    - `uv run pytest -x -q tests/bet_maker/test_health.py` reports the existing tests passing — note that any test asserting an exact 3-key `checks` dict shape must STILL pass; if a P5 test asserts `set(body["checks"].keys()) == {"postgres", "rabbitmq", "rabbitmq_consumer"}` strictly, the test must be updated in this plan. Search: `grep -nE "len\\(.*checks.*\\)|set\\(.*checks" tests/bet_maker/test_health.py` — handle any matches by updating to include "reconciler" (but be conservative; preserve existing per-check assertions like `body["checks"]["postgres"] == "ok"`).
    - `uv run mypy src/bet_maker/` exits 0
    - `uv run ruff check src/bet_maker/entrypoints/api/health.py tests/bet_maker/test_health_reconciler.py` exits 0
  </acceptance_criteria>
  <done>/health returns the 4th `reconciler` key; 3 new health tests pass; existing 6 health tests untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP /health → reconciler task state | Client reads liveness signal; bad health response misroutes orchestrator decisions |
| lifespan shutdown → asyncio cancel chain | Cancellation order determines whether in-flight work is corrupted |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-08-01 | DoS (false-healthy) | /health 4th check | mitigate | `not task.done()` is the literal R8 formulation; test asserts 503 when stubbed task.done()==True |
| T-06-08-02 | DoS (corrupted shutdown) | shutdown order | mitigate | reconciliation_task.cancel() runs FIRST in finally; introspection test asserts ordering |
| T-06-08-03 | Information Disclosure | health body | accept | Status strings (`ok` / `dead`) carry no internal exception data — D-13 explicitly avoids `task.exception()` |
| T-06-08-04 | DoS (http_client closed mid-call) | reconciler ↔ http_client | mitigate | Cancel-first guarantees in-flight reconciler HTTP request finishes (or is cancelled) BEFORE http_client.aclose() |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/test_lifespan_reconciler.py tests/bet_maker/test_health_reconciler.py tests/bet_maker/test_lifespan.py tests/bet_maker/test_health.py` exits 0.
- `uv run mypy src/` exits 0.
- `uv run ruff check src/ tests/bet_maker/` exits 0.
</verification>

<success_criteria>
- Lifespan creates and cancels the reconciler task in the right order (verified by source-introspection tests).
- /health returns 4 checks; 503 fires when task.done().
- deps.py exposes the two new Annotated aliases.
- Zero regression on P5 lifespan + health suites.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-08-SUMMARY.md` with the lifespan diff, the health diff, and the deps diff.
</output>

## Decision Coverage

- D-06: Separate `HttpEventLookup` instance for reconciler (`app.state.reconciler_event_lookup`) — own retry params (`line_provider_reconciler_attempts`, `line_provider_reconciler_backoff_max_s`); shares the singleton `httpx.AsyncClient` with route-scoped lookup (no second pool).
- D-07: `bet_maker/facades/deps.py` extended with `ReconcilerEventLookupDep` + `ReconciliationTaskDep` (symmetric to P3 D-13 `EventLookupDep`).
- D-13: `/health` upgraded with 4th check — `task.done() is True` OR `task.exception() is not None` → 503.
- D-14: Reconciler task pinned at `app.state.reconciliation_task: asyncio.Task[None]`; deps provider returns it for `/health` Depends.
- D-15: Lifespan startup order — wait_for_pg → http_client → broker.connect → reconciler create_task → yield (extends P5 D-21).
- D-16: Lifespan shutdown order — reconciler cancel FIRST (then `with suppress(asyncio.CancelledError): await task`), THEN broker.close, http_client.aclose, engine.dispose (nested try/finally — P4 D-20 pattern).
- D-18: Task name `"reconciliation"` literal — used in test assertion `app.state.reconciliation_task.get_name() == "reconciliation"`.
- D-21: Integration test `test_health_reconciler.py` — `TestHealthReconciler::test_health_503_when_reconciler_task_done` asserts 503 path.
