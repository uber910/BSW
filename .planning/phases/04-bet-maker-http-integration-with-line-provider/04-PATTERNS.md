# Phase 4: bet-maker HTTP integration with line-provider — Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 19 (4 new src, 7 modified src, 6 new/modified tests, 1 dep-manifest, 1 doc-sync)
**Analogs found:** 18 / 19 (one "novel — follow RESEARCH skeleton")

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/bet_maker/facades/line_provider_client.py` | facade (shared infra: exception + retry factory) | factory + exception class — used by both HTTP-out paths | `src/bet_maker/facades/event_lookup.py` (sibling facade with custom exceptions + Protocol) | role-match (same facade layer; tenacity factory is novel — follow RESEARCH skeleton lines 658-722) |
| `src/bet_maker/facades/http_event_lookup.py` | facade (Protocol implementation, HTTP-out) | request-response → 1 HTTP GET, retry, decode | `src/bet_maker/facades/event_lookup.py:30-80` (Protocol + `StubEventLookup` reference implementation; same method `async def get_event(event_id) -> EventSnapshot | None`) | exact (replaces Stub with HTTP-backed; same Protocol contract) |
| `src/bet_maker/selectors/list_active_events.py` | selector (read-only, HTTP-out) | request-response → 1 HTTP GET, retry, list[DTO] | `src/bet_maker/selectors/list_bets.py` (selector returning `list[BetRead]`) AND `src/line_provider/selectors/list_active_events.py` (same name, in-process store) | role-match (selector → DTO list) — note: DB session is replaced by httpx client |
| `src/bet_maker/entrypoints/api/events.py` | route (HTTP-in) | request-response | `src/bet_maker/entrypoints/api/bets.py:48-58` (`GET /bets` route — Depends + selector call) AND `src/line_provider/entrypoints/api/events.py:82-88` (same shape, response_model=list[EventRead]) | exact (mirror of GET /bets minus DB) |
| `src/bet_maker/schemas/events.py` (extend with `EventRead`) | schema (DTO) | data-shape | `src/line_provider/schemas/events.py:65-71` (symmetric duplication per D-13) | exact |
| `src/bet_maker/entrypoints/lifespan.py` (extend) | lifecycle (singleton lifecycle) | startup → app.state pin → shutdown reverse-order | Same file lines 28-50 (P3 shape) — extension target | exact (extending self) |
| `src/bet_maker/facades/deps.py` (extend) | DI providers + Annotated aliases | request → app.state | Same file lines 14-64 (existing `get_*` providers — P3) | exact |
| `src/bet_maker/entrypoints/api/bets.py` (extend `POST /bet` with 503 branch) | route (exception ladder) | request-response | Same file lines 34-45 (existing `except EventNotBettable -> 422`) | exact |
| `src/bet_maker/settings/config.py` (extend with 2 fields) | config (typed env) | env → Pydantic field | Same file lines 28-31 (existing `line_provider_base_url` field with `Field(default=...)`) | exact |
| `src/bet_maker/app.py` (extend `include_router(events.router)`) | wiring | startup | Same file line 18 (existing `app.include_router(bets.router)`) | exact |
| `tests/bet_maker/test_http_event_lookup.py` (NEW) | test-unit (respx) | mock HTTP | `tests/bet_maker/test_event_lookup.py` (StubEventLookup unit tests) — respx-specific pattern from RESEARCH §«Pattern 3» lines 405-477 | role-match (unit-style facade tests; respx idiom is new — follow RESEARCH lines 405-477) |
| `tests/bet_maker/test_list_active_events.py` (NEW) | test-unit (respx) | mock HTTP | Same as above + `tests/bet_maker/test_selectors.py` for shape conventions | role-match |
| `tests/bet_maker/test_events_routes.py` (NEW) | test-integration (two FastAPI apps in one loop) | full HTTP-in → HTTP-out | `tests/bet_maker/test_bet_routes.py:23-117` (route test class pattern) + `tests/line_provider/conftest.py:13-30` (LifespanManager + ASGITransport) + `tests/bet_maker/conftest.py:36-68` (session-scoped lifespan-aware client) | role-match (combines two existing patterns) |
| `tests/bet_maker/test_bet_routes.py` (extend with `TestPostBet503`) | test-integration | request → 503 path | Same file lines 119-156 (`TestPostBetEventNotBettable` class) | exact |
| `tests/bet_maker/test_schemas.py` (extend with `TestEventRead`) | test-unit | DTO validation | Same file lines 109-138 (`TestBetRead` class — model_validate, extra=forbid) | exact |
| `tests/bet_maker/test_lifespan.py` (extend) | test-unit (lifespan pins) | startup state | Same file lines 22-43 (`TestLifespanStatePins`) — extend with httpx client pin + HttpEventLookup swap | exact (mutate existing assertion `StubEventLookup → HttpEventLookup`) |
| `tests/bet_maker/test_settings.py` (NEW — no existing config-test file) | test-unit | env → field default | No analog in tests/bet_maker (no test_settings.py exists); see `test_schemas.py` pattern for env/field defaults via `model_validate` style | partial — follow RESEARCH skeleton + Pydantic v2 settings test idiom |
| `tests/bet_maker/conftest.py` (extend with `line_provider_app` session fixture) | test-fixture | session lifecycle | Same file lines 36-68 (existing `app` session-scoped fixture wrapped in `LifespanManager`) — copy shape, swap to `line_provider.app.build_app` | exact |
| `pyproject.toml` (add `respx>=0.22,<0.23` to dev-deps) | dep-manifest | build config | Same file lines 22-32 (existing `[dependency-groups] dev = [...]` block — `asgi-lifespan>=2.1,<3` is a 1-line sibling) | exact |
| `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` (doc-sync — remove TTL cache) | docs-sync | edit-only | `.planning/phases/02-line-provider-domain/02-01-PLAN.md` (LP-02 str→UUID4) + `.planning/phases/03-bet-maker-domain-db/03-01-PLAN.md` (BM-01/BM-05 coefficient removal) — both phases' Plan 01 = doc-sync-first | exact |

## Pattern Assignments

### `src/bet_maker/facades/line_provider_client.py` (facade — shared exception + retry factory) — NEW

**Analog:** `src/bet_maker/facades/event_lookup.py:1-38` (facade-layer file with custom exception-style class and Protocol-friendly shape).

**Module-shape excerpt** to mirror (imports, `from __future__ annotations`, class docstrings citing D-XX):
```python
# src/bet_maker/facades/event_lookup.py:1-38
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bet_maker.schemas.events import EventState
from config.time import utc_now


