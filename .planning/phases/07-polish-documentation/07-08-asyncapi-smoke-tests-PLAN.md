---
phase: 07-polish-documentation
plan: 08
type: execute
wave: 1
depends_on: [01]
files_modified:
  - tests/bet_maker/test_asyncapi_smoke.py
  - tests/line_provider/test_asyncapi_smoke.py
autonomous: true
requirements: [DOC-01]
must_haves:
  truths:
    - "GET /asyncapi on bet-maker returns 200 (Pitfall 4 — FastStream RabbitRouter must be registered via app.include_router)"
    - "GET /asyncapi on line-provider returns 200 (publisher-side AsyncAPI doc)"
    - "Smoke tests use existing session-scoped `client: AsyncClient` fixtures (no new fixtures)"
    - "Response content-type is HTML or JSON (FastStream may serve either; accept both per PATTERNS.md caveat)"
  artifacts:
    - path: "tests/bet_maker/test_asyncapi_smoke.py"
      provides: "Smoke test asserting /asyncapi exposed by bet-maker FastStream RabbitRouter"
      exports: ["TestAsyncAPISmoke"]
    - path: "tests/line_provider/test_asyncapi_smoke.py"
      provides: "Smoke test asserting /asyncapi exposed by line-provider FastStream RabbitRouter"
  key_links:
    - from: "tests/bet_maker/test_asyncapi_smoke.py::TestAsyncAPISmoke"
      to: "src/bet_maker/app.py::build_app::app.include_router(rabbit_router)"
      via: "GET /asyncapi via httpx.AsyncClient over ASGITransport"
      pattern: "client.get\\(\"/asyncapi\"\\)"
    - from: "tests/line_provider/test_asyncapi_smoke.py"
      to: "src/line_provider/app.py::build_app::app.include_router(rabbit_router)"
      via: "GET /asyncapi via httpx.AsyncClient over ASGITransport"
      pattern: "client.get\\(\"/asyncapi\"\\)"
---

<objective>
Verify FastStream's default `/asyncapi` endpoint is exposed on both services per CONTEXT.md D-10 + RESEARCH.md Pitfall 4. Each service has `app.include_router(rabbit_router)` in `build_app()` (verified by existing code) — but a regression that drops or comments that line would silently strip the endpoint without any unit test catching it. These smoke tests close that gap.

Per PATTERNS.md / RESEARCH.md caveat: FastStream's `/asyncapi` may serve HTML (AsyncAPI rendering UI) or JSON depending on version; the smoke test asserts 200 + non-empty body + content-type contains "html" or "json".

Output: 2 new test files, one per service. Each is a single test reusing the existing session-scoped `client: AsyncClient` fixture from `tests/{bet_maker,line_provider}/conftest.py`.
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
<!-- Existing fixtures we reuse — see read_first below -->

tests/bet_maker/conftest.py — `client` fixture (session-scoped, ASGITransport + LifespanManager):
```python
@pytest.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Session-scoped async HTTP client bound to lifespan-aware app."""
    ...
```

tests/line_provider/conftest.py — `client` fixture (same pattern, plain-async-def style):
```python
@pytest.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Session-scoped async HTTP client bound to the lifespan-aware app fixture."""
    ...
```

bet-maker test style: `@pytest.mark.asyncio(loop_scope="session")` on class (see test_health.py line 19).
line-provider test style: plain `async def test_...(client)` (see test_health.py line 14).
</interfaces>
</context>

