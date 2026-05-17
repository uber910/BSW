---
phase: 05
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - pyproject.toml
  - tests/conftest.py
  - tests/contract/__init__.py
  - tests/contract/test_event_finished_message_schema.py
  - tests/bet_maker/test_messaging.py
  - tests/bet_maker/test_settle.py
  - tests/bet_maker/test_e2e_rabbitmq.py
  - tests/line_provider/test_lifespan.py
  - tests/line_provider/test_event_bus.py
autonomous: true
requirements: [QA-06]
must_haves:
  truths:
    - "uv run python -c 'from testcontainers.rabbitmq import RabbitMqContainer' succeeds (pika present)"
    - "Session-scoped rabbitmq_container + amqp_url fixtures are collectable by pytest"
    - "All Wave 0 stub test files exist and are collectable but xfail/skip until implementation lands"
  artifacts:
    - path: "pyproject.toml"
      provides: "pika>=1.3,<2 in [dependency-groups.dev]"
      contains: "pika"
    - path: "tests/conftest.py"
      provides: "session-scoped rabbitmq_container + amqp_url fixtures"
      contains: "RabbitMqContainer"
    - path: "tests/contract/__init__.py"
      provides: "new tests/contract package"
    - path: "tests/contract/test_event_finished_message_schema.py"
      provides: "schema-equality contract test stub"
    - path: "tests/bet_maker/test_messaging.py"
      provides: "7-branch TestRabbitBroker stub matrix"
    - path: "tests/bet_maker/test_settle.py"
      provides: "settle_bets_for_event idempotency + concurrent settle stubs"
    - path: "tests/bet_maker/test_e2e_rabbitmq.py"
      provides: "real-RabbitMQ e2e stub"
    - path: "tests/line_provider/test_lifespan.py"
      provides: "broker.connect ordering + RabbitEventBus pin stub"
    - path: "tests/line_provider/test_event_bus.py"
      provides: "RabbitEventBus.publish unit stub"
  key_links:
    - from: "tests/conftest.py"
      to: "testcontainers.rabbitmq.RabbitMqContainer"
      via: "session-scoped fixture"
      pattern: "RabbitMqContainer.*rabbitmq:4.2-management-alpine"
---

<objective>
Establish Wave 0 test scaffolding so all later waves can target real automated commands.
Adds `pika>=1.3,<2` as a dev-only dependency (required by `testcontainers.rabbitmq.RabbitMqContainer.readiness_probe()`),
declares session-scoped `rabbitmq_container` + `amqp_url` fixtures next to the existing PG testcontainer fixture,
and creates empty stubs for every test file that will be filled in later plans. Stubs use `pytest.skip("filled by Plan 0X")` so collection passes immediately and each acceptance command shows a meaningful test ID that flips green when the implementing plan lands.

Purpose: Sampling continuity — every later plan's `<verify><automated>` references an existing pytest module. No "MISSING" placeholders.
Output: 1 modified config file, 8 new/modified test files, pika dev-dep installed.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/05-rabbitmq-integration/05-CONTEXT.md
@.planning/phases/05-rabbitmq-integration/05-RESEARCH.md
@.planning/phases/05-rabbitmq-integration/05-PATTERNS.md
@.planning/phases/05-rabbitmq-integration/05-VALIDATION.md
@tests/conftest.py
@tests/bet_maker/conftest.py
@pyproject.toml

<interfaces>
<!-- Existing fixtures pattern that we mirror -->

From tests/conftest.py:
```python
@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg

@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    return str(postgres_container.get_connection_url())
```