class EventSnapshot(BaseModel):
    """Frozen snapshot of an event as observed by line-provider.

    D-11: Returned by EventLookup.get_event. Interactor place_bet (D-14)
    validates: snapshot is not None, deadline > now, state == NEW.
    frozen=True ensures the snapshot can't be mutated between validation
    steps. extra='forbid' guards against drift if line-provider adds new
    fields (Plan 04 HttpEventLookup must explicitly handle them).
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID
    deadline: datetime
    state: EventState


class EventLookup(Protocol):
    """Service-boundary facade for resolving an event_id to a snapshot.
    ...
    """
    async def get_event(self, event_id: UUID) -> EventSnapshot | None: ...
```

**What to copy:**
- `from __future__ import annotations` first line.
- Docstring style: cite decision IDs (`D-11`, `D-13`) inline; mention which decisions lock the contract.

**Tenacity factory pattern — novel, follow RESEARCH skeleton:**
The retry-decorator + `LineProviderUnavailable` shape has no in-codebase analog. Use the verified skeleton from `04-RESEARCH.md` lines 658-722 verbatim (verified against Context7 `/jd/tenacity`):
- `LineProviderUnavailable(reason: str)` exception
- `_is_retryable(exc) -> bool` predicate (TransportError | HTTPStatusError 5xx)
- `_log_before_sleep(retry_state: RetryCallState) -> None` hook
- `make_retry_decorator(attempts: int, max_backoff: float)` factory returning `tenacity.retry(...)` decorator with `reraise=True`

**Rules from CLAUDE.md the analog encodes:**
- `from __future__ import annotations` (Python 3.10 compatibility marker)
- No emojis in code; docstrings reference decision IDs (D-XX) for grep-traceability
- mypy strict: type hints on every parameter and return; `BaseException` type for `_is_retryable` predicate parameter
- Pydantic `frozen=True, extra="forbid"` discipline

---

### `src/bet_maker/facades/http_event_lookup.py` (facade — Protocol implementation, HTTP-out) — NEW

**Analog:** `src/bet_maker/facades/event_lookup.py:41-80` (`StubEventLookup` — reference implementation of the `EventLookup` Protocol).

**Reference implementation shape** (Protocol method signature, error-mapping discipline, comments tagged with D-IDs):
```python
# src/bet_maker/facades/event_lookup.py:41-80
class StubEventLookup:
    """In-process dict-backed EventLookup for P3 tests + dev environments.

    D-11: Tests use `app.state.event_lookup.seed_active(event_id)` to
    register a bettable event before POSTing to /bet. seed_active is the
    common-case convenience method (state=NEW + deadline=now+1h); seed()
    accepts a full EventSnapshot for edge cases (past deadline / finished
    state).
    """

    def __init__(self) -> None:
        self._events: dict[UUID, EventSnapshot] = {}

    # ... seed / seed_active helpers ...

    async def get_event(self, event_id: UUID) -> EventSnapshot | None:
        """Return the seeded snapshot or None — interactor maps None to 422."""
        return self._events.get(event_id)
```

**What to copy:**
- Class-level docstring quoting the relevant `D-XX` IDs (here: D-11 + D-14).
- Exact method signature: `async def get_event(self, event_id: UUID) -> EventSnapshot | None`.
- Return-None-for-missing convention (line 80): "interactor maps None to 422" — same contract; here it's the 404 → None branch.

**HTTP body of `get_event` — follow RESEARCH skeleton:** `04-RESEARCH.md` lines 724-777 — the inner-`_call`-wrapped-by-`@self._retry` idiom plus the `try / except (TransportError, HTTPStatusError) -> raise LineProviderUnavailable` wrapper (Pitfall 5 in RESEARCH line 627-639).

**Rules from CLAUDE.md the analog encodes:**
- mypy strict: `event_id: UUID` (no `str | UUID` widening)
- Docstring per public method
- No module-level state — all state goes on `self.` (Pitfall A2 mitigation, mirrored from `StubEventLookup._events`)

---

### `src/bet_maker/selectors/list_active_events.py` (selector — HTTP-out, list[DTO]) — NEW

**Primary analog:** `src/bet_maker/selectors/list_bets.py:1-22` (selector returning `list[BetRead]`).

**Excerpt to mirror (selector-shape, DTO-validation-in-iteration):**
```python
# src/bet_maker/selectors/list_bets.py:1-22
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead


async def list_bets(session: AsyncSession) -> list[BetRead]:
    """Return all bets, newest first.

    D-07 / BM-07: ROADMAP P3 success criterion #3 -- GET /bets ordered by
    created_at DESC. No pagination, no filtering at test-task scale.
    Pure read -- no UoW (D-25), session is one-shot via get_session DI.

    Anti-Pattern 5 mitigation: BetRead.model_validate(row, from_attributes=True)
    inside the iteration -- caller receives DTOs, never ORM instances.
    """
    stmt = select(Bet).order_by(Bet.created_at.desc())
    result = await session.execute(stmt)
    return [BetRead.model_validate(row, from_attributes=True) for row in result.scalars()]
```

**Secondary analog:** `src/line_provider/selectors/list_active_events.py` — **same function name** in the sibling service (uses in-process store rather than httpx). Functional name parity is intentional.

**What to copy:**
- One async public function per selector module file.
- Docstring cites BM-04 / D-10 / D-11 inline.
- `[Schema.model_validate(item) for item in source]` in the return statement — DTOs only, never raw `dict`/`httpx.Response`.

**HTTP-flavoured body — follow RESEARCH skeleton at lines 779-815:**
- Local `retry_decorator = make_retry_decorator(attempts, max_backoff)` + inner `@retry_decorator async def _call()` pattern.
- `try / except (TransportError, HTTPStatusError) -> raise LineProviderUnavailable(reason=str(exc)) from exc` wrapper.

**Rules from CLAUDE.md the analog encodes:**
- DTOs in return type (Anti-Pattern 5: never leak Response objects out of the selector layer)
- Decimal/Datetime handled via Pydantic in DTO, not in the selector

---

### `src/bet_maker/entrypoints/api/events.py` (route — `GET /events`) — NEW

**Primary analog:** `src/bet_maker/entrypoints/api/bets.py:48-58` (`GET /bets` route — `response_model=list[BetRead]`, Depends, selector call).

**Excerpt to mirror:**
```python
# src/bet_maker/entrypoints/api/bets.py:48-58
@router.get(
    "/bets",
    response_model=list[BetRead],
)
async def get_bets(session: SessionDep) -> list[BetRead]:
    """GET /bets — list all bets, newest first.

    BM-07: returns list[BetRead] ordered by created_at DESC.
    D-25: pure read — session injected directly (no UoW).
    """
    return await list_bets(session)
```

**Secondary analog:** `src/line_provider/entrypoints/api/events.py:82-88` — same name `list_events` on the LP side (`response_model=list[EventRead]`), confirms the API shape this route proxies.

**Exception-mapping pattern to layer on top — analog from `bets.py:34-45`:**
```python
# src/bet_maker/entrypoints/api/bets.py:34-45
    try:
        return await place_bet(
            uow,
            event_id=body.event_id,
            amount=body.amount,
            event_lookup=event_lookup,
        )
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc
```

**Apply to `GET /events`:** wrap `await list_active_events(http_client)` in `try/except LineProviderUnavailable -> raise HTTPException(503, detail="line-provider unreachable") from exc` (D-10).

**What to copy:**
- `router = APIRouter(tags=["events"])` module-level (mirror line 13 of `bets.py`: `tags=["bets"]`).
- `response_model=list[EventRead]` on the decorator.
- `Annotated`-alias DI dependency (`LineProviderHttpClientDep`) injected as a single function parameter — same shape as `SessionDep` / `UoWDep` / `EventLookupDep`.
- `from exc` clause on every `raise HTTPException(...)` (preserves traceback hygiene — same pattern as line 45 of `bets.py`).

**Rules from CLAUDE.md the analog encodes:**
- Use `status.HTTP_503_SERVICE_UNAVAILABLE` constant, not the literal `503` (mypy/ruff readability)
- Detail strings are static, no user-supplied content interpolated (Security ASVS V5 — RESEARCH §Security row "Information disclosure via error detail")

---

### `src/bet_maker/schemas/events.py` (extend with `EventRead`) — MODIFIED

**Analog:** `src/line_provider/schemas/events.py:65-71` (symmetric duplication per D-13, mirror of P3 D-12 `EventState` duplication).

**Excerpt to copy (with `frozen=True` added per D-13):**
```python
# src/line_provider/schemas/events.py:65-71
class EventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    coefficient: Coefficient
    deadline: AwareDatetime
    state: EventState
```

**Adaptation rules:**
- `model_config = ConfigDict(frozen=True, extra="forbid")` — bet-maker side wants `frozen=True` too (D-13). LP side did NOT have `frozen=True` because LP needs to construct from in-memory store; bet-maker only deserialises from HTTP, so freeze it.
- DO NOT import `Coefficient` from line_provider. Bet-maker side uses plain `Decimal` (or its own annotated alias if precision discipline matters — but D-13 says just `coefficient: Decimal`).
- Use bet-maker's own `EventState` (already in this file at lines 11-14), NOT `line_provider.schemas.events.EventState`. Service boundary discipline.
- `deadline: datetime` (or `AwareDatetime` if Pydantic v2's strict-aware semantics are wanted — D-13 specifies plain `datetime`; AwareDatetime is fine but not required).

**Existing file head — read first** (`src/bet_maker/schemas/events.py:1-15`):
```python
"""EventState duplicated from line_provider.schemas.events -- intentional
service-boundary isolation per D-12 (mirror of P2 D-13 EventFinishedMessage
intentional duplication). Value-parity test in test_schemas.py prevents drift.
"""

from __future__ import annotations

from enum import Enum


class EventState(str, Enum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"
```

**What to copy:** the module docstring's "intentional duplication" justification (per D-13 will be added).

**Rules from CLAUDE.md the analog encodes:**
- `extra="forbid"` on every Pydantic schema (project-wide invariant — see `test_schemas.py::TestExtraForbid` at lines 178-187)
- `frozen=True` on DTOs that are read-only at runtime (P3 `EventSnapshot` pattern)

---

### `src/bet_maker/entrypoints/lifespan.py` (extend) — MODIFIED

**Analog:** Same file lines 16-50 (current P3 shape — extension target).

**Current shape (P3) to extend:**
```python
# src/bet_maker/entrypoints/lifespan.py:16-50
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """bet_maker lifespan: configure logging, start DB engine, wait for PG.

    D-13: app.state.event_lookup = StubEventLookup() (Plan 04 swaps to
    HttpEventLookup without touching this function — same Protocol structurally).
    ...
    """
    settings = BetMakerSettings()
    configure_structlog(settings.log_level)
    log = structlog.get_logger()
    log.info("bet_maker.startup", service=settings.service_name)

    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    try:
        await wait_for_postgres(engine)
    except Exception as exc:
        log.critical("bet_maker.startup.failed", reason=str(exc))
        await engine.dispose()
        raise

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.event_lookup = StubEventLookup()

    try:
        yield
    finally:
        log.info("bet_maker.shutdown")
        await engine.dispose()
```

**Extension instructions (D-19, D-20):**
1. After `wait_for_postgres(engine)` succeeds and before the `app.state.*` pin block: create `http_client = httpx.AsyncClient(base_url=str(settings.line_provider_base_url), timeout=httpx.Timeout(5.0))`.
2. Replace `app.state.event_lookup = StubEventLookup()` with `app.state.event_lookup = HttpEventLookup(http_client=http_client, attempts=settings.line_provider_http_attempts, max_backoff=settings.line_provider_http_backoff_max_s)`.
3. Add `app.state.line_provider_http_client = http_client` to the pin block.
4. In `finally:`, insert `await http_client.aclose()` BEFORE `await engine.dispose()` (D-20 reverse-order). Log `bet_maker.shutdown` AFTER aclose but BEFORE dispose (or keep existing order — D-20 only mandates aclose-before-dispose).
5. New imports: `httpx`, `from bet_maker.facades.http_event_lookup import HttpEventLookup`. Drop the `StubEventLookup` import (move it: it stays in `facades/event_lookup.py` for tests, but the lifespan no longer imports it).

**What to copy:**
- Top-of-file imports follow `from __future__ import annotations` then stdlib then third-party then local — same convention as the current file.
- `log = structlog.get_logger()` after `configure_structlog(...)` — same pattern.
- Docstring lists each `D-XX` decision the body implements (D-19, D-20, D-21 in addition to existing D-13/D-15/D-16/D-27).

**Rules from CLAUDE.md the analog encodes:**
- No module-level singletons — every long-lived object goes on `app.state.*` (current file embodies this; extension MUST also follow)
- Always `await` async cleanup (`await engine.dispose()` line 50 — same applies to `await http_client.aclose()`)
- `httpx.Timeout(5.0)` explicit (Pitfall row 1014 in PITFALLS.md)

---

### `src/bet_maker/facades/deps.py` (extend) — MODIFIED

**Analog:** Same file lines 14-64 (existing providers + Annotated aliases).

**Exact excerpt to mirror — `get_event_lookup` + `EventLookupDep`:**
```python
# src/bet_maker/facades/deps.py:50-64
def get_event_lookup(request: Request) -> EventLookup:
    """Read the EventLookup — pinned to app.state by lifespan.

    D-13: P3 StubEventLookup; Plan 04 swaps to HttpEventLookup without touching
    this provider — same Protocol satisfied structurally.
    """
    return cast(EventLookup, request.app.state.event_lookup)


SettingsDep = Annotated[BetMakerSettings, Depends(get_settings)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UoWDep = Annotated[AsyncUnitOfWork, Depends(get_uow)]
EventLookupDep = Annotated[EventLookup, Depends(get_event_lookup)]
```

**Adaptation — add 1 provider + 1 alias (D-12):**
```python
def get_line_provider_http_client(request: Request) -> httpx.AsyncClient:
    """D-12: read the singleton httpx.AsyncClient — pinned by lifespan."""
    return cast(httpx.AsyncClient, request.app.state.line_provider_http_client)


LineProviderHttpClientDep = Annotated[httpx.AsyncClient, Depends(get_line_provider_http_client)]
```

**What to copy:**
- `cast(T, request.app.state.X)` form on every provider — preserves mypy strictness against `Any` from `request.app.state` (which is `Starlette.State` = `Any`-typed).
- Docstring cites `D-XX` decision.
- Alias declared at module bottom, AFTER all providers (existing file convention lines 59-64).

**Rules from CLAUDE.md the analog encodes:**
- mypy strict: `cast(T, ...)` is the project's pattern for narrowing `Any` to typed (vs `# type: ignore`)
- No DI logic in routes — routes consume `*Dep` aliases via type annotation only

---

### `src/bet_maker/entrypoints/api/bets.py` (extend `POST /bet` with 503 branch) — MODIFIED

**Analog:** Same file lines 34-45 (existing `try / except EventNotBettable -> 422`).

**Current shape:**
```python
# src/bet_maker/entrypoints/api/bets.py:34-45
    try:
        return await place_bet(
            uow,
            event_id=body.event_id,
            amount=body.amount,
            event_lookup=event_lookup,
        )
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc
```

**Extension (D-08):** Insert a new `except LineProviderUnavailable as exc:` clause BEFORE the existing `except EventNotBettable`. Order matters — `LineProviderUnavailable` is NOT a subclass of `EventNotBettable`; tested explicitly by Pitfall 7 in RESEARCH.md line 646.

```python
    try:
        return await place_bet(...)
    except LineProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event validation unavailable: line-provider unreachable",
        ) from exc
    except EventNotBettable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event {body.event_id} is not bettable: {exc.reason}",
        ) from exc
```

**What to copy:**
- `from exc` chaining (preserve traceback)
- `status.HTTP_*` constants
- Static detail string (no user-controlled fragments)

**New import:** `from bet_maker.facades.line_provider_client import LineProviderUnavailable`.

**Rules from CLAUDE.md the analog encodes:**
- Static error detail strings (security: no information disclosure)
- Exception order matters for narrow→broad — not applicable here since both are siblings, BUT D-08 mandates `LineProviderUnavailable` FIRST for explicit reading clarity.

---

### `src/bet_maker/settings/config.py` (extend with 2 fields) — MODIFIED

**Analog:** Same file lines 18-31 (existing fields with `Field(default=..., ge=..., le=...)`).

**Exact excerpt to mirror:**
```python
# src/bet_maker/settings/config.py:18-31
    service_name: str = Field(default="bet-maker")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001, ge=1, le=65535)

    postgres_dsn: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://bsw:bsw@postgres:5432/bsw"),
    )
    rabbitmq_url: AmqpDsn = Field(
        default=AmqpDsn("amqp://guest:guest@rabbitmq:5672/"),
    )
    line_provider_base_url: HttpUrl = Field(
        default=HttpUrl("http://line-provider:8000"),
    )
    reconciliation_interval_s: float = Field(default=30.0, gt=0)
```

**Extension (D-21) — append next to `line_provider_base_url`:**
```python
    line_provider_http_attempts: int = Field(default=3, ge=1, le=10)
    line_provider_http_backoff_max_s: float = Field(default=2.0, gt=0)
```

**What to copy:**
- `Field(default=..., gt=..., ge=..., le=...)` discipline (constraints on every numeric field — mirror `reconciliation_interval_s: float = Field(default=30.0, gt=0)` shape exactly).
- Field names in `snake_case`, env-var resolution via `env_prefix="BET_MAKER_"` (already declared on line 13).
- Group related fields together (the two new fields belong under `line_provider_base_url`).

**Rules from CLAUDE.md the analog encodes:**
- Pydantic-settings: typed config, no `os.getenv`
- Constraint-bound numeric defaults (ge/le for ints, gt for floats) — RESEARCH §Security row "Configuration"

---

### `src/bet_maker/app.py` (extend `include_router`) — MODIFIED

**Analog:** Same file lines 10-19 (current `build_app()` factory).

**Excerpt:**
```python
# src/bet_maker/app.py:10-19
def build_app() -> FastAPI:
    app = FastAPI(
        title="bet-maker",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(bets.router)
    return app
```

**Adaptation:** Insert `app.include_router(events.router)` after `bets.router` (or alphabetically — current order is health → bets, P4 adds events). New import: `from bet_maker.entrypoints.api import bets, events, health`.

---

### `tests/bet_maker/test_http_event_lookup.py` (NEW — respx unit tests for `HttpEventLookup`)

**Primary analog:** `tests/bet_maker/test_event_lookup.py` (StubEventLookup unit tests — same file role, different infrastructure).

**Secondary analog — respx idiom:** `04-RESEARCH.md` §«Pattern 3» lines 405-477 (verified against Context7 `/lundberg/respx`).

**Excerpt from RESEARCH lines 419-442 (the canonical respx-test shape for this phase):**
```python
@pytest.mark.asyncio
@respx.mock(base_url="http://line-provider:8000", assert_all_called=True)
async def test_get_event_5xx_then_200_retry_succeeds(respx_mock) -> None:
    """D-15 / D-05: 5xx triggers retry; subsequent 200 succeeds."""
    event_id_str = "11111111-1111-1111-1111-111111111111"
    respx_mock.get(f"/event/{event_id_str}").mock(
        side_effect=[
            Response(503),
            Response(503),
            Response(200, json={
                "event_id": event_id_str,
                "coefficient": "2.50",
                "deadline": "2026-12-01T12:00:00+00:00",
                "state": "NEW",
            }),
        ]
    )

    async with httpx.AsyncClient(base_url="http://line-provider:8000",
                                  timeout=httpx.Timeout(5.0)) as client:
        lookup = HttpEventLookup(http_client=client, attempts=3, max_backoff=2.0)
        snapshot = await lookup.get_event(UUID(event_id_str))

    assert snapshot is not None
    assert snapshot.state == EventState.NEW
```

**Test scenarios (D-15 from CONTEXT.md):**
- `test_get_event_200_returns_snapshot` (D-09 happy path)
- `test_get_event_404_returns_none` (D-09 — `route.call_count == 1`, no retry)
- `test_get_event_4xx_propagates_no_retry` (D-05)
- `test_get_event_5xx_exhausts_raises` (D-07 — `pytest.raises(LineProviderUnavailable)`)
- `test_get_event_5xx_then_200_retry_succeeds` (D-05)

**Rules from CLAUDE.md the analog encodes:**
- Test docstring cites `D-XX` / `BM-04` REQ-ID for grep-traceability (P1 Plan 01-07 convention — see `test_bet_routes.py` lines 32, 47, 59 for examples)
- One assertion concept per test, named after behaviour (not after method)

---

### `tests/bet_maker/test_list_active_events.py` (NEW — respx unit tests for selector)

**Primary analog:** `tests/bet_maker/test_selectors.py` (selector-test conventions — class-per-function, async with `loop_scope="session"`, DTO type assertions).

**Excerpt from `test_selectors.py:26-37` (class-shape):**
```python
@pytest.mark.asyncio(loop_scope="session")
class TestListBets:
    """BM-07 / Risk Axis 9: list_bets ordering and shape invariants."""

    async def test_returns_empty_list_when_no_bets(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Empty table -> []."""
        async with session_factory() as session:
            bets = await list_bets(session)
            assert bets == []
