---
phase: 07-polish-documentation
plan: 07
type: execute
wave: 1
depends_on: [01]
files_modified:
  - tests/audit/__init__.py
  - tests/audit/test_static.py
autonomous: true
requirements: [DOC-04]
must_haves:
  truths:
    - "tests/audit/ package marker file exists (empty or single-line docstring)"
    - "tests/audit/test_static.py contains 7 standalone test functions"
    - "test_subscribers_have_manual_ack passes (verifies ack_policy=AckPolicy.MANUAL on every @router.subscriber in bet_maker/entrypoints/messaging.py)"
    - "test_repositories_use_for_update_skip_locked passes (verifies with_for_update(skip_locked=True) in bet_maker/repositories/bets.py)"
    - "test_async_sessionmaker_expire_on_commit_false passes (verifies expire_on_commit=False in bet_maker/infrastructure/db/engine.py)"
    - "test_dockerfile_exec_form_cmd passes (verifies Dockerfile CMD starts with `CMD [`)"
    - "test_dockerfile_pinned_python_bookworm passes (verifies `3.10-slim-bookworm` substring in Dockerfile)"
    - "test_pythonunbuffered_set passes (verifies PYTHONUNBUFFERED=1 in Dockerfile)"
    - "test_durable_queue_and_exchange passes (verifies durable=True in RabbitQueue + RabbitExchange in bet_maker/entrypoints/messaging.py)"
  artifacts:
    - path: "tests/audit/__init__.py"
      provides: "Python package marker for tests/audit/"
      min_lines: 0
    - path: "tests/audit/test_static.py"
      provides: "7 static-audit regex tests for Looks-Done-But-Isn't invariants"
      contains: "def test_"
  key_links:
    - from: "tests/audit/test_static.py"
      to: "src/bet_maker/entrypoints/messaging.py, src/bet_maker/repositories/bets.py, src/bet_maker/infrastructure/db/engine.py, Dockerfile"
      via: "Path.read_text() + regex/substring"
      pattern: "Path\\(__file__\\)\\.resolve\\(\\)\\.parents\\[2\\]"
---

