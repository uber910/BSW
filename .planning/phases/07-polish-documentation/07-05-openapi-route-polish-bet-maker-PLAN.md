---
phase: 07-polish-documentation
plan: 05
type: execute
wave: 2
depends_on: [02]
files_modified:
  - src/bet_maker/entrypoints/api/bets.py
  - src/bet_maker/entrypoints/api/events.py
  - src/bet_maker/entrypoints/api/health.py
autonomous: true
requirements: [DOC-01]
must_haves:
  truths:
    - "Every bet-maker route decorator has summary=\"...\" (one-line description)"
    - "POST /bet has responses={422: ErrorDetail, 503: ErrorDetail} declaration"
    - "POST /bet has Body(openapi_examples={...}) with concrete UUID + amount example values"
    - "GET /bet/{bet_id} has responses={404: ErrorDetail} declaration"
    - "GET /events (proxy) has responses={503: ErrorDetail} declaration"
    - "GET /health has responses={503: {description-only, no model=}} declaration (multi-key checks payload, not flat ErrorDetail shape)"
    - "All routes still raise HTTPException with same status codes / detail strings — no behaviour change"
    - "ErrorDetail imported via `from bet_maker.schemas.errors import ErrorDetail` in bets.py + events.py"
  artifacts:
    - path: "src/bet_maker/entrypoints/api/bets.py"
      provides: "3 routes (POST /bet, GET /bets, GET /bet/{id}) with OpenAPI metadata polish"
      contains: "summary="
    - path: "src/bet_maker/entrypoints/api/events.py"
      provides: "1 route (GET /events) with OpenAPI metadata polish"
      contains: "summary="
    - path: "src/bet_maker/entrypoints/api/health.py"
      provides: "GET /health with summary + 503 description block"
      contains: "summary="
  key_links:
    - from: "src/bet_maker/entrypoints/api/bets.py"
      to: "src/bet_maker/schemas/errors.py::ErrorDetail"
      via: "import statement; used in responses={...} on POST /bet, GET /bet/{id}"
      pattern: "from bet_maker.schemas.errors import ErrorDetail"
    - from: "src/bet_maker/entrypoints/api/events.py"
      to: "src/bet_maker/schemas/errors.py::ErrorDetail"
      via: "import statement; used in responses={...} on GET /events"
      pattern: "from bet_maker.schemas.errors import ErrorDetail"
---

<objective>
Apply OpenAPI metadata polish to all bet-maker routes per CONTEXT.md D-07 + D-08. Add `summary=`, `responses={...}` mapping non-pydantic 4xx/5xx branches to `ErrorDetail`, and `Body(..., openapi_examples=...)` on POST bodies with concrete example values mirroring P3 integration test fixtures.

**Key nuance per Pitfall 5 (RESEARCH.md):** The 422 on POST /bet has TWO sources — (a) Pydantic body validation (e.g. `amount=10.123`) which returns FastAPI's auto `HTTPValidationError` shape, and (b) `EventNotBettable` from the interactor which is mapped to `HTTPException(422, detail="event {id} is not bettable: {reason}")`. Per D-07, we declare 422 = ErrorDetail in `responses=` for the EventNotBettable branch; FastAPI's auto-422 for pydantic validation co-exists in the OpenAPI schema (FastAPI auto-registers HTTPValidationError separately). Both will appear in OpenAPI under 422 with different schemas — Swagger UI handles `oneOf` fine.

**No handler-body change.** Existing exception ladder (LineProviderUnavailable → 503; EventNotBettable → 422; bet-not-found → 404) stays verbatim.

Output: 3 modified files; full bet-maker test suite (~242 tests) still green; mypy strict zero errors.
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
<!-- Current bet-maker routes (verbatim) — see read_first below. Polish ADDS metadata only. -->

Per CONTEXT.md D-07 + Pattern 1 from RESEARCH.md / PATTERNS.md, the exact mapping:

- POST /bet              → summary + 422 (ErrorDetail, EventNotBettable branch) + 503 (ErrorDetail, LineProviderUnavailable) + Body(openapi_examples)
- GET  /bets             → summary only (no error branch)
- GET  /bet/{bet_id}     → summary + 404 (ErrorDetail, bet-not-found)
- GET  /events  (proxy)  → summary + 503 (ErrorDetail, LineProviderUnavailable)
- GET  /health           → summary + 503 description-only (multi-key checks dict, NOT ErrorDetail shape — see Pitfall 5)

ErrorDetail import per file:
```python
from bet_maker.schemas.errors import ErrorDetail
```