```

**Adaptation:** Replace `session_factory` fixture with an `httpx.AsyncClient` constructed inside the test (or a `respx_mock` fixture). Class name: `TestListActiveEvents`. Class docstring: `"""BM-04 / D-10 / D-11: list_active_events shape, retry, error mapping."""`.

**Test scenarios (D-15 from CONTEXT.md):**
- `test_returns_empty_list_when_lp_empty` (D-10 — 200 + `[]`)
- `test_returns_event_read_list_when_lp_has_events` (D-13 — `EventRead.model_validate` round-trip)
- `test_5xx_then_200_retry_succeeds` (D-05)
- `test_5xx_exhausts_raises_unavailable` (D-07)

**Rules from CLAUDE.md the analog encodes:**
- `@pytest.mark.asyncio(loop_scope="session")` on the class (matches `asyncio_default_fixture_loop_scope="session"` in pyproject.toml — Pitfall A2 mitigation)
- Test method names start with `test_<observable-outcome>` (e.g., `_returns_empty_list_when_*`, not `_test_empty`)

---

### `tests/bet_maker/test_events_routes.py` (NEW — integration test, two FastAPI apps in one loop)

**Primary analog:** `tests/bet_maker/test_bet_routes.py:23-117` (route-test class shape — `TestPostBet`, async methods with `client: AsyncClient`).

**Excerpt for class structure:**
```python
# tests/bet_maker/test_bet_routes.py:23-40
@pytest.mark.asyncio(loop_scope="session")
class TestPostBet:
    """POST /bet — happy path and validation errors (BM-05/BM-06)."""

    async def test_post_bet_happy_path_returns_201(
        self,
        client: AsyncClient,
        seed_event: Callable[..., UUID],
    ) -> None:
        """BM-05: POST /bet returns 201 + BetRead with all required fields."""
        event_id = seed_event()
        response = await client.post("/bet", json={"event_id": str(event_id), "amount": "10.00"})
        assert response.status_code == 201
        ...
