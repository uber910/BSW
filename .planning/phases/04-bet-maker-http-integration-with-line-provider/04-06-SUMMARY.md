---
phase: 04-bet-maker-http-integration-with-line-provider
plan: 06
subsystem: selectors
tags: [httpx, tenacity, respx, line-provider, list-active-events, bet-maker, retry, 503]

requires:
  - phase: 04-bet-maker-http-integration-with-line-provider
    provides: "Plan 04-02 EventRead DTO (frozen + extra='forbid') + Plan 04-04 shared retry-factory (make_retry_decorator) + LineProviderUnavailable exception"
provides:
  - "src/bet_maker/selectors/list_active_events.py -- async selector hitting LP GET /events through shared retry-decorator, returning list[EventRead]"
  - "tests/bet_maker/test_list_active_events.py -- 4 respx-driven contractual scenarios + 1 marker class"
affects:
  - "04-07 lifespan wiring -- selector consumes the same httpx.AsyncClient singleton constructed there"
  - "04-08 bet-maker GET /events route -- delegates to list_active_events and translates LineProviderUnavailable to HTTP 503 per D-10"

tech-stack:
  added: []
  patterns:
    - "Module-level async selector pattern: `async def name(http_client, *, attempts, max_backoff) -> list[DTO]` -- mirrors HttpEventLookup's facade-method shape (Plan 04-05) but is a plain function rather than a class because the selector has no state to bind and no Protocol to satisfy."
    - "List-of-DTOs invariant (Anti-Pattern 5 mitigation): `[EventRead.model_validate(item) for item in response.json()]` inside the iteration guarantees callers receive immutable Pydantic DTOs -- never raw dicts; combined with `extra='forbid'`, LP schema drift surfaces as a loud ValidationError rather than silent partial data."
    - "Pitfall 5 inverted: no 404 short-circuit branch is needed for /events because LP's /events route has no 4xx response paths (state=NEW + deadline>now filter only). Any unexpected 4xx falls through to LineProviderUnavailable -- the correct fail-loud semantics for an unannounced contract change."

key-files:
  created:
    - "src/bet_maker/selectors/list_active_events.py (~48 lines -- module docstring cites BM-04/D-10/D-11/D-13/D-01; outer try/except over (TransportError, HTTPStatusError) collapses to LineProviderUnavailable)"
    - "tests/bet_maker/test_list_active_events.py (~132 lines -- 4 respx scenarios + TestListActiveEvents marker class)"
  modified: []

key-decisions:
  - "Module-level async function rather than a class -- the selector has no instance state (httpx.AsyncClient is passed in per call from DI). Class wrapping would have been pure ceremony. Mirrors `list_bets` selector shape (which takes AsyncSession the same way)."
  - "No 404 short-circuit branch -- LP /events route is documented (line_provider/entrypoints/api/events.py:82-88) as never returning 404. Adding the branch defensively would have created dead code and broken the symmetry with the verified RESEARCH skeleton (lines 779-815). If LP ever does return 4xx on /events, fail-loud via LineProviderUnavailable is the right behaviour anyway."
  - "Marker class `TestListActiveEvents` retained alongside 4 module-level scenarios -- plan must_haves declare `contains: 'class TestListActiveEvents'` while the plan body shows function-level decorators. The marker class holds one inspect-based invariant (`iscoroutinefunction`) -- smallest-surface satisfaction of both constraints, mirroring the HttpEventLookup test file from Plan 04-05."

patterns-established:
  - "Selector idiom for cross-service HTTP reads: free async function + shared retry-decorator from a co-located facade module (line_provider_client). The retry-decorator is the only contract shared across HttpEventLookup (class facade) and list_active_events (function selector) -- proves D-11 'independent facade, no unified client' end-to-end."
  - "respx scenario coverage convention for list endpoints: empty / non-empty / 5xx-then-200 / 5xx-exhausts -- four scenarios are the minimum complete set for a single-endpoint list selector (cf. Plan 04-05's five for a single-endpoint get-by-id facade where 404 is meaningful)."

requirements-completed: []
requirements-progressed: [BM-04]

duration: ~3min
completed: 2026-05-17
---

# Phase 04 / Plan 06: list_active_events selector (D-10/D-11) -- Summary

