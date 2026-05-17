---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 05
subsystem: facades
tags: [httpx, tenacity, respx, event-lookup, protocol, bet-maker, line-provider, 404, retry]

requires:
  - phase: 03-bet-maker-domain-db
    provides: "EventLookup Protocol + EventSnapshot frozen DTO (P3 D-11); EventState enum duplication (P3 D-12)"
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: "Plan 04-04 shared retry-factory (make_retry_decorator) + LineProviderUnavailable exception"
provides:
  - "src/bet_maker/facades/http_event_lookup.py -- HttpEventLookup class implementing EventLookup Protocol over httpx"
  - "Production EventLookup replacement (D-14) ready for Plan 04-07 lifespan wiring"
  - "tests/bet_maker/test_http_event_lookup.py -- 5 respx-driven contractual scenarios + 1 Protocol-marker test"
affects:
  - "04-07 lifespan wiring -- app.state.event_lookup = HttpEventLookup(http_client=..., attempts=..., max_backoff=...)"
  - "04-09 POST /bet 503 path -- LineProviderUnavailable from HttpEventLookup must propagate to route layer"

tech-stack:
  added: []
  patterns:
    - "404-before-raise_for_status ordering (Pitfall 5): the 404 short-circuit precedes raise_for_status so 5xx remains observable to tenacity as httpx.HTTPStatusError"
    - "Outer try/except mapping pattern: a single (TransportError, HTTPStatusError) -> LineProviderUnavailable conversion at the facade boundary collapses transport + non-retried-4xx + retry-exhausted-5xx into one downstream-actionable exception"
    - "respx module-level decorator pattern: @respx.mock(base_url=..., assert_all_called=...) on async functions yields the cleanest test idiom; class-grouping is reserved for invariants and Protocol-marker checks"
    - "Pydantic v2 implicit coercion: EventSnapshot(deadline=payload['deadline'], state=payload['state']) lets the model's field validators coerce ISO 8601 string to datetime and str to EventState -- no manual parsing"

key-files:
  created:
    - "src/bet_maker/facades/http_event_lookup.py (~71 lines -- module docstring cites D-11/D-14/D-05/D-07/D-09 + Pitfall 5)"
    - "tests/bet_maker/test_http_event_lookup.py (~145 lines -- 5 respx scenarios + TestHttpEventLookup Protocol marker)"
  modified: []

key-decisions:
  - "Keep literal 404 in the code via `# noqa: PLR2004` rather than extract to `_HTTP_NOT_FOUND` -- plan acceptance criterion requires grep-c match on the literal `if response.status_code == 404:` line; constant extraction would silently break the verification contract."
  - "Marker class `TestHttpEventLookup` retained alongside module-level test functions -- plan must_haves declare `contains: 'class TestHttpEventLookup'` while the plan body shows function-level decorators. The marker class is the smallest-surface satisfaction of both constraints (one test inside proves Protocol satisfaction)."
  - "Hoisted `EventLookup` import to module scope (PLC0415) rather than keeping it inline inside the marker test -- top-level imports are project convention and the Protocol type is already needed by tests."

patterns-established:
  - "Facade implementation pattern: a small class binding (httpx.AsyncClient, retry-decorator) at construction and exposing one Protocol method per upstream endpoint. The retry-decorator wraps the inner _call coroutine so tenacity has a clean callable boundary."
  - "Decision-by-code mapping in docstrings: module docstring cites D-XX inline next to the mapping rule (200/404/4xx/5xx) -- preserves traceability without forcing readers to open the CONTEXT file."
  - "respx scenario coverage convention: one test per truth-table row of the response-mapping (200/404/4xx/5xx-exhausts/5xx-then-200) -- five scenarios is the minimum complete set for a single-endpoint facade."

requirements-completed: []
requirements-progressed: [BM-04]

duration: ~4min
completed: 2026-05-17
---

# Phase 04 / Plan 05: HttpEventLookup over httpx+tenacity (D-05/D-07/D-09/D-11/D-14) -- Summary

