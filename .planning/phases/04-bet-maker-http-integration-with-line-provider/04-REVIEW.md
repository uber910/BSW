---
phase: 04
phase_name: bet-maker-http-integration-with-line-provider
reviewed_at: 2026-05-17T21:04:58Z
depth: standard
status: issues_found
files_reviewed: 20
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
---

# Phase 04 Code Review

## Summary
Phase 04 ships a clean, well-decomposed HTTP integration with disciplined exception ladder, correct shutdown order, frozen DTOs, and respx-driven unit tests. No critical bugs; the main residual risks live at the LP/bet-maker JSON boundary in `HttpEventLookup` (unhandled `KeyError`/`ValidationError` would escape as HTTP 500 instead of 503) and in one weak integration assertion that does not actually verify the empty-list contract.

## Findings

### Critical (must-fix)
None.

### Warning (should-fix)

### WR-01 — Malformed LP payload in HttpEventLookup escapes ladder as 500
- File: /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/http_event_lookup.py:61-66
- Severity: warning
- Category: correctness / security
- Issue: After `response.raise_for_status()` the code does `payload = response.json()` then constructs `EventSnapshot(event_id=UUID(payload["event_id"]), deadline=payload["deadline"], state=payload["state"])`. None of `json.JSONDecodeError`, `KeyError`, `ValueError` (UUID), or `pydantic.ValidationError` is caught. If LP returns a 200 with malformed or schema-drifted JSON, the exception is neither retried (it is not in `_is_retryable`) nor mapped to `LineProviderUnavailable` — it propagates up to FastAPI as a 500. That violates the intent of D-07/D-08 (which makes 503 the single failure surface for upstream issues) and degrades the "no surprise 500s at the boundary" invariant the route layer relies on. Defense-in-depth point: a malformed payload from LP is observationally indistinguishable from LP being broken; clients should see 503, not 500.
- Fix: Widen the `except` clause in `get_event` (and the analogous spot in `list_active_events`) to also catch `KeyError`, `ValueError`, `pydantic.ValidationError`, and re-raise as `LineProviderUnavailable(reason="malformed payload from line-provider")` (static reason — do not leak parser internals into `.reason`). Same treatment in `selectors/list_active_events.py:43` where `EventRead.model_validate(item)` can raise `ValidationError` and currently escapes.
- Decision impact: Tightens D-07/D-08/D-10 invariant (LP-related failures always surface as 503) without changing decision text.

### WR-02 — `LineProviderUnavailable.reason` propagates raw httpx URL/exception text into logs
- File: /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/http_event_lookup.py:71; /Users/dmitrydankov/Personal/BSW/src/bet_maker/selectors/list_active_events.py:48
- Severity: warning
- Category: security (info disclosure in logs)
- Issue: `raise LineProviderUnavailable(reason=str(exc))` puts `str(httpx.HTTPStatusError)` / `str(httpx.TransportError)` into the exception's `.reason`. The route handler converts to a static client-facing detail correctly, but `.reason` itself ends up wherever the exception is logged (structlog default `JSONRenderer` will serialise `exc.args[0]`). For typical httpx exceptions this includes the full LP URL with port — currently internal (`http://line-provider:8000`), but if `line_provider_base_url` is ever pointed at a tenant-prefixed host or one with embedded credentials (`http://user:pass@host/...`), those would land in operator logs verbatim. Not a critical issue today (URL has no secrets), but the pattern is fragile.
- Fix: Make `.reason` a fixed-shape, redacted summary. E.g. `LineProviderUnavailable(reason=f"{type(exc).__name__}: {getattr(exc.response, 'status_code', 'no-response')}")` for HTTPStatusError; or pull only `type(exc).__name__` for TransportError. The full `exc` is still chained via `from exc` for tracebacks (already done) — that goes to traceback handlers, not to a default structured log field.
- Decision impact: Preserves D-07 contract (`LineProviderUnavailable(reason: str)` signature). Strengthens hygiene.