```

**Secondary analog (LifespanManager + ASGITransport pattern):** `tests/line_provider/conftest.py:13-30`:
```python
# tests/line_provider/conftest.py:13-30
@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    """FastAPI instance with lifespan triggered.

    Yielded separately so integration tests in plan 02-07 can seed
    app.state.event_store directly without touching client._transport.
    """
    application = build_app()
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client bound to the lifespan-aware app fixture."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Tertiary analog (session-scoped + dependency_overrides):** `tests/bet_maker/conftest.py:36-68`:
```python
# tests/bet_maker/conftest.py:36-68
@pytest_asyncio.fixture(scope="session")
async def app(pg_dsn: str) -> AsyncIterator[FastAPI]:
    """Session-scoped FastAPI bet_maker app with lifespan triggered.

    Session-scoped to avoid asyncpg event-loop mismatch: ...
    """
    from bet_maker.app import build_app  # noqa: PLC0415

    os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
    try:
        application = build_app()
        async with LifespanManager(application):
            yield application
    finally:
        os.environ.pop("BET_MAKER_POSTGRES_DSN", None)


@pytest_asyncio.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Combine the three analogs (RESEARCH lines 492-552 gives the explicit combination):**
- New fixture in `conftest.py`: `line_provider_app` (session-scoped, wrapped in `LifespanManager`, mirrors `tests/line_provider/conftest.py:13-22`).
- New test-only client `bet_maker_client_against_real_lp` that overrides `app.dependency_overrides[get_line_provider_http_client] = lambda: AsyncClient(transport=ASGITransport(app=line_provider_app), base_url="http://line-provider:8000", timeout=Timeout(5.0))`.
- ALSO override `app.state.event_lookup = HttpEventLookup(http_client=lp_client, attempts=3, max_backoff=2.0)` so the interactor `place_bet` uses HTTP path (it reads `event_lookup` from `app.state`, not via Depends per `bets.py:24`).

**Test scenarios (D-16):**
- `test_get_events_returns_active_from_lp` (BM-04, D-10)
- `test_get_events_returns_empty_after_state_finished` (D-10 — `PUT /event/{id}` to LP → `GET /events` to BM returns `[]`)
- `test_post_bet_happy_path_through_real_lp` (D-09 — full chain)
- `test_post_bet_422_when_event_unknown_in_lp` (D-09 — 404 → None → EventNotBettable → 422)
- `test_get_events_503_when_lp_5xx` — for forced-5xx, use `respx` overlay on the lp_client (RESEARCH §«Claude's Discretion» line 151 — real LP for happy/state, respx for 5xx)

**Rules from CLAUDE.md the analog encodes:**
- `scope="session"` fixtures for any object that uses asyncpg (event-loop discipline, Pitfall A2)
- `loop_scope="session"` on test classes that share session-scoped fixtures
- `from bet_maker.app import build_app  # noqa: PLC0415` — local import to defer side-effects, ruff-PLC0415 ignored on test fixtures (project convention)
- `try / finally` around env-var pokes (lines 51-57 of `tests/bet_maker/conftest.py`)