**The production EventLookup is wired: HttpEventLookup binds the shared retry-decorator from Plan 04-04 to a httpx.AsyncClient and turns line-provider's `GET /event/{id}` into the same `EventSnapshot | None` contract that StubEventLookup already exposes -- the place_bet interactor downstream cannot tell the difference.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-17
- **Completed:** 2026-05-17
- **Tasks:** 2 (both TDD-shaped, both autonomous)
- **Files modified:** 2 (both new)

## Accomplishments

- `src/bet_maker/facades/http_event_lookup.py` created with `HttpEventLookup(http_client, *, attempts=3, max_backoff=2.0)` -- structurally satisfies the `EventLookup` Protocol (verified type-clean under mypy strict) and reuses `make_retry_decorator` from Plan 04-04 (D-11 single-source-of-truth for retry policy).
- Response mapping locked per D-05/D-07/D-09:
  - 200 -> `EventSnapshot(event_id, deadline, state)` (Pydantic v2 coerces ISO 8601 string to datetime and "NEW" to `EventState.NEW`).
  - 404 -> `None` (interactor maps to 422 "event not found").
  - 4xx-other -> `httpx.HTTPStatusError` -> caught by outer except -> `LineProviderUnavailable` (route layer maps to 503).
  - 5xx after retry exhaustion -> `LineProviderUnavailable`.
  - `httpx.TransportError` after retry exhaustion -> `LineProviderUnavailable`.
- Pitfall 5 mitigation verified: the 404 short-circuit stands BEFORE `response.raise_for_status()`, so 5xx remains observable to tenacity as `httpx.HTTPStatusError` and 404 cannot be misinterpreted as transport failure.
- `tests/bet_maker/test_http_event_lookup.py` created with 5 module-level respx scenarios per D-15 + 1 marker class `TestHttpEventLookup` containing a Protocol-satisfaction proof.
- All bet_maker tests passing (134 total; +6 new); `mypy --strict` clean (69 source files); `ruff check` clean.

## Task Commits

1. **Task 1: Create src/bet_maker/facades/http_event_lookup.py** -- `c76fb1e` (feat -- HttpEventLookup over httpx+tenacity)
2. **Task 2: Create tests/bet_maker/test_http_event_lookup.py** -- `c9afc33` (test -- 5 respx scenarios + Protocol marker)

**Plan metadata:** _to be committed by this wrap-up_ (docs -- STATE/ROADMAP/SUMMARY)

## Files Created/Modified

- `src/bet_maker/facades/http_event_lookup.py` -- new (~71 lines). Module docstring cites D-11/D-14/D-05/D-07/D-09 + Pitfall 5. Imports: `httpx`, `uuid.UUID`, `bet_maker.facades.event_lookup.EventSnapshot`, `bet_maker.facades.line_provider_client.{LineProviderUnavailable, make_retry_decorator}`. No new dependencies.
- `tests/bet_maker/test_http_event_lookup.py` -- new (~145 lines). 5 module-level async tests with `@pytest.mark.asyncio` + `@respx.mock(base_url=LP_BASE_URL, ...)`; 1 marker class `TestHttpEventLookup` with a single sync test asserting `lookup: EventLookup = HttpEventLookup(client)` type-checks. Imports: `httpx`, `pytest`, `respx`, `httpx.Response`, the new facade, plus `EventLookup`/`EventState` for typing/assertions.

## Decision-by-Decision Mapping

