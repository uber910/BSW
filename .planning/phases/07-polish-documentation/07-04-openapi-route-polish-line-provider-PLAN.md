---
phase: 07-polish-documentation
plan: 04
type: execute
wave: 2
depends_on: [02]
files_modified:
  - src/line_provider/entrypoints/api/events.py
  - src/line_provider/entrypoints/api/health.py
autonomous: true
requirements: [DOC-01]
must_haves:
  truths:
    - "Every line-provider route decorator has summary=\"...\" (one-line description)"
    - "POST /event has responses={409: ErrorDetail} declaration"
    - "PUT /event/{event_id} has responses={404: ErrorDetail, 422: ErrorDetail} declaration"
    - "GET /event/{event_id} has responses={404: ErrorDetail} declaration"
    - "POST /event and PUT /event/{event_id} have Body(openapi_examples={...}) with concrete UUID + Decimal example values"
    - "GET /health has summary=\"...\" declaration"
    - "All routes still raise HTTPException with same status codes — no behaviour change"
    - "ErrorDetail imported via `from line_provider.schemas.errors import ErrorDetail`"
  artifacts:
    - path: "src/line_provider/entrypoints/api/events.py"
      provides: "4 routes (POST /event, PUT /event/{id}, GET /event/{id}, GET /events) with OpenAPI metadata polish"
      contains: "summary="
    - path: "src/line_provider/entrypoints/api/health.py"
      provides: "GET /health with summary= metadata"
      contains: "summary="
  key_links:
    - from: "src/line_provider/entrypoints/api/events.py"
      to: "src/line_provider/schemas/errors.py::ErrorDetail"
      via: "import statement; used in responses={...}"
      pattern: "from line_provider.schemas.errors import ErrorDetail"
---

<objective>
Apply OpenAPI metadata polish to all line-provider routes per CONTEXT.md D-07 + D-08. Add `summary=` (one-liner), `responses={...}` mapping non-pydantic 4xx/5xx branches to `ErrorDetail` (D-09), and `Body(..., openapi_examples=...)` on POST/PUT bodies with concrete UUID + Decimal + ISO datetime example values from existing P2 integration tests.

Purpose: Swagger UI on `:8000/docs` becomes self-explanatory for the reviewer — every route lists 4xx/5xx branches with the exact JSON envelope, and request body inputs come with copy-paste-ready examples.

**No handler-body change.** Only decorator + signature edits. Existing docstrings stay — FastAPI surfaces them as `description=` automatically (do NOT move docstrings into kwargs).

Output: 2 modified files; routes still pass existing integration tests; mypy strict zero errors.
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
<!-- Current line-provider routes (verbatim from src/) — see read_first below -->

Existing pattern: `@router.post("/event", status_code=..., response_model=...)`.
Polish ADDS `summary=`, `responses=`, and `Body(openapi_examples=)` only.

Per CONTEXT.md D-07 + Pattern 1 from RESEARCH.md, the exact additions are:
- POST /event       → summary + 409 (ErrorDetail) + Body(openapi_examples)
- PUT  /event/{id}  → summary + 404 (ErrorDetail) + 422 (ErrorDetail) + Body(openapi_examples)
- GET  /event/{id}  → summary + 404 (ErrorDetail)
- GET  /events      → summary only (no error branch)
- GET  /health      → summary only

ErrorDetail import:
```python
from line_provider.schemas.errors import ErrorDetail
```

FastAPI `Body(openapi_examples={"key": {"summary": ..., "description": ..., "value": ...}})` is the Pydantic-v2-friendly form (FastAPI 0.103+) that powers Swagger UI dropdowns.
</interfaces>
</context>