### WR-03 — `test_returns_empty_list_when_lp_empty` does not actually verify "empty"
- File: /Users/dmitrydankov/Personal/BSW/tests/bet_maker/test_events_routes.py:119-133
- Severity: warning
- Category: test quality
- Issue: The test docstring claims "empty LP -> bet-maker GET /events returns []", but the body explicitly downgrades to `assert isinstance(response.json(), list)` because session-scoped LP carries state across tests. So the assertion does not verify the empty-list contract at all — it only checks the response is JSON-array-shaped (which `response_model=list[EventRead]` already guarantees). This is dead test coverage for D-10's empty-case branch.
- Fix: Either (a) move the test to its own LP fixture (function-scoped LP via `respx` mocking `/events` -> `Response(200, json=[])` — same pattern already used in `TestGetEvents503`), or (b) compute the LP baseline via `lp_client.get("/events")`, then assert `bet-maker /events` returns exactly that baseline (sub-set semantics give a real invariant: bet-maker reflects LP). Option (a) is cleaner and matches the rest of the suite.
- Decision impact: Restores genuine D-10 empty-case coverage; verifier reported it as PASS based on the existing weak assertion.

### Info (nice-to-have)

### IN-01 — `_call` rebuilds retry-decorated closure on every invocation
- File: /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/http_event_lookup.py:55-67; /Users/dmitrydankov/Personal/BSW/src/bet_maker/selectors/list_active_events.py:37-43
- Severity: info
- Category: code quality / micro-perf
- Issue: In `HttpEventLookup.get_event`, `_call` is redefined every call and `@self._retry` re-wraps it; in `list_active_events`, `make_retry_decorator` is rebuilt every call. Functionally fine — tenacity's `Retrying` object is cheap — but it allocates per request. Stable, single-source-of-truth alternative: define `_call` at class scope (or as a separate module-level coroutine), then call `await self._retry(_call)(self._http_client, event_id)`.
- Fix: Optional refactor; safe to leave.
- Decision impact: None.

### IN-02 — `_F` TypeVar is bound to `Callable[..., Awaitable[Any]]` and the cast is loose
- File: /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/line_provider_client.py:34, 80-96
- Severity: info
- Category: type safety
- Issue: `make_retry_decorator(...) -> Callable[[_F], _F]` claims an identity-preserving decorator, but `tenacity.retry(...)` returns its own typed wrapper whose signature is `Callable[..., Coroutine[Any, Any, R]]` — not literally `_F`. The promise to the caller is therefore slightly stronger than what tenacity actually delivers; in practice mypy strict is satisfied because tenacity's stubs are loose, so the `Any` leakage is invisible.
- Fix: Optional. Either tighten the bound to `Callable[..., Coroutine[Any, Any, Any]]` and accept the type erasure, or document why the identity-preserving claim is pragmatic.
- Decision impact: None.

### IN-03 — `_log_before_sleep` does not bind contextvars despite citing Pitfall A7 mitigation
- File: /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/line_provider_client.py:64-77
- Severity: info
- Category: code quality / docstring accuracy
- Issue: The docstring says "Pitfall A7 mitigation: keep all retry state inside retry_state — no module-level contextvars". That is true (no contextvars used) but it is not really a "mitigation" — it is just "we did not use contextvars". The phrasing reads as if active mitigation occurred. Minor wording polish.
- Fix: Reword to "Pitfall A7 note: this function deliberately does not touch contextvars; retry state lives inside `retry_state` only."
- Decision impact: None.

### IN-04 — `test_post_bet_503_when_line_provider_unavailable` uses `lambda: _RaisingLookup()` with `# noqa: PLW0108`
- File: /Users/dmitrydankov/Personal/BSW/tests/bet_maker/test_bet_routes.py:190, 227
- Severity: info
- Category: test quality
- Issue: `lambda: _RaisingLookup()` is flagged by ruff (`PLW0108` — unnecessary lambda) because `_RaisingLookup` itself is a zero-arg callable. Suppressing with `# noqa` is fine, but `lambda: _RaisingLookup()` returns a fresh instance per call; `_RaisingLookup` (the class) returns a fresh instance per call too — semantically equivalent. Dropping the lambda removes the noqa.
- Fix: `app.dependency_overrides[get_event_lookup] = _RaisingLookup`.
- Decision impact: None.