<objective>
Create static-audit test module per CONTEXT.md D-19 with 7 regex/substring tests asserting code-base invariants from the "Looks Done But Isn't" 18-item checklist (ROADMAP P7 SC#6, PITFALLS.md §«Looks Done But Isn't»). These tests run in CI and break the build if a regression silently undoes a P1-P6 invariant.

Per RESEARCH.md/CONTEXT.md D-19: use `Path.read_text()` + `re.search` / `in`. Python `ast` module is overkill for literal-kwarg detection.

Output: `tests/audit/__init__.py` (empty marker) + `tests/audit/test_static.py` (7 tests). All 7 tests must pass against current code-base (verified by RESEARCH.md 18-item evidence map — every item is `verified` today).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-polish-documentation/07-CONTEXT.md
@.planning/phases/07-polish-documentation/07-PATTERNS.md
@.planning/phases/07-polish-documentation/07-RESEARCH.md

<interfaces>
<!-- Files read at test time (read-only via Path.read_text()) -->

src/bet_maker/entrypoints/messaging.py — relevant substrings:
- `@router.subscriber(` ... `ack_policy=AckPolicy.MANUAL` (single subscriber)
- `RabbitQueue("bet_maker.events.finished", durable=True, ...)`
- `RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)`

src/bet_maker/repositories/bets.py — relevant substring:
- `with_for_update(skip_locked=True)` (in `get_pending_locked`)

src/bet_maker/infrastructure/db/engine.py — relevant substring:
- `async_sessionmaker(engine, expire_on_commit=False)`

Dockerfile — relevant substrings:
- `3.10-slim-bookworm` (ARG PYTHON_VERSION line)
- `PYTHONUNBUFFERED=1` (ENV line)
- `CMD [` (exec-form CMD start; current file has `CMD ["python", "-c", "..."]` placeholder)

REPO_ROOT calculation: `Path(__file__).resolve().parents[2]`:
- `tests/audit/test_static.py`.parents[0] = `tests/audit/`
- .parents[1] = `tests/`
- .parents[2] = repo root (where `src/`, `Dockerfile`, etc. live)
</interfaces>
</context>

<threat_model>
N/A — static tests read source files; no runtime side effects, no network, no user input. Audit tests do NOT modify any file.
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create tests/audit/ package and 7 static-audit tests</name>
  <files>tests/audit/__init__.py, tests/audit/test_static.py</files>
  <read_first>
    - src/bet_maker/entrypoints/messaging.py (verify exact strings the regex must match)
    - src/bet_maker/repositories/bets.py (verify with_for_update line)
    - src/bet_maker/infrastructure/db/engine.py (verify async_sessionmaker line)
    - Dockerfile (verify CMD form + bookworm pin + PYTHONUNBUFFERED)
    - tests/contract/__init__.py (analog for empty package marker)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → tests/audit/test_static.py)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (18-item evidence map; Pitfall 6 formatting fragility)
  </read_first>
  <behavior>
    - Test 1 `test_subscribers_have_manual_ack`: count of `@router.subscriber(` decorators == count of `ack_policy=AckPolicy.MANUAL` mentions in `src/bet_maker/entrypoints/messaging.py`; subscriber_count ≥ 1.
    - Test 2 `test_repositories_use_for_update_skip_locked`: substring `with_for_update(skip_locked=True)` present in `src/bet_maker/repositories/bets.py`.
    - Test 3 `test_async_sessionmaker_expire_on_commit_false`: regex `async_sessionmaker\([^)]*expire_on_commit\s*=\s*False` matches in `src/bet_maker/infrastructure/db/engine.py`.
    - Test 4 `test_dockerfile_exec_form_cmd`: regex `^CMD \[` (multiline) matches in `Dockerfile`; at least one CMD line exists; no CMD line in shell form (`CMD <unquoted-command>`).
    - Test 5 `test_dockerfile_pinned_python_bookworm`: substring `3.10-slim-bookworm` present in `Dockerfile`.
    - Test 6 `test_pythonunbuffered_set`: substring `PYTHONUNBUFFERED=1` (or `PYTHONUNBUFFERED = 1` with optional whitespace) present in `Dockerfile`.
    - Test 7 `test_durable_queue_and_exchange`: regex `RabbitQueue\([^)]*durable\s*=\s*True` AND regex `RabbitExchange\([^)]*durable\s*=\s*True` both match in `src/bet_maker/entrypoints/messaging.py`.
  </behavior>
  <action>
    Create `tests/audit/__init__.py` with single-line content:
    ```python
    # Phase 7 D-19: static-audit test package for "Looks Done But Isn't" checklist.
    ```

    Create `tests/audit/test_static.py` with the following 7 tests verbatim:

    ```python
    """Phase 7 D-19 static audit tests.

    Each test asserts a single ``Looks Done But Isn't`` invariant from
    ``.planning/research/PITFALLS.md``. The tests are pure file-content checks
    (``Path.read_text()`` + regex/substring) so they run in CI without spinning
    up Docker, RabbitMQ, or PostgreSQL.

    A failing test here means a refactor silently undid a Phase 1-6 invariant
    (e.g. someone re-formatted ``@router.subscriber(...)`` and dropped
    ``ack_policy=AckPolicy.MANUAL``). The grep-style style is deliberate:
    Pitfall 6 (RESEARCH.md) warns formatting drift can break a regex, so the
    patterns anchor on stable substrings rather than full multi-line shapes.
    """

    from __future__ import annotations

    import re
    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parents[2]
    SRC = REPO_ROOT / "src"


    def test_subscribers_have_manual_ack() -> None:
        """R1 / F1: every @router.subscriber must declare ack_policy=AckPolicy.MANUAL.

        Default AckPolicy.REJECT_ON_ERROR would silently drop messages on
        any handler exception — breaks the Core Value invariant (no stuck PENDING bets).
        """
        src = (SRC / "bet_maker" / "entrypoints" / "messaging.py").read_text()
        subscribers = re.findall(r"@router\.subscriber\s*\(", src)
        manual_ack_kwargs = re.findall(r"ack_policy\s*=\s*AckPolicy\.MANUAL", src)
        assert subscribers, "no @router.subscriber decorator found — wrong file?"
        assert len(subscribers) == len(manual_ack_kwargs), (
            f"{len(subscribers)} @router.subscriber decorators found, "
            f"but only {len(manual_ack_kwargs)} declare "
            f"ack_policy=AckPolicy.MANUAL — see ARCHITECTURE.md R1/F1"
        )


    def test_repositories_use_for_update_skip_locked() -> None:
        """R3: BetRepository.get_pending_locked must use with_for_update(skip_locked=True).

        The row lock plus skip_locked=True is what makes consumer + reconciler
        concurrent settle idempotent against the same event_id.
        """
        src = (SRC / "bet_maker" / "repositories" / "bets.py").read_text()
        assert "with_for_update(skip_locked=True)" in src, (
            "BetRepository.get_pending_locked must use "
            "with_for_update(skip_locked=True) — see ARCHITECTURE.md R3."
        )


    def test_async_sessionmaker_expire_on_commit_false() -> None:
        """A1 (Pitfall): async_sessionmaker must declare expire_on_commit=False.

        Without this, any access to ORM attributes after commit raises
        MissingGreenlet (the async session would try to lazy-reload, which
        requires greenlet). Plan 03-07 place_bet interactor depends on this.
        """
        src = (SRC / "bet_maker" / "infrastructure" / "db" / "engine.py").read_text()
        assert re.search(
            r"async_sessionmaker\s*\([^)]*expire_on_commit\s*=\s*False",
            src,
            re.DOTALL,
        ), (
            "async_sessionmaker must declare expire_on_commit=False — "
            "see ARCHITECTURE.md A1."
        )


    def test_dockerfile_exec_form_cmd() -> None:
        """R11 / D-04: Dockerfile CMD must be in exec form (JSON array).

        Exec-form CMD passes SIGTERM directly to the process; shell-form
        CMD (without brackets) wraps in /bin/sh which traps SIGTERM and
        forces docker to SIGKILL after stop_grace_period.
        """
        src = (REPO_ROOT / "Dockerfile").read_text()
        cmd_lines = [
            line for line in src.splitlines() if line.lstrip().startswith("CMD")
        ]
        assert cmd_lines, "Dockerfile has no CMD line"
        for line in cmd_lines:
            assert re.match(r"\s*CMD\s*\[", line), (
                f"non-exec-form CMD found: {line!r} — "
                "use CMD [\"python\", \"...\"] not CMD python ..."
            )


    def test_dockerfile_pinned_python_bookworm() -> None:
        """D-20: Dockerfile must pin python:3.10-slim-bookworm.

        Rolling tag 3.10-slim resolves to trixie (since May 2026) which
        ships glibc/openssl changes that may break asyncpg wheels.
        """
        src = (REPO_ROOT / "Dockerfile").read_text()
        assert "3.10-slim-bookworm" in src, (
            "Dockerfile must pin python:3.10-slim-bookworm explicitly "
            "(not rolling 3.10-slim) — see CLAUDE.md Stack Patterns."
        )


    def test_pythonunbuffered_set() -> None:
        """D-04: PYTHONUNBUFFERED=1 must be set so stdout flushes immediately.

        Without this, structlog logs are buffered in Docker and only appear
        after the process exits — invisible during steady-state run.
        """
        src = (REPO_ROOT / "Dockerfile").read_text()
        assert re.search(r"PYTHONUNBUFFERED\s*=\s*1", src), (
            "Dockerfile must declare PYTHONUNBUFFERED=1."
        )


    def test_durable_queue_and_exchange() -> None:
        """R4 / R10: RabbitQueue and RabbitExchange must declare durable=True.

        Non-durable queues/exchanges are deleted on RabbitMQ restart and
        silently lose the EventFinishedMessage stream. Combined with named
        volume on /var/lib/rabbitmq, durability is what makes the stack
        survive a broker restart.
        """
        src = (SRC / "bet_maker" / "entrypoints" / "messaging.py").read_text()
        assert re.search(
            r"RabbitQueue\([^)]*durable\s*=\s*True", src, re.DOTALL
        ), "RabbitQueue must declare durable=True — see ARCHITECTURE.md R4/R10."
        assert re.search(
            r"RabbitExchange\([^)]*durable\s*=\s*True", src, re.DOTALL
        ), "RabbitExchange must declare durable=True — see ARCHITECTURE.md R4/R10."
    ```

    No async, no fixtures, no `client`. Plain `def test_...()` functions — pytest collects them under `asyncio_mode = "auto"` without issue.

    Run `uv run pytest -q tests/audit/test_static.py -v` — all 7 tests must pass.
    Run `uv run mypy tests/audit/test_static.py` — should pass per existing pyproject override `[[tool.mypy.overrides]] module = ["tests.*"]; disallow_untyped_defs = false` (D-14). If a strict-mode error occurs, fix with minimal type annotation (do NOT add `# type: ignore`).
    Run `uv run ruff check tests/audit/`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/audit/test_static.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/audit/__init__.py` exists (any content, including empty)
    - File `tests/audit/test_static.py` exists, `grep -c "^def test_" tests/audit/test_static.py` returns 7
    - All 7 tests pass: `uv run pytest -q tests/audit/test_static.py` shows `7 passed`
    - `grep -c "REPO_ROOT" tests/audit/test_static.py` ≥ 7 (each test uses REPO_ROOT)
    - `grep -c "Path(__file__).resolve().parents\[2\]" tests/audit/test_static.py` returns 1 (REPO_ROOT calc — single source)
    - `uv run mypy tests/audit/test_static.py` passes (under tests override — should be clean even without strict)
    - `uv run ruff check tests/audit/` shows no issues
    - No `# type: ignore` in `tests/audit/test_static.py` (per D-12 — even though tests have looser override, this new file should be clean)
  </acceptance_criteria>
  <done>tests/audit/ package created with 7 passing static-audit tests; mypy/ruff clean; ready for audit-table reference in plan 07-09.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q tests/audit/` — 7 passed
- `uv run pytest -q` — full suite + 7 new tests green
- `uv run mypy src tests/audit` — zero errors
- `uv run ruff check tests/audit/ && uv run ruff format --check tests/audit/` — no issues
- Coverage check: `uv run pytest -q --cov --cov-fail-under=85` — still green (new test files don't affect src coverage)
</verification>

<success_criteria>
- 7 static-audit tests pass against current code-base (matching the `verified` status in 18-item evidence map)
- Each test names a Pitfall ID / decision in its docstring for traceability
- Regex anchors on stable substrings (per Pitfall 6) — no fragile multi-line shapes
- No emojis, no `# type: ignore` (per CLAUDE.md)
- Plan 07-09 can reference test IDs like `tests/audit/test_static.py::test_subscribers_have_manual_ack` in 07-AUDIT.md Evidence column
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-07-SUMMARY.md` recording:
- 7 test IDs (verbatim node IDs) for referencing in 07-AUDIT.md
- Pytest output (all 7 passed)
- mypy/ruff status
</output>