**The read-side proxy is wired: `list_active_events` reuses Plan 04-04's shared retry-factory to turn line-provider's `GET /events` into a list[EventRead] -- bet-maker's `GET /events` route in Plan 04-08 will drop in as a single `await` call.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-17
- **Completed:** 2026-05-17
- **Tasks:** 2 (both TDD-shaped, both autonomous)
- **Files modified:** 2 (both new)

## Accomplishments

- `src/bet_maker/selectors/list_active_events.py` created with `async list_active_events(http_client, *, attempts=3, max_backoff=2.0) -> list[EventRead]`. The inner `_call` is decorated with the shared `make_retry_decorator` from Plan 04-04 (D-11 single-source-of-truth for retry policy) and parses the response body per item via `EventRead.model_validate` (D-13 frozen + extra="forbid" -- LP schema drift surfaces as ValidationError; Anti-Pattern 5 mitigation -- callers never see raw dicts).
- Response mapping locked per D-05/D-07/D-10:
  - 200 + JSON array -> `list[EventRead]` (possibly empty per D-10).
  - 5xx after retry exhaustion -> `LineProviderUnavailable` (route layer in Plan 04-08 maps to HTTP 503).
  - 4xx from LP (not expected; LP /events has no 4xx response paths) -> falls through the outer except -> `LineProviderUnavailable` (Pitfall 5 inverted -- no short-circuit branch required).
  - `httpx.TransportError` after retry exhaustion -> `LineProviderUnavailable`.
- D-01 alignment: no TTL cache. Every call hits LP fresh; bet-maker GET /events latency = one LP roundtrip plus retry-backoff. REQUIREMENTS.md BM-04 was synchronised to this contract in Plan 04-01.
- `tests/bet_maker/test_list_active_events.py` created with 4 module-level respx scenarios per D-15 + 1 marker class `TestListActiveEvents` containing an `iscoroutinefunction` invariant.
- All bet_maker tests passing (139 total; +5 new -- 4 respx scenarios + 1 marker); `mypy --strict` clean (70 source files); `ruff check` clean.

## Function Signature

```python
async def list_active_events(
    http_client: httpx.AsyncClient,
    *,
    attempts: int = 3,
    max_backoff: float = 2.0,
) -> list[EventRead]:
    ...
```

- `http_client`: the lifespan-managed singleton (Plan 04-07 will build it with `httpx.AsyncClient(base_url=str(settings.line_provider_base_url), timeout=httpx.Timeout(5.0))`).
- `attempts` / `max_backoff`: defaults match Plan 04-04 / D-21 for HTTP routes. Plan 04-08 will pass `settings.line_provider_http_attempts` and `settings.line_provider_http_backoff_max_s` from `BetMakerSettings`.

## Retry Behaviour

The inner `_call` coroutine is decorated by the shared `make_retry_decorator(attempts, max_backoff)`:

- Retries `httpx.TransportError` (timeout/connect/network) and `httpx.HTTPStatusError` where `status_code >= 500` (D-05).
- Does **not** retry 4xx -- caught by the outer `except` and surfaced as `LineProviderUnavailable` without further attempts (Pitfall 4 mitigation -- 4xx is contract response, not transient failure).
- Stop policy: `stop_after_attempt(attempts)`; verified by `test_5xx_exhausts_raises_unavailable` asserting `route.call_count == attempts`.
- Wait policy: `wait_exponential(multiplier=0.5, min=0.5, max=max_backoff)` -- tests pass `max_backoff=0.1` to keep total wall time under 5s.

## List-of-DTOs Invariant (Anti-Pattern 5 Mitigation)

```python
return [EventRead.model_validate(item) for item in response.json()]
```

- Every element in the returned list is an immutable Pydantic `EventRead` instance (`frozen=True`).
- `extra="forbid"` means an unannounced LP schema change (e.g. a new field added in line-provider) raises `ValidationError` at the selector boundary rather than silently dropping data.
- Anti-Pattern 5 ("returning raw dicts") cannot occur: the type annotation `-> list[EventRead]` is enforced by mypy strict, and the comprehension materialises DTOs before return.
- `value-parity` tests (test_schemas in Plan 04-02) plus this behaviour together guarantee callers see typed UUIDs, Decimals, AwareDatetimes, and EventState enum members -- not strings.

## Decision-by-Decision Mapping