### IN-05 — `_clear_event_lookup` autouse fixture has an unused `_auto_truncate` sibling that doesn't return anything
- File: /Users/dmitrydankov/Personal/BSW/tests/bet_maker/conftest.py:15-23
- Severity: info
- Category: code quality
- Issue: `_auto_truncate(truncate_bets: None) -> None` is an autouse fixture whose only job is to pull `truncate_bets` into the autouse layer. It is functionally correct but reads as a no-op. Convention-wise this is fine for the chaining pattern, but adding a one-line `# autouse adapter` comment would help readers. Already documented in the docstring, so this is low-priority.
- Fix: No change needed; or replace with a `pytest.fixture(autouse=True)(truncate_bets)` registration in conftest if you prefer terser.
- Decision impact: None.

### IN-06 — Hardcoded `404`, `500` magic numbers handled with `# noqa: PLR2004` but `>= 500` is open-coded
- File: /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/http_event_lookup.py:58; /Users/dmitrydankov/Personal/BSW/src/bet_maker/facades/line_provider_client.py:36, 60
- Severity: info
- Category: code quality / consistency
- Issue: `http_event_lookup.py` uses `if response.status_code == 404:  # noqa: PLR2004`. `line_provider_client.py` factors `_HTTP_5XX_FLOOR = 500`. Inconsistent: introduce `_HTTP_NOT_FOUND = 404` next to `_HTTP_5XX_FLOOR` and drop the `noqa`, or accept the `noqa` and remove the constant. Either is fine; consistency is the value.
- Fix: Pick one style across both files.
- Decision impact: None.

## Strengths
- Exception ladder is correct and well-justified: `LineProviderUnavailable` caught before `EventNotBettable` in `bets.py:48-57`, with a dedicated test (`test_post_bet_503_ladder_precedes_422`) that asserts the order behaviourally — not just by source-line index.
- D-09/Pitfall 5 ordering is correctly enforced: in `http_event_lookup.py:58-60` the 404 short-circuit precedes `raise_for_status`, and `test_get_event_404_returns_none` asserts `route.call_count == 1` to lock in that 404 is not retried.
- D-20 shutdown order is verified by behaviour, not source order: `test_aclose_before_dispose` monkey-patches both methods and asserts on a captured call list — protects against future refactors that silently reorder the `finally`.
- Frozen, `extra="forbid"` DTOs (`EventRead`, `EventSnapshot`) with explicit value-parity test against `line_provider.schemas.events.EventState` — guards LP/bet-maker drift exactly as D-12/D-13 require.
- Test coverage is thorough across all 5 retry-policy scenarios for both `HttpEventLookup` and `list_active_events`, with deterministic call-count assertions (`route.call_count == attempts`) that catch off-by-one in retry exhaustion.

## Decision Audit
- D-02 (httpx.Timeout(5.0) explicit) — present at `lifespan.py:47` with the exact `httpx.Timeout(5.0)` constructor and inline "Pitfall 1" citation. Matches.
- D-08 (POST /bet ladder order: LP-first, ENB-second) — `bets.py:48 < bets.py:53`; test `test_post_bet_503_ladder_precedes_422` proves the order is semantic, not coincidental. Matches.
- D-09 (404 -> None; no retry) — `http_event_lookup.py:58-60` (404 short-circuit before `raise_for_status`); `_is_retryable` returns False for 4xx; `test_get_event_404_returns_none` locks in `route.call_count == 1`. Matches.
- D-13 (EventRead duplicated, frozen, extra='forbid') — `schemas/events.py:37-43` carries `frozen=True, extra="forbid"`; `test_event_read_extra_forbid`, `test_event_read_frozen`, and `test_eventstate_value_parity_with_line_provider` all green. Matches.
- D-20 (aclose before dispose; nested try/finally) — `lifespan.py:67-70` uses nested `try/finally` so `dispose` runs even on `aclose` failure; `test_aclose_before_dispose` asserts order via patched call recording. Matches.

## Next Steps
Review findings; WR-01 is the highest-value follow-up (broadens the LineProviderUnavailable catch surface in `HttpEventLookup` and `list_active_events` to include `KeyError` / `ValueError` / `ValidationError` / `json.JSONDecodeError`). WR-02 and WR-03 are quick hygiene wins. Info-level items are optional. Consider `/gsd-code-review 04 --fix` for the WR-01 / WR-02 / IN-04 / IN-06 cluster.