---

### `tests/bet_maker/test_bet_routes.py` (extend with `TestPostBet503`) — MODIFIED

**Analog:** Same file lines 119-156 (existing `TestPostBetEventNotBettable` class).

**Excerpt:**
```python
# tests/bet_maker/test_bet_routes.py:119-130
@pytest.mark.asyncio(loop_scope="session")
class TestPostBetEventNotBettable:
    """POST /bet — EventNotBettable reason strings (BM-06)."""

    async def test_post_bet_422_event_not_found(self, client: AsyncClient) -> None:
        """BM-06: 422 with 'event not found' when event_id not in lookup."""
        unknown_id = uuid4()
        response = await client.post("/bet", json={"event_id": str(unknown_id), "amount": "10.00"})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "event not found" in detail
        assert str(unknown_id) in detail
```

**Adaptation (D-17):** Add `TestPostBet503` class. Mechanism: a small fake EventLookup that always raises `LineProviderUnavailable("simulated")`, injected via `app.dependency_overrides[get_event_lookup]`.

```python
@pytest.mark.asyncio(loop_scope="session")
class TestPostBet503:
    """POST /bet — 503 when line-provider unreachable (D-08)."""

    async def test_post_bet_503_when_line_provider_unavailable(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """D-08: LineProviderUnavailable -> 503 with static detail; no PG write."""
        class _RaisingLookup:
            async def get_event(self, event_id):
                raise LineProviderUnavailable(reason="simulated")

        from bet_maker.facades.deps import get_event_lookup
        app.dependency_overrides[get_event_lookup] = lambda: _RaisingLookup()
        try:
            response = await client.post("/bet", json={"event_id": str(uuid4()), "amount": "10.00"})
            assert response.status_code == 503
            assert response.json()["detail"] == "event validation unavailable: line-provider unreachable"
        finally:
            app.dependency_overrides.pop(get_event_lookup, None)
```

**Rules from CLAUDE.md the analog encodes:**
- `try / finally` around `dependency_overrides` (mirror of `tests/bet_maker/conftest.py:51-57` env-var pattern)
- Static assertion on detail string (exact match — no substring search, since detail is static)

---

### `tests/bet_maker/test_schemas.py` (extend with `TestEventRead`) — MODIFIED

**Analog:** Same file lines 109-138 (`TestBetRead` — model_validate, JSON round-trip, extra-forbid).

**Excerpt:**
```python
# tests/bet_maker/test_schemas.py:109-138
class TestBetRead:
    """BM-05 / D-19 / D-05: BetRead from_attributes + Decimal as JSON string."""

    def test_from_attributes_accepts_orm_like(self) -> None:
        """D-14: BetRead.model_validate(orm_obj, from_attributes=True) works."""
        orm_like = SimpleNamespace(...)
        read = BetRead.model_validate(orm_like, from_attributes=True)
        assert isinstance(read.id, UUID)
        ...

    def test_decimal_serializes_as_string(self) -> None:
        """D-19 / Pitfall A4: amount serialises as string '10.00', not float."""
        ...
        payload = json.loads(read.model_dump_json())
        assert payload["amount"] == "10.00"
```