| Decision | Effect in code |
|----------|---------------|
| **D-05** "retry on TransportError + 5xx; 4xx propagates" | Inherited via `make_retry_decorator` from Plan 04-04 (`retry_if_exception(_is_retryable)`). HttpEventLookup itself adds no retry logic -- it composes the shared factory at `__init__`. |
| **D-07** "LineProviderUnavailable on retry exhaustion" | Outer `except (httpx.TransportError, httpx.HTTPStatusError) as exc: raise LineProviderUnavailable(reason=str(exc)) from exc` catches both the retried-and-still-failing TransportError and any HTTPStatusError that wasn't shortcut by 404. |
| **D-09** "404 -> None per Protocol contract" | `if response.status_code == 404: return None` stands inside the retried `_call`, BEFORE `raise_for_status`. Verified by `test_get_event_404_returns_none` which also asserts `route.call_count == 1` -- no retry on 4xx. |
| **D-11** "independent facade, no unified client" | HttpEventLookup is a self-contained module; it does NOT import a hypothetical `LineProviderClient` aggregate. The future `list_active_events` selector (Plan 04-06) will likewise stand alone and only share `make_retry_decorator` + `LineProviderUnavailable`. |
| **D-14** "production lifespan replaces Stub with Http" | The constructor signature `(http_client, *, attempts, max_backoff)` is shaped exactly so that Plan 04-07 can call `HttpEventLookup(http_client=client, attempts=settings.line_provider_http_attempts, max_backoff=settings.line_provider_http_backoff_max_s)` -- a single line drop-in for the current `StubEventLookup()`. |
| **D-15** "respx-based unit tests cover 200/404/4xx/5xx-exhausts/5xx-then-200" | Five tests, one per scenario; each scenario asserts `route.call_count` so retry semantics are pinned numerically rather than implicitly. |

## respx Scenario List

| Test name | Mock setup | Assertion |
|-----------|-----------|-----------|
| `test_get_event_200_returns_snapshot` | `return_value=Response(200, json={event_id, coefficient, deadline (aware), state})` | `snapshot.event_id == UUID(...)`, `snapshot.state == EventState.NEW`, `snapshot.deadline.tzinfo is not None` |
| `test_get_event_404_returns_none` | `return_value=Response(404)` | `result is None`, `route.call_count == 1` (Pitfall 4 -- no retry on 4xx) |
| `test_get_event_4xx_propagates_no_retry` | `return_value=Response(422)` | `raises LineProviderUnavailable`, `route.call_count == 1` |
| `test_get_event_5xx_exhausts_raises` | `return_value=Response(503)` (every call) | `raises LineProviderUnavailable`, `route.call_count == 3` (exactly `attempts`) |
| `test_get_event_5xx_then_200_retry_succeeds` | `side_effect=[Response(503), Response(503), Response(200, json={...})]` | `snapshot.state == EventState.NEW`, `route.call_count == 3` |

Tests use `attempts=3, max_backoff=0.1` to keep `wait_exponential` capped at 100ms across retries -- total wall time observed at ~3.83s for the file, well under any reviewer-sensible limit.

## Pitfall 5 Verification Trace

**Pitfall 5 (RESEARCH line 627):** if `response.raise_for_status()` runs before the 404 check, every 404 becomes an `httpx.HTTPStatusError(status_code=404)` -- which would then be caught by the outer `except` and converted to `LineProviderUnavailable`. That mapping is wrong per D-09: 404 must produce `None`, not 503.

**Mitigation in code:** the ordering inside `_call` is explicit and documented:

```python
async def _call() -> EventSnapshot | None:
    response = await self._http_client.get(f"/event/{event_id}")
    if response.status_code == 404:  # noqa: PLR2004
        return None
    response.raise_for_status()
    ...
```

**Test evidence:** `test_get_event_404_returns_none` does two things at once -- it asserts `result is None` (so the 404 path returned, not raised) AND `route.call_count == 1` (so the predicate inside `_is_retryable` from Plan 04-04 -- which would retry an HTTPStatusError with `status_code >= 500` -- never fires on 404). The combination is the canonical Pitfall 5 proof: if the ordering were reversed, the test would either see `LineProviderUnavailable` raised (the 4xx path) or `route.call_count == 3` (if mistakenly retried).

## Auto-fixes Folded