New fixtures follow the exact same shape with `RabbitMqContainer`.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add pika dev-dep to pyproject.toml and refresh uv.lock</name>
  <read_first>
    - pyproject.toml (current `[dependency-groups]` block at lines 22-33)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Environment Availability (Pitfall 3 — `pika` ModuleNotFoundError on testcontainers import)
  </read_first>
  <action>
    Edit `pyproject.toml` `[dependency-groups]` dev list (currently ends with `"respx>=0.22,<0.23",`). Append `"pika>=1.3,<2",` on a new line BEFORE the closing `]`. Then run `uv lock` to regenerate `uv.lock` deterministically (do NOT run `uv sync` — the executor handles install at the next test run). Do NOT add `pika` to the runtime `[project] dependencies` block — it is dev-only per RESEARCH.md §Pitfall 3.
  </action>
  <verify>
    <automated>grep -q '"pika&gt;=1.3,&lt;2"' pyproject.toml &amp;&amp; uv run python -c "from testcontainers.rabbitmq import RabbitMqContainer; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'pika' pyproject.toml` returns at least 1
    - `grep -c 'pika' pyproject.toml | grep -v '^#'` confirms the dependency exists (no comment-only matches)
    - `uv run python -c "from testcontainers.rabbitmq import RabbitMqContainer"` exits 0
    - `grep -q 'pika' pyproject.toml` returns true ONLY inside `[dependency-groups]` block (not under `[project] dependencies`)
    - `uv.lock` git diff shows `pika` added under `[[package]]` blocks
  </acceptance_criteria>
  <done>pika is installed in the dev venv; importing RabbitMqContainer no longer raises ModuleNotFoundError.</done>
</task>

<task type="auto">
  <name>Task 2: Add session-scoped rabbitmq_container + amqp_url fixtures to tests/conftest.py</name>
  <read_first>
    - tests/conftest.py (current PG testcontainer pattern lines 23-40)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/conftest.py (modified)`
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §E2E test (RabbitMqContainer API)
  </read_first>
  <action>
    Append two fixtures to `tests/conftest.py` after the existing `truncate_bets` fixture. Use the EXACT shape from PATTERNS.md (session-scoped, mirrors PG container):

    ```python
    from testcontainers.rabbitmq import RabbitMqContainer  # type: ignore[import-untyped]

    @pytest.fixture(scope="session")
    def rabbitmq_container() -> Iterator[RabbitMqContainer]:
        """Session-scoped RabbitMQ 4.2 container for e2e + lifespan integration tests.

        QA-06 / D-31: real RabbitMQ via testcontainers — TestRabbitBroker alone
        misses topology bugs (F6). Image matches docker-compose.yml line-provider
        and bet-maker production target.
        Built-in readiness probe uses pika.BlockingConnection (pika is dev-dep).
        """
        with RabbitMqContainer("rabbitmq:4.2-management-alpine") as rmq:
            yield rmq

    @pytest.fixture(scope="session")
    def amqp_url(rabbitmq_container: RabbitMqContainer) -> str:
        """AMQP URL of the running testcontainers RabbitMQ.

        Used by e2e tests and line_provider/bet_maker lifespan tests that
        env-poke BET_MAKER_RABBITMQ_URL / LINE_PROVIDER_RABBITMQ_URL.
        """
        host = rabbitmq_container.get_container_host_ip()
        port = rabbitmq_container.get_exposed_port(5672)
        user = rabbitmq_container.username
        password = rabbitmq_container.password
        vhost = rabbitmq_container.vhost
        return f"amqp://{user}:{password}@{host}:{port}/{vhost}"
    ```

    Place the `from testcontainers.rabbitmq import ...` import after the existing `from testcontainers.postgres import PostgresContainer` line. Keep `type: ignore[import-untyped]` because testcontainers is not stub-typed.
  </action>
  <verify>
    <automated>uv run pytest tests/conftest.py --collect-only -q 2>&amp;1 | grep -q 'no tests collected' &amp;&amp; uv run python -c "import importlib; m = importlib.import_module('tests.conftest'); assert hasattr(m, 'rabbitmq_container') and hasattr(m, 'amqp_url'); print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'def rabbitmq_container' tests/conftest.py | grep -v '^#'` returns 1
    - `grep -c 'def amqp_url' tests/conftest.py | grep -v '^#'` returns 1
    - `grep -q 'RabbitMqContainer("rabbitmq:4.2-management-alpine")' tests/conftest.py`
    - `grep -q '@pytest.fixture(scope="session")' tests/conftest.py` (already there for PG; now there are at least 4 occurrences)
    - `uv run pytest --collect-only -q tests/` exits 0 (collection passes)
    - `uv run mypy src tests/conftest.py` exits 0
  </acceptance_criteria>
  <done>Fixtures collectable; no test changes required to use them; module-level import does not fail.</done>