**Adaptation:** Add `TestEventRead` class. Scenarios (D-13):
- `test_event_read_parses_lp_payload` — input `{"event_id": "...", "coefficient": "2.50", "deadline": "...", "state": "NEW"}` → `EventRead` instance with right types.
- `test_event_read_extra_forbid` — extra field → `ValidationError` (mirror `test_betcreate_extra_forbid` at line 84-95).
- `test_event_read_frozen` — `read.event_id = uuid4()` → `ValidationError` (frozen=True).
- `test_event_read_decimal_serializes_as_string` — `coefficient: Decimal("2.50")` → JSON `"2.50"` (mirror `test_decimal_serializes_as_string`).

**Also extend `TestExtraForbid`** (lines 178-187) with `test_eventread_extra_forbid`.

**Rules from CLAUDE.md the analog encodes:**
- JSON serialisation of `Decimal` MUST round-trip as string, not float (P3 D-19 / Pitfall A4)
- `ValidationError` is the canonical assertion target for Pydantic extra-forbid

---

### `tests/bet_maker/test_lifespan.py` (extend) — MODIFIED

**Analog:** Same file lines 22-43 (`TestLifespanStatePins`) — current state-pin assertions.

**Excerpt:**
```python
# tests/bet_maker/test_lifespan.py:21-43
@pytest.mark.asyncio(loop_scope="session")
class TestLifespanStatePins:
    """D-13: successful startup pins all required app.state attributes."""

    async def test_engine_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.engine is AsyncEngine after lifespan startup."""
        assert hasattr(app.state, "engine")
        assert isinstance(app.state.engine, AsyncEngine)
    ...
    async def test_event_lookup_pinned_on_state(self, app: FastAPI) -> None:
        """D-13: app.state.event_lookup is StubEventLookup after lifespan startup."""
        assert hasattr(app.state, "event_lookup")
        assert isinstance(app.state.event_lookup, StubEventLookup)
```

**Adaptation (D-14 + D-19 + D-20):**
- **MUTATE existing test** `test_event_lookup_pinned_on_state` (lines 35-38): assertion changes from `isinstance(..., StubEventLookup)` to `isinstance(..., HttpEventLookup)`. Docstring updates: `"D-14 / D-19: app.state.event_lookup is HttpEventLookup in production lifespan (was StubEventLookup in P3)."`
- **ADD new test** `test_http_client_pinned_on_state`:
  ```python
  async def test_http_client_pinned_on_state(self, app: FastAPI) -> None:
      """D-12 / D-19: app.state.line_provider_http_client is httpx.AsyncClient."""
      assert hasattr(app.state, "line_provider_http_client")
      assert isinstance(app.state.line_provider_http_client, httpx.AsyncClient)
  ```
- **ADD new class** `TestShutdownOrder` — checks `aclose` is called before `dispose` via `unittest.mock.patch` on both methods recording call order (or simpler: assert by code-review in PR; the test exists more for PR-gate signal than runtime catch). RESEARCH line 643 leaves this as code-review-or-trivial-mock.

**NB:** `tests/bet_maker/conftest.py:33` does `app.state.event_lookup._events.clear()` — this accesses StubEventLookup-specific `._events`. After P4 the conftest fixture `_clear_event_lookup` MUST be updated (the `app` fixture uses `HttpEventLookup` now, which has no `._events`). Suggested fix: override `app.state.event_lookup = StubEventLookup()` in the autouse fixture (or shift to `app.dependency_overrides[get_event_lookup]`). This must be flagged in the plan.

**Rules from CLAUDE.md the analog encodes:**
- `loop_scope="session"` on lifespan-asserting tests (asyncpg lives in the same loop as the engine, Pitfall A2)
- `isinstance(...)` over duck-typing — concrete check on what was wired

---

### `tests/bet_maker/test_settings.py` (NEW — no existing config-test file)

**No direct analog.** No `test_settings.py` or `test_config.py` exists under `tests/bet_maker/`. Settings have so far only been exercised indirectly through `app` fixture.

**Use Pydantic-settings idiomatic pattern** — set env var, instantiate Settings, assert field:
```python
# Shape inspired by Pydantic v2 + pydantic-settings docs (no project analog)
import os

import pytest

from bet_maker.settings.config import BetMakerSettings


class TestBetMakerSettings:
    """D-21: 2 new fields with env-prefix BET_MAKER_."""

    def test_line_provider_http_attempts_default(self) -> None:
        """D-21: default = 3."""
        settings = BetMakerSettings()
        assert settings.line_provider_http_attempts == 3

    def test_line_provider_http_attempts_from_env(self, monkeypatch) -> None:
        """D-21: BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS=5 -> 5."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", "5")
        settings = BetMakerSettings()
        assert settings.line_provider_http_attempts == 5

    def test_line_provider_http_attempts_rejects_zero(self, monkeypatch) -> None:
        """D-21: ge=1 — 0 raises ValidationError."""
        monkeypatch.setenv("BET_MAKER_LINE_PROVIDER_HTTP_ATTEMPTS", "0")
        with pytest.raises(Exception):  # ValidationError; pydantic 2.x
            BetMakerSettings()
    ...
```

**Rules from CLAUDE.md the analog encodes:**
- `monkeypatch.setenv` is the pytest convention (vs `os.environ[...]` with manual cleanup)
- `ge`/`le`/`gt` constraints validated at instantiation — test the boundary
- Read prefix from `BetMakerSettings.model_config["env_prefix"]` if dynamic — not needed here, prefix is literal `"BET_MAKER_"` (line 13 of `config.py`)

**FLAG (novel):** No existing project pattern for settings tests; follow generic pydantic-settings idioms (well-documented, no surprise).

---

### `tests/bet_maker/conftest.py` (extend with `line_provider_app` fixture) — MODIFIED

**Analog:** Same file lines 36-58 (existing `app` session-scoped fixture).

**Excerpt to mirror exactly (substituting LP app + no env-var poke needed since LP has no PG):**
```python
# tests/bet_maker/conftest.py:36-58
@pytest_asyncio.fixture(scope="session")
async def app(pg_dsn: str) -> AsyncIterator[FastAPI]:
    """Session-scoped FastAPI bet_maker app with lifespan triggered.

    Session-scoped to avoid asyncpg event-loop mismatch: ...
    """
    from bet_maker.app import build_app  # noqa: PLC0415

    os.environ["BET_MAKER_POSTGRES_DSN"] = pg_dsn
    try:
        application = build_app()
        async with LifespanManager(application):
            yield application
    finally:
        os.environ.pop("BET_MAKER_POSTGRES_DSN", None)
```

**Adaptation (D-16):**
```python
@pytest_asyncio.fixture(scope="session")
async def line_provider_app() -> AsyncIterator[FastAPI]:
    """Session-scoped line_provider FastAPI app with lifespan triggered.

    D-16: same session-scope as bet_maker `app` fixture — they must share
    the same event loop so HTTPX ASGITransport can call between them
    without 'Future attached to a different loop' errors (Pitfall A2).
    """
    from line_provider.app import build_app  # noqa: PLC0415

    application = build_app()
    async with LifespanManager(application):
        yield application
```