FastAPI Body(openapi_examples) on `POST /bet`:
```python
openapi_examples={
    "happy": {"summary": "Place a valid bet", "value": {"event_id": "00...01", "amount": "10.00"}},
    "bad_decimal": {"summary": "Invalid — too many decimal places", "value": {"event_id": "00...01", "amount": "10.123"}},
}
```
</interfaces>
</context>

<threat_model>
N/A — documentation phase. All `summary`/`description` strings are static. `responses={...}` declarations affect OpenAPI schema, not runtime. The existing exception ladder (D-08 in P4 plan 04-09 — `LineProviderUnavailable → 503` before `EventNotBettable → 422`) is unchanged.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Polish OpenAPI metadata on bet-maker bets routes</name>
  <files>src/bet_maker/entrypoints/api/bets.py</files>
  <read_first>
    - src/bet_maker/entrypoints/api/bets.py (current state — 3 routes)
    - src/bet_maker/schemas/errors.py (must exist from plan 07-02)
    - src/bet_maker/schemas/bets.py (BetCreate field names — amount: Decimal, event_id: UUID)
    - tests/bet_maker/test_bet_routes.py (existing integration tests — happy-path UUID + amount values)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → src/bet_maker/entrypoints/api/bets.py)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (Pitfall 5)
  </read_first>
  <action>
    Edit `src/bet_maker/entrypoints/api/bets.py` using the Edit tool with the following targeted changes:

    **Change A: Imports** — Replace the existing FastAPI import line:
    ```python
    from fastapi import APIRouter, HTTPException, status
    ```
    with:
    ```python
    from fastapi import APIRouter, Body, HTTPException, status
    ```
    Add a new import line near the other bet_maker imports:
    ```python
    from bet_maker.schemas.errors import ErrorDetail
    ```

    **Change B: POST /bet decorator + signature** — Replace exactly:

    BEFORE:
    ```python
    @router.post(
        "/bet",
        status_code=status.HTTP_201_CREATED,
        response_model=BetRead,
    )
    async def post_bet(
        body: BetCreate,
        uow: UoWDep,
        event_lookup: EventLookupDep,
    ) -> BetRead:
    ```

    AFTER:
    ```python
    @router.post(
        "/bet",
        status_code=status.HTTP_201_CREATED,
        response_model=BetRead,
        summary="Place a bet on a bettable event",
        responses={
            status.HTTP_422_UNPROCESSABLE_ENTITY: {
                "model": ErrorDetail,
                "description": (
                    "Event is not bettable: event not found, "
                    "deadline passed, or event not active. "
                    "Pydantic body validation 422 (extra fields, bad Decimal) "
                    "is also possible and uses FastAPI's HTTPValidationError shape."
                ),
            },
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ErrorDetail,
                "description": "line-provider unreachable after retries.",
            },
        },
    )
    async def post_bet(
        uow: UoWDep,
        event_lookup: EventLookupDep,
        body: BetCreate = Body(
            openapi_examples={
                "happy": {
                    "summary": "Place a valid bet on a NEW non-expired event",
                    "value": {
                        "event_id": "00000000-0000-0000-0000-000000000001",
                        "amount": "10.00",
                    },
                },
                "bad_decimal": {
                    "summary": "Invalid amount — too many decimal places (returns 422)",
                    "value": {
                        "event_id": "00000000-0000-0000-0000-000000000001",
                        "amount": "10.123",
                    },
                },
            },
        ),
    ) -> BetRead:
    ```

    Note: parameter order is `uow, event_lookup, body` — non-default Annotated deps first, then `body: BetCreate = Body(...)` last (mypy strict requires this ordering when `Body(...)` provides a default).

    **Keep the existing docstring and try/except handler body verbatim.** Do NOT remove the LineProviderUnavailable → 503 + EventNotBettable → 422 ladder; FastAPI surfaces the docstring as `description=` automatically.

    **Change C: GET /bets** — Replace exactly:

    BEFORE:
    ```python
    @router.get(
        "/bets",
        response_model=list[BetRead],
    )
    async def get_bets(session: SessionDep) -> list[BetRead]:
    ```

    AFTER:
    ```python
    @router.get(
        "/bets",
        response_model=list[BetRead],
        summary="List all bets (newest first)",
    )
    async def get_bets(session: SessionDep) -> list[BetRead]:
    ```

    **Change D: GET /bet/{bet_id}** — Replace exactly:

    BEFORE:
    ```python
    @router.get(
        "/bet/{bet_id}",
        response_model=BetRead,
    )
    async def get_bet(bet_id: UUID, session: SessionDep) -> BetRead:
    ```

    AFTER:
    ```python
    @router.get(
        "/bet/{bet_id}",
        response_model=BetRead,
        summary="Fetch single bet by id",
        responses={
            status.HTTP_404_NOT_FOUND: {
                "model": ErrorDetail,
                "description": "Bet with this bet_id does not exist.",
            },
        },
    )
    async def get_bet(bet_id: UUID, session: SessionDep) -> BetRead:
    ```

    Run `uv run pytest -q tests/bet_maker/test_bet_routes.py` — all P3+P4 bet-route tests must still pass.
    Run `uv run mypy src/bet_maker/entrypoints/api/bets.py` — zero errors.
    Run `uv run ruff check src/bet_maker/entrypoints/api/bets.py && uv run ruff format --check src/bet_maker/entrypoints/api/bets.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/bet_maker/test_bet_routes.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "summary=" src/bet_maker/entrypoints/api/bets.py` returns 3
    - `grep -c "responses={" src/bet_maker/entrypoints/api/bets.py` returns 2 (POST /bet, GET /bet/{id})
    - `grep -c "openapi_examples=" src/bet_maker/entrypoints/api/bets.py` returns 1 (POST /bet only)
    - `grep -c "from bet_maker.schemas.errors import ErrorDetail" src/bet_maker/entrypoints/api/bets.py` returns 1
    - `grep -c "ErrorDetail" src/bet_maker/entrypoints/api/bets.py` ≥ 4 (1 import + at least 3 model refs in responses)
    - `grep -F "00000000-0000-0000-0000-000000000001" src/bet_maker/entrypoints/api/bets.py` returns 2 lines (happy + bad_decimal examples)
    - `grep -F "10.123" src/bet_maker/entrypoints/api/bets.py` returns 1 line (bad_decimal example)
    - `grep -c "HTTP_503_SERVICE_UNAVAILABLE" src/bet_maker/entrypoints/api/bets.py` ≥ 2 (still raised + declared in responses)
    - `uv run pytest -q tests/bet_maker/test_bet_routes.py` shows all tests passing (LineProviderUnavailable→503 and EventNotBettable→422 ladder must still fire correctly)
    - `uv run mypy src/bet_maker/entrypoints/api/bets.py` shows zero errors
    - `uv run ruff check src/bet_maker/entrypoints/api/bets.py` shows no issues
  </acceptance_criteria>
  <done>POST /bet has summary + 422/503 ErrorDetail responses + Body(openapi_examples); GET /bets has summary; GET /bet/{id} has summary + 404 ErrorDetail; handler bodies unchanged; tests still green.</done>