<threat_model>
N/A — documentation phase. All `summary` and `description` strings are static literals; no f-string interpolation of user input. `responses={...}` declarations affect OpenAPI schema only, not runtime error handling (existing `HTTPException(detail=...)` ladder is unchanged).
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Polish OpenAPI metadata on line-provider events routes</name>
  <files>src/line_provider/entrypoints/api/events.py</files>
  <read_first>
    - src/line_provider/entrypoints/api/events.py (full file — current 4 routes)
    - src/line_provider/schemas/errors.py (must exist from plan 07-02)
    - src/line_provider/schemas/events.py (EventCreate/EventUpdate field names for accurate examples)
    - tests/line_provider/test_event_routes.py (existing integration tests — use real UUID/coefficient/deadline values from happy-path tests for examples)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (Pattern Assignments → src/line_provider/entrypoints/api/events.py)
  </read_first>
  <action>
    Edit `src/line_provider/entrypoints/api/events.py` using the Edit tool with the following targeted changes:

    **Change A: Imports** — Replace the existing FastAPI import line:
    ```python
    from fastapi import APIRouter, HTTPException, Request, status
    ```
    with:
    ```python
    from fastapi import APIRouter, Body, HTTPException, Request, status
    ```
    Add a new import line just after the `from fastapi` block:
    ```python
    from line_provider.schemas.errors import ErrorDetail
    ```

    **Change B: POST /event** — Replace the existing decorator + signature exactly:

    BEFORE:
    ```python
    @router.post(
        "/event",
        status_code=status.HTTP_201_CREATED,
        response_model=EventRead,
    )
    async def post_event(body: EventCreate, store: StoreDep) -> EventRead:
    ```

    AFTER:
    ```python
    @router.post(
        "/event",
        status_code=status.HTTP_201_CREATED,
        response_model=EventRead,
        summary="Create new event in NEW state",
        responses={
            status.HTTP_409_CONFLICT: {
                "model": ErrorDetail,
                "description": "Event with this event_id already exists.",
            },
        },
    )
    async def post_event(
        store: StoreDep,
        body: EventCreate = Body(
            openapi_examples={
                "happy": {
                    "summary": "Create new bettable event",
                    "description": "Successful creation of a NEW event in the future.",
                    "value": {
                        "event_id": "00000000-0000-0000-0000-000000000001",
                        "coefficient": "1.50",
                        "deadline": "2030-01-01T00:00:00+00:00",
                    },
                },
            },
        ),
    ) -> EventRead:
    ```

    Note: parameter order swapped to `store` first, `body` second — FastAPI requires parameters with `Body(...)` default to come after non-default params; `store` is `StoreDep` (Annotated alias) which counts as a default. To keep mypy strict happy and avoid the "Non-default argument follows default" error, list `store: StoreDep` first.

    **Change C: PUT /event/{event_id}** — Replace the existing decorator + signature exactly:

    BEFORE:
    ```python
    @router.put(
        "/event/{event_id}",
        status_code=status.HTTP_200_OK,
        response_model=EventRead,
    )
    async def put_event(
        event_id: UUID,
        body: EventUpdate,
        request: Request,
        store: StoreDep,
        event_bus: EventBusDep,
    ) -> EventRead:
    ```

    AFTER:
    ```python
    @router.put(
        "/event/{event_id}",
        status_code=status.HTTP_200_OK,
        response_model=EventRead,
        summary="Update event (state transition NEW -> FINISHED_WIN/LOSE)",
        responses={
            status.HTTP_404_NOT_FOUND: {
                "model": ErrorDetail,
                "description": "Event with this event_id does not exist.",
            },
            status.HTTP_422_UNPROCESSABLE_ENTITY: {
                "model": ErrorDetail,
                "description": "State transition not allowed (e.g. FINISHED -> NEW).",
            },
        },
    )
    async def put_event(
        event_id: UUID,
        request: Request,
        store: StoreDep,
        event_bus: EventBusDep,
        body: EventUpdate = Body(
            openapi_examples={
                "finish_win": {
                    "summary": "Transition NEW event to FINISHED_WIN",
                    "value": {
                        "coefficient": "1.50",
                        "deadline": "2030-01-01T00:00:00+00:00",
                        "state": "FINISHED_WIN",
                    },
                },
                "finish_lose": {
                    "summary": "Transition NEW event to FINISHED_LOSE",
                    "value": {
                        "coefficient": "1.50",
                        "deadline": "2030-01-01T00:00:00+00:00",
                        "state": "FINISHED_LOSE",
                    },
                },
            },
        ),
    ) -> EventRead:
    ```

    **Change D: GET /event/{event_id}** — Replace the decorator exactly:

    BEFORE:
    ```python
    @router.get(
        "/event/{event_id}",
        response_model=EventRead,
    )
    async def get_event(event_id: UUID, store: StoreDep) -> EventRead:
    ```

    AFTER:
    ```python
    @router.get(
        "/event/{event_id}",
        response_model=EventRead,
        summary="Fetch event by id",
        responses={
            status.HTTP_404_NOT_FOUND: {
                "model": ErrorDetail,
                "description": "Event with this event_id does not exist.",
            },
        },
    )
    async def get_event(event_id: UUID, store: StoreDep) -> EventRead:
    ```

    **Change E: GET /events** — Replace the decorator exactly:

    BEFORE:
    ```python
    @router.get(
        "/events",
        response_model=list[EventRead],
    )
    async def list_events(store: StoreDep) -> list[EventRead]:
    ```

    AFTER:
    ```python
    @router.get(
        "/events",
        response_model=list[EventRead],
        summary="List active events (deadline in future, state == NEW)",
    )
    async def list_events(store: StoreDep) -> list[EventRead]:
    ```

    **Do NOT modify handler bodies.** The existing try/except + HTTPException ladder for state-machine + not-found errors is unchanged.

    Run `uv run pytest -q tests/line_provider/test_event_routes.py` — all 23 integration tests from P2 must still pass (behaviour invariant: decorator metadata does not affect runtime behaviour).
    Run `uv run mypy src/line_provider/entrypoints/api/events.py` — must pass zero errors.
    Run `uv run ruff check src/line_provider/entrypoints/api/events.py && uv run ruff format --check src/line_provider/entrypoints/api/events.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/line_provider/test_event_routes.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "summary=" src/line_provider/entrypoints/api/events.py` returns 4 (one per route)
    - `grep -c "responses={" src/line_provider/entrypoints/api/events.py` returns 3 (POST, PUT, GET-by-id; GET-list has none)
    - `grep -c "openapi_examples=" src/line_provider/entrypoints/api/events.py` returns 2 (POST, PUT bodies)
    - `grep -c "ErrorDetail" src/line_provider/entrypoints/api/events.py` returns at least 4 (1 import + 3 responses model refs)
    - `grep -c "from line_provider.schemas.errors import ErrorDetail" src/line_provider/entrypoints/api/events.py` returns 1
    - `grep -c "00000000-0000-0000-0000-000000000001" src/line_provider/entrypoints/api/events.py` ≥ 1 (UUID example present)
    - `grep -c "FINISHED_WIN" src/line_provider/entrypoints/api/events.py` ≥ 1 (state example present)
    - `uv run pytest -q tests/line_provider/test_event_routes.py` shows all tests passing (no behaviour change)
    - `uv run mypy src/line_provider/entrypoints/api/events.py` shows zero errors
    - `uv run ruff check src/line_provider/entrypoints/api/events.py` shows no issues
  </acceptance_criteria>
  <done>4 routes have summary; POST/PUT/GET-by-id have responses=ErrorDetail; POST/PUT have Body(openapi_examples); tests still green; mypy/ruff clean.</done>