**What to copy:**
- `scope="session"` (Pitfall A2)
- `# noqa: PLC0415` on the local import (project convention)
- `LifespanManager(application)` wrap (LP has its own lifespan; in-memory store + event bus are populated inside)
- Docstring cites D-16 + Pitfall A2

**No env-var poke** needed for `line_provider_app` — LP has no Postgres. Drop the `os.environ.pop` cleanup.

**Also: update `_clear_event_lookup` (lines 26-33).** Currently does `app.state.event_lookup._events.clear()` which assumes `StubEventLookup`. After P4 lifespan swap (D-14), this attribute doesn't exist on `HttpEventLookup`. Two options:
1. **Recommended**: replace the autouse fixture body to first override `app.state.event_lookup = StubEventLookup()` so unit tests of `POST /bet` happy path keep working (P3 tests rely on it).
2. Alternative: use `app.dependency_overrides[get_event_lookup] = lambda: StubEventLookup()` per-test/per-class.

This is a P4 plan-required adjustment, flagged here for the planner.

---

### `pyproject.toml` (add `respx` to dev-deps) — MODIFIED

**Analog:** Same file lines 22-32 (existing `[dependency-groups] dev` array — `asgi-lifespan>=2.1,<3` is the most-recent sibling addition):
```toml
# pyproject.toml:22-32
[dependency-groups]
dev = [
    "pytest>=9.0,<10",
    "pytest-asyncio>=1.1,<2",
    "pytest-cov>=7.1,<8",
    "ruff>=0.15,<0.16",
    "mypy>=2.1,<3",
    "pre-commit>=4.6,<5",
    "asgi-lifespan>=2.1,<3",
    "testcontainers>=4.9,<5",
]
```

**Adaptation:** Append `"respx>=0.22,<0.23",` to the array. Pin matches CONTEXT D-15 verbatim.

**Companion command:** `uv add --group dev "respx>=0.22,<0.23"` then `uv sync --frozen`. This both edits `pyproject.toml` AND regenerates `uv.lock`. Running `uv add` is the canonical approach — manual editing followed by `uv lock` is acceptable but more error-prone.

**Rules from CLAUDE.md the analog encodes:**
- Pinned ranges `>=X.Y,<X+1`, NEVER `==` (line-by-line in the array)
- Lockfile mode (`uv sync --frozen`) used in CI (CLAUDE.md "Installation" guidance)

---

### `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` (doc-sync — D-01) — MODIFIED

**Analog 1:** `.planning/phases/02-line-provider-domain/02-01-PLAN.md` — first plan of P2; doc-sync only; LP-02 str → UUID4 rewrite.

**Analog 2:** `.planning/phases/03-bet-maker-domain-db/03-01-PLAN.md` — first plan of P3; doc-sync only; BM-01/BM-05 coefficient removal.

**Excerpt from `03-01-PLAN.md` (lines 99-130) showing the exact rewrite pattern:**
```markdown
<task type="auto">
  <name>Task 2: Rewrite BM-01 (remove coefficient) per D-01</name>
  <files>.planning/REQUIREMENTS.md</files>
  <read_first>
    - .planning/REQUIREMENTS.md (строка 32 — текущая BM-01)
    - .planning/phases/03-bet-maker-domain-db/03-CONTEXT.md §«ТЗ-compliance» D-01 + §«Bet модель / DB-схема» D-09
    - .planning/phases/02-line-provider-domain/02-01-PLAN.md Task 2 (mirror — LP-02 str→UUID4 sync)
  </read_first>
  <action>
    Открыть `.planning/REQUIREMENTS.md`. Найти строку 32:
    ```
    - [ ] **BM-01**: SQLAlchemy 2.0 async модели для ставок (id UUID, event_id, amount Decimal 12.2, coefficient Decimal 6.2, status enum, created_at, updated_at)
    ```

    Заменить ровно на:
    ```
    - [ ] **BM-01**: SQLAlchemy 2.0 async модели для ставок (id UUID, event_id UUID, amount Decimal 12.2, status enum (PENDING/WON/LOST), ...). Per D-01 (Phase 3 CONTEXT.md): coefficient НЕ хранится в Bet — это атрибут события, живёт в line-provider; ТЗ стр. 3 `POST /bet` body = ...
    ```
    ...
  </action>
```

**What to copy (style — Plan 04-01 mirror):**
- Single-file edits (one file per task; no batched cross-file edits)
- "Найти строку X / Заменить ровно на ..." literal-block pattern — the executor performs exact string match-and-replace; no fuzzy interpretation.
- Inline citation `per D-01 (Phase 4 CONTEXT.md)` on each replaced phrase — for grep-traceability (analog 03-01 Task 2 line ~111 enforces this).
- Each task verifies the change with a grep: `! grep -i "TTL cache" REQUIREMENTS.md ROADMAP.md` (Pitfall mitigation: silent re-introduction).
- Task 1 is **verification-only against TZ first source** (mirror of 03-01 Task 1 — see lines 67-97) — read PDF, confirm TZ does NOT require cache.

**Specific D-01 edits to enact in Plan 04-01:**
1. `.planning/REQUIREMENTS.md` BM-04: replace any wording like `"+ tiny TTL cache"` / `"TTL cache"` → leave only `"проксирует список активных событий из line-provider через httpx с retry (tenacity)"`.
2. `.planning/ROADMAP.md` Phase 4 Success Criterion #1: replace `"with acceptable lag (cached via TTL dict)"` → `"with acceptable lag (свежий результат каждого запроса; отставание = длительность одного HTTP-вызова к LP плюс retry-backoff)"`.
3. Optional polish: add note to `README` "next-step extensions" — deferred to P7 (DOC-02), not part of Plan 04-01.

**Rules from CLAUDE.md the analog encodes:**
- Memory hint: "Verify decisions against TZ source" — TZ PDF first task of each phase if drift detected (memory file `feedback_verify_against_tz.md`)
- "DO NOT ADD COMMENTS unless asked" — applies to code, NOT to planning docs; doc edits with inline `per D-01` citations are explicitly required
- "No emojis in docs and code" — applies; check that the new wording has no emojis

---

## Shared Patterns

### Pattern A: `from __future__ import annotations` + Decision-ID docstrings

**Source:** Universal across `src/bet_maker/*.py` — every file starts with `from __future__ import annotations` (Python 3.10 string-annotation forward-refs). Every public class/function docstring cites the relevant `D-XX` decision ID for grep-traceability (P1 Plan 01-07 convention).

**Apply to:** all new `src/bet_maker/**/*.py` files in P4 (`line_provider_client.py`, `http_event_lookup.py`, `list_active_events.py`, `events.py`, extensions to `lifespan.py`, `deps.py`, `bets.py`, `events.py` schemas, `config.py`, `app.py`).

```python
# universal head
from __future__ import annotations

# ... imports ...


class Something:
    """One-line description.

    D-XX: <decision quote>. Pitfall ABC mitigation: <how>.
    """
```

---

### Pattern B: `app.state.*` pin + `cast(T, request.app.state.X)` provider

**Source:** `src/bet_maker/facades/deps.py:14-56` — all `get_*` providers cast `request.app.state.*` to the typed target. This is the project's canonical "singleton lifecycle" pattern.

**Apply to:** new `get_line_provider_http_client` (D-12).