</task>

<task type="auto">
  <name>Task 2: Polish OpenAPI metadata on bet-maker GET /events route</name>
  <files>src/bet_maker/entrypoints/api/events.py</files>
  <read_first>
    - src/bet_maker/entrypoints/api/events.py (current state — single route)
    - src/bet_maker/schemas/errors.py (from plan 07-02)
    - tests/bet_maker/test_events_routes.py (P4 integration tests — happy + 503 cases)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → src/bet_maker/entrypoints/api/events.py)
  </read_first>
  <action>
    Edit `src/bet_maker/entrypoints/api/events.py` using the Edit tool.

    **Change A: Imports** — Add ErrorDetail import after the existing `from bet_maker.schemas.events import EventRead` line:
    ```python
    from bet_maker.schemas.errors import ErrorDetail
    ```

    **Change B: GET /events decorator** — Replace exactly:

    BEFORE:
    ```python
    @router.get(
        "/events",
        response_model=list[EventRead],
    )
    async def get_events(http_client: LineProviderHttpClientDep) -> list[EventRead]:
    ```

    AFTER:
    ```python
    @router.get(
        "/events",
        response_model=list[EventRead],
        summary="List active events (proxied from line-provider)",
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "model": ErrorDetail,
                "description": "line-provider unreachable after retries.",
            },
        },
    )
    async def get_events(http_client: LineProviderHttpClientDep) -> list[EventRead]:
    ```

    Keep the existing docstring + try/except `LineProviderUnavailable → 503` handler verbatim.

    Run `uv run pytest -q tests/bet_maker/test_events_routes.py` — P4 6 tests must still pass.
    Run `uv run mypy src/bet_maker/entrypoints/api/events.py` — zero errors.
    Run `uv run ruff check src/bet_maker/entrypoints/api/events.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/bet_maker/test_events_routes.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "summary=\"List active events" src/bet_maker/entrypoints/api/events.py` returns 1
    - `grep -c "responses={" src/bet_maker/entrypoints/api/events.py` returns 1
    - `grep -c "HTTP_503_SERVICE_UNAVAILABLE" src/bet_maker/entrypoints/api/events.py` ≥ 2 (raise + declare)
    - `grep -c "from bet_maker.schemas.errors import ErrorDetail" src/bet_maker/entrypoints/api/events.py` returns 1
    - `uv run pytest -q tests/bet_maker/test_events_routes.py` shows all P4 events tests passing
    - `uv run mypy src/bet_maker/entrypoints/api/events.py` shows zero errors
    - `uv run ruff check src/bet_maker/entrypoints/api/events.py` shows no issues
  </acceptance_criteria>
  <done>GET /events has summary + 503 ErrorDetail response; handler body unchanged; P4 events tests still green.</done>