</task>

<task type="auto">
  <name>Task 3: Create empty Wave 0 stub test files (collectable skips)</name>
  <read_first>
    - .planning/phases/05-rabbitmq-integration/05-VALIDATION.md §Wave 0 Requirements
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md per-file analog references for each new test file
  </read_first>
  <action>
    Create the following EMPTY-BUT-COLLECTABLE pytest modules. Each file contains exactly one stub test that pytest skips with a message naming the plan that will fill it. This guarantees later plans' `<verify><automated>` commands resolve to a real test ID (not a `MISSING` placeholder), and the suite stays green throughout Wave 0.

    File 1 — `tests/contract/__init__.py`: empty file (zero bytes).

    File 2 — `tests/contract/test_event_finished_message_schema.py`:
    ```python
    """Contract test stub — schema-equality of EventFinishedMessage across services.

    Implementation lands in Plan 05-02. D-28 / D-29.
    """
    from __future__ import annotations
    import pytest

    def test_schemas_are_identical_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-02 (schema duplication)")
    ```

    File 3 — `tests/bet_maker/test_messaging.py`:
    ```python
    """Unit-test stub for bet-maker AMQP consumer handler.

    Implementation lands in Plan 05-05. D-30 / D-09 / D-11.
    """
    from __future__ import annotations
    import pytest

    @pytest.mark.asyncio(loop_scope="session")
    async def test_happy_path_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-05 (messaging entrypoint)")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_subscriber_config_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-05 (messaging entrypoint)")
    ```

    File 4 — `tests/bet_maker/test_settle.py`:
    ```python
    """Stub for settle_bets_for_event interactor + concurrent settle race.

    Implementation lands in Plan 05-04. D-12 / D-17 / D-18.
    """
    from __future__ import annotations
    import pytest

    @pytest.mark.asyncio(loop_scope="session")
    async def test_idempotent_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-04 (settle interactor)")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_no_double_update_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-04 (settle interactor)")
    ```

    File 5 — `tests/bet_maker/test_e2e_rabbitmq.py`:
    ```python
    """E2E stub — real RabbitMQ via testcontainers.

    Implementation lands in Plan 05-09. D-31 / QA-06 / F6.
    """
    from __future__ import annotations
    import pytest

    @pytest.mark.asyncio(loop_scope="session")
    async def test_e2e_consumer_settles_bet_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-09 (e2e real-RabbitMQ test)")
    ```

    File 6 — `tests/line_provider/test_lifespan.py`:
    ```python
    """Lifespan stub for line-provider broker.connect ordering.

    Implementation lands in Plan 05-07. D-24.
    """
    from __future__ import annotations
    import pytest

    @pytest.mark.asyncio(loop_scope="session")
    async def test_event_bus_is_rabbit_in_production_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-07 (lifespan composition)")
    ```

    File 7 — `tests/line_provider/test_event_bus.py`:
    ```python
    """Unit stub for RabbitEventBus.publish correlation propagation.

    Implementation lands in Plan 05-06. D-23 / Pitfall 6.
    """
    from __future__ import annotations
    import pytest

    @pytest.mark.asyncio(loop_scope="session")
    async def test_publish_passes_correlation_id_placeholder() -> None:
        pytest.skip("Wave 0 stub — filled by Plan 05-06 (RabbitEventBus publisher)")
    ```

    All files start with `from __future__ import annotations` (codebase convention #3 in PATTERNS.md). None of these files import production code that does not yet exist — they only use `pytest.skip`. Mypy must remain clean.
  </action>
  <verify>
    <automated>uv run pytest tests/contract tests/bet_maker/test_messaging.py tests/bet_maker/test_settle.py tests/bet_maker/test_e2e_rabbitmq.py tests/line_provider/test_lifespan.py tests/line_provider/test_event_bus.py --collect-only -q 2>&amp;1 | tee /tmp/coll.txt | grep -E 'collected|test_' &gt; /dev/null &amp;&amp; uv run pytest tests/contract tests/bet_maker/test_messaging.py tests/bet_maker/test_settle.py tests/bet_maker/test_e2e_rabbitmq.py tests/line_provider/test_lifespan.py tests/line_provider/test_event_bus.py -q 2>&amp;1 | grep -E 'skipped|passed' &gt; /dev/null</automated>
  </verify>
  <acceptance_criteria>
    - `ls tests/contract/__init__.py tests/contract/test_event_finished_message_schema.py tests/bet_maker/test_messaging.py tests/bet_maker/test_settle.py tests/bet_maker/test_e2e_rabbitmq.py tests/line_provider/test_lifespan.py tests/line_provider/test_event_bus.py` lists all 7 files
    - `grep -lc 'pytest.skip("Wave 0 stub' tests/contract tests/bet_maker tests/line_provider -r | wc -l` reports at least 6
    - `uv run pytest tests/contract tests/bet_maker/test_messaging.py tests/bet_maker/test_settle.py tests/bet_maker/test_e2e_rabbitmq.py tests/line_provider/test_lifespan.py tests/line_provider/test_event_bus.py -q` exits 0 with all tests in "skipped" state
    - `uv run mypy src tests/contract tests/bet_maker/test_messaging.py tests/bet_maker/test_settle.py tests/bet_maker/test_e2e_rabbitmq.py tests/line_provider/test_lifespan.py tests/line_provider/test_event_bus.py` exits 0
    - `uv run ruff check tests/contract tests/bet_maker/test_messaging.py tests/bet_maker/test_settle.py tests/bet_maker/test_e2e_rabbitmq.py tests/line_provider/test_lifespan.py tests/line_provider/test_event_bus.py` exits 0
  </acceptance_criteria>
  <done>All Wave 0 stub files exist; collect + run is green with skip status; downstream plan verify commands have real targets.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pyproject.toml dev-dep | Dev-only dependency; not shipped to production runtime |
| testcontainers RabbitMQ | Local-only ephemeral container, dynamic credentials, never used in prod |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-01-01 | Tampering | pyproject.toml dependency injection | accept | pika is widely-used, MIT-licensed, and confined to `[dependency-groups.dev]`; not present in production wheel. Severity: low. |
| T-05-01-02 | Information disclosure | testcontainers RabbitMQ credentials | accept | Credentials are auto-generated per test session by testcontainers and never logged in plaintext. Fixture lives in test-only namespace. Severity: low. |
| T-05-01-03 | Denial of service | testcontainers leakage across sessions | mitigate | Pre-existing `TESTCONTAINERS_RYUK_DISABLED=true` env in tests/conftest.py is acceptable for local dev; CI shutdown handled by container scope=session lifecycle. Severity: low. |
</threat_model>

<verification>
- `uv run pytest --collect-only -q` exits 0 — all Wave 0 stubs collectable
- `uv run pytest tests/ -q` exits 0 with new tests in "skipped" state, no failures
- `uv run mypy src tests` exits 0 (zero new errors)
- `uv run ruff check src tests` exits 0
- `uv run python -c "from testcontainers.rabbitmq import RabbitMqContainer; print('ok')"` outputs `ok`
- `grep -q "pika" pyproject.toml` confirms dev-dep presence
</verification>

<success_criteria>
- pika dev-dep installed and importable
- session-scoped `rabbitmq_container` + `amqp_url` fixtures defined in `tests/conftest.py` next to existing PG container
- 7 stub test files created; all skip cleanly with reference to the implementing plan
- Full test suite remains green (no regressions)
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-01-wave0-test-scaffolding-SUMMARY.md` documenting: pyproject.toml diff, list of new files, exact fixture signatures, count of stubs created.
</output>