</task>

<task type="auto">
  <name>Task 2: Polish OpenAPI metadata on line-provider /health route</name>
  <files>src/line_provider/entrypoints/api/health.py</files>
  <read_first>
    - src/line_provider/entrypoints/api/health.py (current state — 9 lines)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (LP health pattern section)
  </read_first>
  <action>
    Edit `src/line_provider/entrypoints/api/health.py` using the Edit tool. Replace the decorator exactly:

    BEFORE:
    ```python
    @router.get("/health")
    async def health() -> dict[str, str]:
    ```

    AFTER:
    ```python
    @router.get(
        "/health",
        summary="Liveness probe",
    )
    async def health() -> dict[str, str]:
    ```

    Note: line-provider /health has NO error branch (no PG/RMQ deps to check — LP is in-memory; subscriber/broker/publisher liveness is not health-checked here per P5 D-20). Therefore no `responses=` block needed.

    Run `uv run pytest -q tests/line_provider/test_health.py` — both health tests must still pass.
    Run `uv run mypy src/line_provider/entrypoints/api/health.py` — zero errors.
    Run `uv run ruff check src/line_provider/entrypoints/api/health.py`.
  </action>
  <verify>
    <automated>uv run pytest -q tests/line_provider/test_health.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "summary=\"Liveness probe\"" src/line_provider/entrypoints/api/health.py` returns 1
    - `grep -c "responses=" src/line_provider/entrypoints/api/health.py` returns 0 (no error branch declared)
    - `uv run pytest -q tests/line_provider/test_health.py` shows tests passing
    - `uv run mypy src/line_provider/entrypoints/api/health.py` shows zero errors
    - `uv run ruff check src/line_provider/entrypoints/api/health.py` shows no issues
  </acceptance_criteria>
  <done>/health has summary metadata; no responses block (no error branch); tests still green; mypy/ruff clean.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q tests/line_provider/` — full line-provider suite green (existing ~25 tests)
- `uv run mypy src` — zero errors
- `uv run ruff check . && uv run ruff format --check .` — zero issues
- Manually: starting line-provider and visiting `:8000/docs` shows: summaries on every route, Try-it-out examples on POST/PUT, 409/404/422 error envelope schemas visible
- Manually: `:8000/openapi.json` includes `"summary"` and `"responses"` keys with ErrorDetail `$ref`
</verification>

<success_criteria>
- 4 events routes + 1 health route have `summary=`.
- POST /event has 409 ErrorDetail response declared; PUT /event/{id} has 404 + 422 ErrorDetail responses; GET /event/{id} has 404 ErrorDetail.
- POST + PUT bodies have `openapi_examples` dict with concrete UUID/coefficient/deadline/state values from P2 happy-path tests.
- ErrorDetail imported from `line_provider.schemas.errors`.
- No handler-body change — all P2 integration tests still pass.
- mypy strict zero errors; ruff zero issues.
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-04-SUMMARY.md` recording:
- Decorator before/after for each of the 5 routes
- Test results (P2 integration suite must remain green)
- mypy/ruff status
</output>