</task>

<task type="auto">
  <name>Task 3: Polish OpenAPI metadata on bet-maker /health route</name>
  <files>src/bet_maker/entrypoints/api/health.py</files>
  <read_first>
    - src/bet_maker/entrypoints/api/health.py (current state — 503-on-degraded handler)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (BM /health pattern — description-only, no `model=`, because 503 payload is multi-key dict, not ErrorDetail)
  </read_first>
  <action>
    Edit `src/bet_maker/entrypoints/api/health.py` using the Edit tool.

    **Change A: Decorator** — Replace exactly:

    BEFORE:
    ```python
    @router.get("/health")
    async def health(
        engine: EngineDep,
        broker: RabbitBrokerDep,
        reconciler_task: ReconciliationTaskDep,
    ) -> JSONResponse:
    ```

    AFTER:
    ```python
    @router.get(
        "/health",
        summary="Service health (PG + RMQ + consumer + reconciler)",
        responses={
            503: {
                "description": (
                    "Degraded — one of: postgres / rabbitmq / rabbitmq_consumer / "
                    "reconciler is down. Payload: "
                    "{status: 'degraded', checks: {postgres, rabbitmq, "
                    "rabbitmq_consumer, reconciler}}."
                ),
            },
        },
    )
    async def health(
        engine: EngineDep,
        broker: RabbitBrokerDep,
        reconciler_task: ReconciliationTaskDep,
    ) -> JSONResponse:
    ```

    **Critical (per PATTERNS.md line ~360):** The 503 response on /health does NOT use `"model": ErrorDetail` because the actual 503 payload is the multi-key `{"status": "degraded", "checks": {...}}` dict, not the flat `{"detail": "..."}` envelope. The 503 entry carries `description=` only.

    Keep the docstring and handler body verbatim.

    Run `uv run pytest -q tests/bet_maker/test_health.py` — P3+P5+P6 health tests (200 + 503 degraded scenarios) must still pass.
    Run `uv run mypy src/bet_maker/entrypoints/api/health.py` — zero errors.
    Run `uv run ruff check src/bet_maker/entrypoints/api/health.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/bet_maker/test_health.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "summary=\"Service health" src/bet_maker/entrypoints/api/health.py` returns 1
    - `grep -c "responses={" src/bet_maker/entrypoints/api/health.py` returns 1
    - `grep -c "\"model\"" src/bet_maker/entrypoints/api/health.py` returns 0 (no model= on 503 — payload is multi-key dict)
    - `grep -c "ErrorDetail" src/bet_maker/entrypoints/api/health.py` returns 0 (not used here)
    - `uv run pytest -q tests/bet_maker/test_health.py` shows all health tests passing
    - `uv run mypy src/bet_maker/entrypoints/api/health.py` shows zero errors
    - `uv run ruff check src/bet_maker/entrypoints/api/health.py` shows no issues
  </acceptance_criteria>
  <done>/health has summary + 503 description-only block (no model=); handler body unchanged; health tests still green.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q tests/bet_maker/` — full bet-maker suite green (~242 tests + the 6 ErrorDetail tests from plan 07-02 = ~248)
- `uv run mypy src` — zero errors
- `uv run ruff check . && uv run ruff format --check .` — zero issues
- Manually: `:8001/docs` shows summaries on every route, Try-it-out examples on POST /bet, 422/503/404 ErrorDetail schemas visible on `/bet`, 503 description-only on `/health`
</verification>

<success_criteria>
- POST /bet has 422 + 503 ErrorDetail responses + Body(openapi_examples) with happy + bad_decimal examples
- GET /bets has summary only
- GET /bet/{id} has summary + 404 ErrorDetail
- GET /events has summary + 503 ErrorDetail
- GET /health has summary + 503 description-only (no model=)
- ErrorDetail imported only in bets.py + events.py (NOT health.py)
- Existing exception ladders (D-08 from P4) unchanged
- Full bet-maker test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-05-SUMMARY.md` recording:
- Decorator before/after for each of the 5 routes (POST /bet, GET /bets, GET /bet/{id}, GET /events, GET /health)
- Pitfall 5 notes (422 has two sources — Pydantic auto + EventNotBettable manual)
- Test/mypy/ruff status
</output>