| Decision | Effect in code |
|----------|---------------|
| **D-01** "no TTL cache in P4" | Selector calls `await http_client.get("/events")` on every invocation. No module-level state, no in-flight singleton, no memoisation. |
| **D-05** "retry on TransportError + 5xx; 4xx propagates" | Inherited via `make_retry_decorator` from Plan 04-04 (`retry_if_exception(_is_retryable)`). Selector itself adds no retry logic -- it composes the shared factory at runtime. |
| **D-07** "LineProviderUnavailable on retry exhaustion" | Outer `except (httpx.TransportError, httpx.HTTPStatusError) as exc: raise LineProviderUnavailable(reason=str(exc)) from exc` catches both retried-and-still-failing transport errors and any HTTPStatusError that wasn't swallowed by retry. |
| **D-10** "GET /events 200 / [] / 503 semantics on the bet-maker side" | 200 -> `list[EventRead]` (including `[]`), retry-exhausted 5xx / unexpected 4xx -> `LineProviderUnavailable` (Plan 04-08 route translates to 503). |
| **D-11** "independent selector -- no unified client" | The module imports only `make_retry_decorator` and `LineProviderUnavailable` from `line_provider_client` -- no hypothetical `LineProviderClient` aggregate. Same pattern as HttpEventLookup (Plan 04-05). |
| **D-13** "EventRead duplicated at bet-maker boundary" | `from bet_maker.schemas.events import EventRead` -- the duplicated DTO with frozen + extra="forbid". Selector never imports from `line_provider.schemas.events`. |
| **D-15** "respx-based unit tests cover empty/list/5xx-retry/5xx-exhausts" | Four tests, one per scenario; each scenario asserts `route.call_count` where retry behaviour is observable (3 == attempts for retry-success and exhaustion). |

## respx Scenario List

| Test name | Mock setup | Assertion |
|-----------|-----------|-----------|
| `test_returns_empty_list_when_lp_empty` | `return_value=Response(200, json=[])` | `result == []` |
| `test_returns_event_read_list_when_lp_has_events` | `return_value=Response(200, json=[e1, e2])` (both shaped as LP EventRead) | `len(result) == 2`, all elements are `EventRead`, event_id set matches input, all `state == EventState.NEW` |
| `test_5xx_then_200_retry_succeeds` | `side_effect=[Response(503), Response(503), Response(200, json=[event])]` | `len(result) == 1`, `result[0].event_id == event_id`, `route.call_count == 3` |
| `test_5xx_exhausts_raises_unavailable` | `return_value=Response(503)` (every call) | `raises LineProviderUnavailable`, `route.call_count == 3` (== attempts) |
| `TestListActiveEvents.test_list_active_events_is_async_callable` | n/a (static check) | `inspect.iscoroutinefunction(list_active_events) is True` |

Tests use `attempts=3, max_backoff=0.1` to cap `wait_exponential` at 100ms across retries -- total wall time observed at ~3.87s for the file.

## Pitfall 5 Inverted -- No 404 Branch