```python
# pattern
def get_X(request: Request) -> X:
    """Read X — pinned to app.state by lifespan."""
    return cast(X, request.app.state.X)


XDep = Annotated[X, Depends(get_X)]
```

**Rule:** every long-lived object goes through `app.state.*` + `cast(...)` provider + `Annotated[..., Depends(...)]` alias. NO module-level singletons (Pitfall A2 in PITFALLS.md).

---

### Pattern C: Exception ladder in routes with `from exc` chaining

**Source:** `src/bet_maker/entrypoints/api/bets.py:34-45` — `try` around interactor/selector, narrow exception handlers each mapping to `HTTPException(status_code=..., detail=...) from exc`.

**Apply to:** new `POST /bet` 503 branch (D-08), new `GET /events` 503 branch (D-10).

**Rule:** every `raise HTTPException(...)` MUST include `from exc` for traceback hygiene. Order matters: most-specific first; sibling exceptions in plan-determined order (`LineProviderUnavailable` BEFORE `EventNotBettable` per D-08 readability).

---

### Pattern D: `pydantic` schemas with `extra="forbid"`, `frozen=True` on DTOs

**Source:** `src/bet_maker/facades/event_lookup.py:23` (`ConfigDict(frozen=True, extra="forbid")`); `src/line_provider/schemas/events.py:66` (`ConfigDict(extra="forbid")`). Verified by `tests/bet_maker/test_schemas.py::TestExtraForbid` lines 178-187 (project-wide invariant).

**Apply to:** new `EventRead` in `bet_maker/schemas/events.py` (D-13) — `ConfigDict(frozen=True, extra="forbid")`.

**Rule:** every Pydantic DTO MUST have `extra="forbid"`. DTOs returned to callers (not constructed mid-pipeline) get `frozen=True` as well.

---

### Pattern E: Session-scoped lifespan-aware test fixtures with `LifespanManager` + `ASGITransport`

**Source:** `tests/bet_maker/conftest.py:36-68` + `tests/line_provider/conftest.py:13-30`. The `LifespanManager(app)` wrap is non-optional when using `ASGITransport` (Pitfall 3 in RESEARCH.md — HTTPX does NOT trigger ASGI lifespan).

**Apply to:** new `line_provider_app` session fixture (D-16).

**Rule:** any FastAPI test app must be `async with LifespanManager(application): yield application` — never bare `application` with `ASGITransport`. Fixture scope must match `asyncio_default_fixture_loop_scope="session"` (pyproject.toml line ~77) to avoid Pitfall A2.

---

### Pattern F: Test docstring cites REQ-ID + D-XX for grep-traceability

**Source:** `tests/bet_maker/test_bet_routes.py:32, 47, 59, 96` — every test docstring leads with `BM-XX:` / `D-XX:` / `Pitfall AX mitigation:`. Established in P1 Plan 01-07.

**Apply to:** all new tests in P4 (`test_http_event_lookup.py`, `test_list_active_events.py`, `test_events_routes.py`, `test_bet_routes.py::TestPostBet503`, `test_schemas.py::TestEventRead`, `test_lifespan.py` extensions, `test_settings.py`).

**Rule:** test docstring = REQ/Decision citation + one-line behaviour description. Enables `git grep "BM-04"` to find every line touching that requirement.

---

### Pattern G: `@pytest.mark.asyncio(loop_scope="session")` on test classes

**Source:** `tests/bet_maker/test_bet_routes.py:23, 119, 158, 201` — every test class has the decorator. Pairs with session-scoped fixtures (`app`, `client`, `session_factory`).

**Apply to:** all new test classes in P4 that use the session-scoped `app`/`client` fixtures.

**Rule:** loop-scope must match fixture-scope (`session`). Mixing function-scope tests with session-scope fixtures → Pitfall A2 ("Future attached to a different loop"). Project-wide convention since P3.

---

### Pattern H: Doc-sync as Plan 01 of each phase

**Source:** `.planning/phases/02-line-provider-domain/02-01-PLAN.md` (str→UUID4) + `.planning/phases/03-bet-maker-domain-db/03-01-PLAN.md` (coefficient removal + BM-13 add).

**Apply to:** Plan 04-01 (D-01 TTL cache removal).

**Rule:** if a phase's CONTEXT.md flags REQUIREMENTS.md / ROADMAP.md drift against TZ first-source, the drift fix is **the first plan** of the phase. Code plans depend on this completing first (no Wave 1 work proceeds in parallel). Style: literal "найти X / заменить на Y" with inline `per D-NN (Phase X CONTEXT.md)` citation. Single commit per file.

---

## No Analog Found

Files with novel patterns (the planner should reference the RESEARCH.md skeleton verbatim rather than searching for a project analog):

| File | Role | Reason | Where to look instead |
|------|------|--------|----------------------|
| `src/bet_maker/facades/line_provider_client.py` — `make_retry_decorator` factory + tenacity `_log_before_sleep` + `_is_retryable` predicate | facade (retry-factory) | No existing project module uses `tenacity` for HTTP retries. The closest is `src/bet_maker/infrastructure/db/pings.py::wait_for_postgres` (tenacity on DB connect), but its signature/concerns are different (no exception filter, no 5xx-vs-4xx split, no before-sleep hook). | `04-RESEARCH.md` §«Code Examples» lines 658-722 — verified shape against Context7 `/jd/tenacity`. Pitfall 4 (RESEARCH line 620) explicitly mandates `retry_if_exception(_is_retryable)` over `retry_if_exception_type((TransportError, HTTPStatusError))`. |
| `tests/bet_maker/test_settings.py` (NEW) | test-unit (env-driven settings) | No existing project test for pydantic-settings. Settings have been exercised indirectly through the `app` fixture (which calls `BetMakerSettings()` inside lifespan with env vars set). | pydantic-settings 2.14.x docs (Context7 `/pydantic/pydantic-settings`) + standard `monkeypatch.setenv` idiom. Pattern is well-documented and low-risk. |
| `tests/bet_maker/test_lifespan.py::TestShutdownOrder` (sub-pattern) | test-unit | Asserting *order* of two `await` calls inside a `finally` block has no project precedent. RESEARCH line 643 explicitly notes "verify by code review at PR time, OR trivial mock recording call order". Treat as code-review-gate rather than a runtime test. | `04-RESEARCH.md` Pitfall 6 line 641-644. |

(Everything else has a strong direct analog above.)

## Metadata

**Analog search scope:**
- `src/bet_maker/` (all P3 files), `src/line_provider/` (P1+P2 files for cross-service mirror patterns)
- `tests/bet_maker/` (P3 test suite), `tests/line_provider/conftest.py` (LifespanManager + ASGITransport pattern)
- `.planning/phases/02-line-provider-domain/02-01-PLAN.md`, `.planning/phases/03-bet-maker-domain-db/03-01-PLAN.md` (doc-sync plan style)
- `.planning/phases/04-bet-maker-http-integration-with-line-provider/04-CONTEXT.md`, `04-RESEARCH.md` (decision IDs + verified code skeletons)
- `pyproject.toml` (dev-deps array + tool configs)

**Files scanned:** 19 source/test files + 2 doc-sync plans + 1 dep-manifest = 22

**Pattern extraction date:** 2026-05-15

**Phase:** 04-bet-maker-http-integration-with-line-provider