<threat_model>
N/A — smoke tests only issue a single GET request to an existing FastStream-managed endpoint. No payload, no auth, no side effects.
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: bet-maker AsyncAPI smoke test</name>
  <files>tests/bet_maker/test_asyncapi_smoke.py</files>
  <read_first>
    - tests/bet_maker/conftest.py (locate the `client` fixture and its scope)
    - tests/bet_maker/test_health.py (mirror @pytest.mark.asyncio(loop_scope="session") class style)
    - src/bet_maker/app.py (verify `app.include_router(rabbit_router)` is present)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → tests/bet_maker/test_asyncapi_smoke.py)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (Pitfall 4 + Pattern 3 — content-type may be HTML or JSON)
  </read_first>
  <behavior>
    - Test `test_asyncapi_endpoint_returns_200`: GET /asyncapi returns status 200.
    - The response body is non-empty (`response.content` is not zero bytes).
    - The response `Content-Type` header contains either `html` or `json` (FastStream version-dependent rendering).
  </behavior>
  <action>
    Create `tests/bet_maker/test_asyncapi_smoke.py` with the following content verbatim:

    ```python
    """Smoke test: /asyncapi endpoint is exposed by FastStream RabbitRouter.

    D-10 / Pitfall 4 (RESEARCH.md): FastStream RabbitRouter auto-registers
    /asyncapi at its default URL when app.include_router(router) is called.
    A regression that comments out the include_router line would silently
    strip the endpoint — this smoke test catches that.

    Content-type may be HTML (AsyncAPI rendering UI) or JSON depending on
    FastStream version; both are acceptable. The assertion is on status
    code + non-empty body + content-type contains "html" or "json".
    """

    from __future__ import annotations

    import pytest
    from httpx import AsyncClient


    @pytest.mark.asyncio(loop_scope="session")
    class TestAsyncAPISmoke:
        """AsyncAPI endpoint smoke test — session loop for session-scoped client."""

        async def test_asyncapi_endpoint_returns_200(
            self, client: AsyncClient
        ) -> None:
            """D-10: /asyncapi must return 200 with non-empty body."""
            response = await client.get("/asyncapi")
            assert response.status_code == 200, (
                f"GET /asyncapi returned {response.status_code} — "
                "FastStream RabbitRouter not wired? "
                "See src/bet_maker/app.py::build_app — app.include_router(rabbit_router) "
                "is required."
            )
            assert response.content, "/asyncapi returned empty body"
            content_type = response.headers.get("content-type", "")
            assert any(t in content_type for t in ("html", "json")), (
                f"/asyncapi content-type not html or json: {content_type!r}"
            )
    ```

    Run `uv run pytest -q tests/bet_maker/test_asyncapi_smoke.py -v` — single test must pass.
    Run `uv run mypy tests/bet_maker/test_asyncapi_smoke.py` — passes under tests override (D-14).
    Run `uv run ruff check tests/bet_maker/test_asyncapi_smoke.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/bet_maker/test_asyncapi_smoke.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/bet_maker/test_asyncapi_smoke.py` exists
    - `grep -c "^class TestAsyncAPISmoke" tests/bet_maker/test_asyncapi_smoke.py` returns 1
    - `grep -c "async def test_asyncapi_endpoint_returns_200" tests/bet_maker/test_asyncapi_smoke.py` returns 1
    - `grep -c "@pytest.mark.asyncio(loop_scope=\"session\")" tests/bet_maker/test_asyncapi_smoke.py` returns 1
    - `grep -c "client.get(\"/asyncapi\")" tests/bet_maker/test_asyncapi_smoke.py` returns 1
    - `uv run pytest -q tests/bet_maker/test_asyncapi_smoke.py` shows 1 passed
    - `uv run mypy tests/bet_maker/test_asyncapi_smoke.py` passes
    - `uv run ruff check tests/bet_maker/test_asyncapi_smoke.py` shows no issues
    - No `# type: ignore`
  </acceptance_criteria>
  <done>bet-maker /asyncapi smoke test passes; ready for audit-table reference in plan 07-09.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: line-provider AsyncAPI smoke test</name>
  <files>tests/line_provider/test_asyncapi_smoke.py</files>
  <read_first>
    - tests/line_provider/conftest.py (locate the `client` fixture and verify session-scope)
    - tests/line_provider/test_health.py (mirror plain-async-def function style, no class wrapper, no explicit @pytest.mark.asyncio — asyncio_mode=auto handles it)
    - src/line_provider/app.py (verify `app.include_router(rabbit_router)` is present)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → tests/line_provider/test_asyncapi_smoke.py)
  </read_first>
  <behavior>
    - Test `test_asyncapi_endpoint_returns_200`: GET /asyncapi on line-provider returns status 200, non-empty body, content-type contains html or json.
  </behavior>
  <action>
    Create `tests/line_provider/test_asyncapi_smoke.py` with the following content verbatim:

    ```python
    """Smoke test: line-provider /asyncapi endpoint exposed by FastStream RabbitRouter.

    D-10 (publisher side): line-provider's RabbitRouter (publisher-only —
    no @router.subscriber) still registers /asyncapi to document the publish
    contract. A regression that comments out app.include_router(rabbit_router)
    in src/line_provider/app.py would silently strip the endpoint — this
    smoke test catches that.

    Content-type may be HTML or JSON depending on FastStream version; both are
    acceptable (Pitfall 4 / PATTERNS.md caveat).
    """

    from __future__ import annotations

    from httpx import AsyncClient


    async def test_asyncapi_endpoint_returns_200(client: AsyncClient) -> None:
        """D-10: /asyncapi available on line-provider for AsyncAPI publish-contract docs."""
        response = await client.get("/asyncapi")
        assert response.status_code == 200, (
            f"GET /asyncapi returned {response.status_code} — "
            "FastStream RabbitRouter not wired? "
            "See src/line_provider/app.py::build_app — app.include_router(rabbit_router) "
            "is required."
        )
        assert response.content, "/asyncapi returned empty body"
        content_type = response.headers.get("content-type", "")
        assert any(t in content_type for t in ("html", "json")), (
            f"/asyncapi content-type not html or json: {content_type!r}"
        )
    ```

    Run `uv run pytest -q tests/line_provider/test_asyncapi_smoke.py -v` — single test must pass.
    Run `uv run mypy tests/line_provider/test_asyncapi_smoke.py` — passes under tests override.
    Run `uv run ruff check tests/line_provider/test_asyncapi_smoke.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/line_provider/test_asyncapi_smoke.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/line_provider/test_asyncapi_smoke.py` exists
    - `grep -c "^async def test_asyncapi_endpoint_returns_200" tests/line_provider/test_asyncapi_smoke.py` returns 1
    - `grep -c "client.get(\"/asyncapi\")" tests/line_provider/test_asyncapi_smoke.py` returns 1
    - File has NO class wrapper (`grep -c "^class " tests/line_provider/test_asyncapi_smoke.py` returns 0 — plain async def style mirroring line-provider test_health.py)
    - `uv run pytest -q tests/line_provider/test_asyncapi_smoke.py` shows 1 passed
    - `uv run mypy tests/line_provider/test_asyncapi_smoke.py` passes
    - `uv run ruff check tests/line_provider/test_asyncapi_smoke.py` shows no issues
  </acceptance_criteria>
  <done>line-provider /asyncapi smoke test passes; ready for audit-table reference in plan 07-09.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q tests/bet_maker/test_asyncapi_smoke.py tests/line_provider/test_asyncapi_smoke.py` — 2 passed
- Full suite + new tests: `uv run pytest -q` — green
- `uv run mypy src tests` — zero errors
- `uv run ruff check . && uv run ruff format --check .` — zero issues
</verification>

<success_criteria>
- Two new test files, one smoke test each, both passing
- bet-maker uses class wrapper + `@pytest.mark.asyncio(loop_scope="session")` (mirrors local test convention)
- line-provider uses plain async def (mirrors local test convention)
- Both reuse existing session-scoped `client: AsyncClient` fixture — no new fixtures
- No `# type: ignore`, no emojis
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-08-SUMMARY.md` recording:
- 2 test node IDs (verbatim) for referencing in 07-AUDIT.md
- Pytest output (2 passed)
- Notes on content-type observed during test run (html vs json — informational only)
- mypy/ruff status
</output>