Plan 04-05's HttpEventLookup needed the 404 short-circuit ordering because LP's `GET /event/{id}` route has a 4xx response path (404 when the event isn't found) and 404 -> None is the contract per D-09.

LP's `GET /events` route has **no** 4xx response paths -- it always returns 200 with an array (possibly empty per D-10). The selector therefore needs no special-case branch:

```python
response = await http_client.get("/events")
response.raise_for_status()  # raises only on >=400; in practice >=500 by LP contract
return [EventRead.model_validate(item) for item in response.json()]
```

Any unexpected 4xx (which would mean LP's contract changed) is caught by the outer `except` and converted to `LineProviderUnavailable` -- the right fail-loud semantics for an unannounced contract change.

## Auto-fixes Folded

- **PLC0415 in test file:** initial draft had `import inspect` inside the marker test's method body; ruff flagged it as non-top-level. Hoisted to the module imports next to the other stdlib import (`uuid.uuid4`).
- **E501 docstring length:** `test_5xx_exhausts_raises_unavailable` had a 104-char one-line docstring. Split into a one-line summary + body line documenting the `route.call_count == attempts` invariant.

No semantic changes; both fixes are pure surface concerns. No deviations from plan.

## STRIDE Threat Coverage

- **T-04-06-DoS-timeout (DoS via slow LP):** mitigated at the wiring boundary -- Plan 04-07 lifespan constructs `httpx.AsyncClient(timeout=httpx.Timeout(5.0))` per D-02. Worst-case `list_active_events` latency = 3 * (5s call + ~0.1-2s backoff) ~= 21s, bounded.
- **T-04-06-DoS-retry (DoS via retry storm):** inherited from Plan 04-04 (`stop_after_attempt(attempts)`) + Plan 04-03 (`attempts: int = Field(ge=1, le=10)`). Verified by `test_5xx_exhausts_raises_unavailable` asserting `route.call_count == 3 == attempts`.
- **T-04-06-InputValidation (Tampering of LP payload):** mitigated via `EventRead.model_validate` per item with `extra="forbid"` + `frozen=True` -- LP schema drift surfaces as `ValidationError` for the whole call (partial success would be confusing).
- **T-04-06-DoS-largepayload (unbounded array):** accept LOW -- LP only returns active events (state=NEW + deadline > now). Test-task scale -> expected size <= 1000. Pagination deferred to P6 batch endpoint (per CONTEXT "Out of scope").

## Tests

- 5 new tests in `tests/bet_maker/test_list_active_events.py` (4 respx scenarios + 1 marker) -- all pass.
- 139 bet_maker tests total (was 134 before Plan 04-06).
- Wall time for the new file: ~3.87s (4 respx scenarios with `max_backoff=0.1`).

## Verification Commands Run

- `uv run pytest tests/bet_maker/test_list_active_events.py -q -x` -> 5 passed.
- `uv run pytest tests/bet_maker -q -x` -> 139 passed.
- `uv run mypy src` -> Success: no issues found in 70 source files.
- `uv run ruff check` -> All checks passed.
- `uv run python -c "from bet_maker.selectors.list_active_events import list_active_events; print('OK')"` -> prints `OK`.

## Task Commits

1. **Task 1: Create src/bet_maker/selectors/list_active_events.py** -- `85adb66` (feat -- list_active_events selector)
2. **Task 2: Create tests/bet_maker/test_list_active_events.py** -- `d182a04` (test -- 4 respx scenarios + marker class)

**Plan metadata:** _to be committed by this wrap-up_ (docs -- STATE/ROADMAP/SUMMARY)

## Files Created/Modified

- `src/bet_maker/selectors/list_active_events.py` -- new (~48 lines). Module docstring cites BM-04/D-01/D-10/D-11/D-13. Imports: `httpx`, `bet_maker.facades.line_provider_client.{LineProviderUnavailable, make_retry_decorator}`, `bet_maker.schemas.events.EventRead`. No new dependencies.
- `tests/bet_maker/test_list_active_events.py` -- new (~132 lines). 4 module-level async tests with `@pytest.mark.asyncio` + `@respx.mock(base_url=LP_BASE_URL, ...)`; 1 marker class `TestListActiveEvents` containing a single sync `iscoroutinefunction` assertion. Imports: `inspect`, `httpx`, `pytest`, `respx`, `httpx.Response`, `uuid.uuid4`, plus the selector and its DTOs.

## Decisions Made

- Function-level selector rather than class wrapper -- no state to bind, no Protocol to satisfy. Mirrors `list_bets` shape (which takes `AsyncSession` the same way).
- No 404 short-circuit branch -- LP /events has no 4xx response paths per the verified LP route contract. Adding the branch defensively would have created dead code.
- Marker class `TestListActiveEvents` kept alongside module-level respx scenarios -- satisfies the `must_haves.artifacts.contains: "class TestListActiveEvents"` directive without complicating the four scenario decorators.

## Deviations from Plan

None - plan executed exactly as written. Two surface-level auto-fixes (PLC0415 import hoist + E501 docstring split) folded into the test commit; no semantic changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-07 (lifespan wiring) can now construct the singleton `httpx.AsyncClient` and pin it to `app.state.line_provider_http_client`; both `HttpEventLookup` (Plan 04-05) and `list_active_events` (this plan) will consume it.
- Plan 04-08 (bet-maker GET /events route) can drop the following call:

```python
try:
    events = await list_active_events(
        request.app.state.line_provider_http_client,
        attempts=settings.line_provider_http_attempts,
        max_backoff=settings.line_provider_http_backoff_max_s,
    )
except LineProviderUnavailable as exc:
    raise HTTPException(status_code=503, detail="line-provider unavailable") from exc
return events
```

- BM-04 still Pending -- closes in Plan 04-08 (the route itself is the requirement).

## Requirements Progress

- **BM-04:** progressed (this plan delivers the dependency; Plan 04-08 closes BM-04 by wiring the route on top of `list_active_events`).

---
*Phase: 04-bet-maker-http-integration-with-line-provider*
*Completed: 2026-05-17*