- **PLR2004 on `404`:** the linter wanted a named constant; we kept the literal and applied `# noqa: PLR2004` because plan acceptance criterion `grep -c "if response.status_code == 404:" ...` requires the literal to remain. Single-call-site, intent obvious from context, comment-aware.
- **PLC0415 in test file:** initial draft kept `from bet_maker.facades.event_lookup import EventLookup` inside the marker test for "smallest blast radius"; ruff flagged it as non-top-level. Hoisted to the module imports -- the symbol is already needed by typing anyway.
- **E501 docstring length:** `test_get_event_5xx_exhausts_raises` had a 103-char one-line docstring. Split into a one-line summary + body line.
- **ruff format pass:** collapsed `async with httpx.AsyncClient(base_url=..., timeout=...) as client:` lines to single-line form within the 100-char limit. No semantic change.

## STRIDE Threat Coverage (as of this plan)

- **T-04-05-DoS-timeout (DoS via slow LP):** mitigated at the wiring boundary -- Plan 04-07 lifespan constructs `httpx.AsyncClient(timeout=httpx.Timeout(5.0))` per D-02 (verified planned, implemented in 04-07). Worst-case `get_event` latency = 3 * (5s call + ~2s backoff) ~= 21s, bounded.
- **T-04-05-DoS-retry (DoS via retry storm):** inherited from Plan 04-04 -- `stop_after_attempt(attempts)` cap + `attempts` bounded by `BetMakerSettings` (`ge=1, le=10`). Verified by `test_get_event_5xx_exhausts_raises` (`route.call_count == 3 == attempts`).
- **T-04-05-InputValidation (Tampering of LP payload):** mitigated via `EventSnapshot` Pydantic `extra="forbid"` + `frozen=True` -- LP schema drift would surface as `ValidationError` (not silent N/A). Acceptable: schema drift is a loud production error, not silent value loss.
- **T-04-05-Info-disclosure (LineProviderUnavailable.reason carries httpx detail):** mitigated by route layer (Plan 04-09 will translate to a static 503 detail string). The internal `.reason` is logged but never returned to clients.

## Tests

- 6 new tests in `tests/bet_maker/test_http_event_lookup.py` (5 respx scenarios + 1 Protocol marker) -- all pass.
- 134 bet_maker tests total (was 128 before plan 04-05).
- Wall time for the new file: ~3.83s (5 respx scenarios with `max_backoff=0.1`).

## Verification Commands Run

- `uv run pytest tests/bet_maker/test_http_event_lookup.py -q -x` -> 6 passed.
- `uv run pytest tests/bet_maker -q -x` -> 134 passed.
- `uv run mypy src` -> Success: no issues found in 69 source files.
- `uv run ruff check` -> All checks passed.
- `uv run python -c "from bet_maker.facades.http_event_lookup import HttpEventLookup; from bet_maker.facades.event_lookup import EventLookup; import httpx; lookup: EventLookup = HttpEventLookup(httpx.AsyncClient()); print('Protocol satisfied')"` -> prints `Protocol satisfied`.

## Downstream Readiness

Plan 04-07 (lifespan wiring) can now drop the following replacement into `entrypoints/lifespan.py` without any additional refactoring:

```python
http_client = httpx.AsyncClient(
    base_url=str(settings.line_provider_base_url),
    timeout=httpx.Timeout(5.0),
)
app.state.line_provider_http_client = http_client
app.state.event_lookup = HttpEventLookup(
    http_client=http_client,
    attempts=settings.line_provider_http_attempts,
    max_backoff=settings.line_provider_http_backoff_max_s,
)
```

Plan 04-09 (POST /bet 503 path) can rely on `LineProviderUnavailable` bubbling from `HttpEventLookup.get_event` through the unchanged `place_bet` interactor (Pitfall 7 from RESEARCH -- interactor must NOT catch).

## Requirements Progress

- **BM-04:** still Pending; closes in Plan 04-08 (GET /events route on bet-maker -- HttpEventLookup is the dependency for the upstream-validation side of BM-04 but the requirement statement is the `GET /events` endpoint itself).
