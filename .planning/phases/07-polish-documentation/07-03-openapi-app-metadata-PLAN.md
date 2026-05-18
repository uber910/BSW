---
phase: 07-polish-documentation
plan: 03
type: execute
wave: 1
depends_on: [01]
files_modified:
  - src/line_provider/app.py
  - src/bet_maker/app.py
autonomous: true
requirements: [DOC-01]
must_haves:
  truths:
    - "FastAPI(...) call in line_provider/app.py has a description= kwarg with non-empty Russian one-sentence text"
    - "FastAPI(...) call in bet_maker/app.py has a description= kwarg with non-empty Russian one-sentence text"
    - "Both descriptions reference AsyncAPI endpoint (/asyncapi) per D-10"
    - "title= and version= remain unchanged (already present)"
    - "No new dependencies, no behaviour change — only OpenAPI metadata"
  artifacts:
    - path: "src/line_provider/app.py"
      provides: "FastAPI app factory with description= populated"
      contains: "description="
    - path: "src/bet_maker/app.py"
      provides: "FastAPI app factory with description= populated"
      contains: "description="
  key_links:
    - from: "src/line_provider/app.py::build_app::FastAPI(...)"
      to: "OpenAPI /docs description block"
      via: "FastAPI auto-renders description on /docs Swagger UI"
      pattern: "FastAPI\\([\\s\\S]*?description="
    - from: "src/bet_maker/app.py::build_app::FastAPI(...)"
      to: "OpenAPI /docs description block"
      via: "FastAPI auto-renders description on /docs Swagger UI"
      pattern: "FastAPI\\([\\s\\S]*?description="
---

<objective>
Add `description=` kwarg to both `FastAPI(...)` constructors in `build_app()` per CONTEXT.md D-06. One Russian sentence per service stating what the service does + AsyncAPI endpoint URL (D-10). `contact=` and `license_info=` deliberately omitted per D-06 ("Claude's Discretion — можно опустить, не критично"; license_info omitted because there is no public license for the test-task).

Purpose: when reviewer opens `:8000/docs` / `:8001/docs`, the Swagger UI title block is no longer empty.

Output: 2 modified files, +description= kwarg on each.
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
<!-- Current state of both files (verbatim) -->

src/line_provider/app.py:
```python
def build_app() -> FastAPI:
    app = FastAPI(
        title="line-provider",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
```

src/bet_maker/app.py:
```python
def build_app() -> FastAPI:
    app = FastAPI(
        title="bet-maker",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(bets.router)
    app.include_router(events.router)
    app.include_router(rabbit_router)
    return app
```

Order of kwargs MUST be: `title`, `description`, `version`, `lifespan` — keeps FastAPI's canonical ordering.
</interfaces>
</context>

<threat_model>
N/A — documentation phase; no new attack surface. OpenAPI description strings contain only static metadata, no f-strings, no user input.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Add description= to line_provider FastAPI app factory</name>
  <files>src/line_provider/app.py</files>
  <read_first>
    - src/line_provider/app.py (current state — pattern + lines to edit)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → src/{line_provider,bet_maker}/app.py)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-06)
  </read_first>
  <action>
    Edit `src/line_provider/app.py` using the Edit tool. Replace the existing `FastAPI(...)` block exactly:

    BEFORE:
    ```python
        app = FastAPI(
            title="line-provider",
            version="0.1.0",
            lifespan=lifespan,
        )
    ```

    AFTER:
    ```python
        app = FastAPI(
            title="line-provider",
            description=(
                "Источник событий и их статусов. Хранит события в памяти, "
                "публикует EventFinishedMessage в RabbitMQ exchange `bsw.events` "
                "при переходе в FINISHED_WIN / FINISHED_LOSE. "
                "AsyncAPI: /asyncapi."
            ),
            version="0.1.0",
            lifespan=lifespan,
        )
    ```

    Per CLAUDE.md "no emojis in docs and code": description contains plain Russian text + backticks for technical identifiers only. No emojis.

    Per D-06: do NOT add `contact=` or `license_info=`.

    After edit:
    - `uv run mypy src/line_provider/app.py` — must pass zero errors.
    - `uv run ruff check src/line_provider/app.py && uv run ruff format --check src/line_provider/app.py` — must pass.
    - `uv run pytest -q tests/line_provider/` — full LP suite must remain green (no behaviour change).
  </action>
  <verify>
    <automated>uv run pytest -q tests/line_provider/</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "description=" src/line_provider/app.py` returns 1
    - `grep -F "AsyncAPI: /asyncapi" src/line_provider/app.py` returns 1 line (description mentions endpoint)
    - `grep -F "EventFinishedMessage" src/line_provider/app.py` returns 1 line (description mentions publish contract)
    - `grep -c "contact=" src/line_provider/app.py` returns 0 (deliberately omitted per D-06)
    - `grep -c "license_info=" src/line_provider/app.py` returns 0 (deliberately omitted per D-06)
    - `uv run mypy src/line_provider/app.py` shows zero errors
    - `uv run ruff check src/line_provider/app.py` shows no issues
    - `uv run pytest -q tests/line_provider/` shows all tests passing (no behaviour change)
  </acceptance_criteria>
  <done>FastAPI line-provider description= populated with Russian one-sentence summary + AsyncAPI URL; tests still green; mypy/ruff clean.</done>
</task>

<task type="auto">
  <name>Task 2: Add description= to bet_maker FastAPI app factory</name>
  <files>src/bet_maker/app.py</files>
  <read_first>
    - src/bet_maker/app.py (current state)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (same pattern — bet_maker version)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-06)
  </read_first>
  <action>
    Edit `src/bet_maker/app.py` using the Edit tool. Replace the existing `FastAPI(...)` block exactly:

    BEFORE:
    ```python
        app = FastAPI(
            title="bet-maker",
            version="0.1.0",
            lifespan=lifespan,
        )
    ```

    AFTER:
    ```python
        app = FastAPI(
            title="bet-maker",
            description=(
                "Сервис приёма и истории ставок. Хранит ставки в PostgreSQL, "
                "получает финальные статусы событий из RabbitMQ "
                "(queue `bet_maker.events.finished`), reconciler как защита "
                "от потерянных сообщений. AsyncAPI: /asyncapi."
            ),
            version="0.1.0",
            lifespan=lifespan,
        )
    ```

    Per CLAUDE.md "no emojis in docs and code": plain Russian + backticks only.

    Per D-06: do NOT add `contact=` or `license_info=`.

    After edit:
    - `uv run mypy src/bet_maker/app.py` — must pass zero errors.
    - `uv run ruff check src/bet_maker/app.py && uv run ruff format --check src/bet_maker/app.py` — must pass.
    - `uv run pytest -q tests/bet_maker/` — full BM suite must remain green.
  </action>
  <verify>
    <automated>uv run pytest -q tests/bet_maker/</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "description=" src/bet_maker/app.py` returns 1
    - `grep -F "AsyncAPI: /asyncapi" src/bet_maker/app.py` returns 1 line
    - `grep -F "bet_maker.events.finished" src/bet_maker/app.py` returns 1 line (description mentions consumer queue)
    - `grep -F "reconciler" src/bet_maker/app.py` returns 1 line (description mentions reconciler)
    - `grep -c "contact=" src/bet_maker/app.py` returns 0
    - `grep -c "license_info=" src/bet_maker/app.py` returns 0
    - `uv run mypy src/bet_maker/app.py` shows zero errors
    - `uv run ruff check src/bet_maker/app.py` shows no issues
    - `uv run pytest -q tests/bet_maker/` shows all tests passing
  </acceptance_criteria>
  <done>FastAPI bet-maker description= populated; tests still green; mypy/ruff clean.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q` — full suite green (no behaviour change)
- `uv run mypy src` — zero errors
- `uv run ruff check . && uv run ruff format --check .` — zero issues
- Manually: starting either service and opening `:8000/docs` / `:8001/docs` shows the description text in the Swagger UI header (cannot be automated in CI, but is the visible reviewer outcome of this plan)
</verification>

<success_criteria>
- Both `app.py` files have `description=` kwarg in their `FastAPI(...)` call.
- Each description is a single Russian sentence mentioning what the service does + `/asyncapi` endpoint.
- No `contact=` / `license_info=` added (deliberate per D-06).
- Full test suite green; mypy strict zero errors; ruff clean.
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-03-SUMMARY.md` recording:
- Diff (before/after) for both files
- Test/mypy/ruff status
- Description text verbatim (so plan 07-10 can reference it in README §Architecture if desired)
</output>
