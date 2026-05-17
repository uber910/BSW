---
phase: 04
phase_name: bet-maker-http-integration-with-line-provider
fixed_at: 2026-05-17T21:18:39Z
fix_scope: critical_warning
findings_in_scope: 3
fixed: 3
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 04 Code Review Fixes

## Summary
All three Warning findings from the Phase 04 code review were fixed and committed atomically. WR-01 broadens the LP/bet-maker JSON-boundary catch surface so malformed payloads surface as 503 instead of 500; WR-02 redacts the LineProviderUnavailable.reason shape to prevent URL/credential leakage into structured logs; WR-03 replaces a weak shape-only assertion with a deterministic respx-overlay path that genuinely verifies the empty-list contract.

## Applied Fixes

### WR-01 — Malformed LP payload in HttpEventLookup escapes ladder as 500 — FIXED
- Commit: 5829db3
- Files: src/bet_maker/facades/http_event_lookup.py, src/bet_maker/selectors/list_active_events.py, tests/bet_maker/test_http_event_lookup.py, tests/bet_maker/test_list_active_events.py
- Approach: Added a second `except` arm in both `HttpEventLookup.get_event` and `list_active_events` that catches `JSONDecodeError`, `KeyError`, `ValueError` (UUID parsing), and `pydantic.ValidationError`. All four are re-raised as `LineProviderUnavailable(reason="malformed payload from line-provider")` with `from exc` so tracebacks are preserved. Reason is a static string — parser internals never leak into `.reason`. Tightens the D-07/D-08/D-10 invariant that LP-related failures always surface as 503.
- Verification: 16 tests pass in `tests/bet_maker/test_http_event_lookup.py + test_list_active_events.py`. New tests: `test_get_event_malformed_json_raises_unavailable`, `test_get_event_missing_key_raises_unavailable`, `test_get_event_invalid_uuid_raises_unavailable`, `test_malformed_json_raises_unavailable`, `test_schema_drift_raises_unavailable`. mypy + ruff clean.

### WR-02 — LineProviderUnavailable.reason propagates raw httpx URL/exception text into logs — FIXED
- Commit: 5889ae5
- Files: src/bet_maker/facades/http_event_lookup.py, src/bet_maker/selectors/list_active_events.py, tests/bet_maker/test_http_event_lookup.py, tests/bet_maker/test_list_active_events.py
- Approach: Split the prior combined `(httpx.TransportError, httpx.HTTPStatusError)` clause into two arms with redacted `.reason` strings: `HTTPStatusError` -> `f"HTTPStatusError: {response.status_code}"`, `TransportError` -> `type(exc).__name__`. The original exception is still chained via `from exc` for traceback handlers — only the structured-log-visible `.reason` field is redacted. Route detail strings ("line-provider unreachable" / "event validation unavailable: line-provider unreachable") are unchanged because the route layer maps `LineProviderUnavailable` to a static HTTP detail anyway.
- Verification: 20 tests pass in `tests/bet_maker/test_http_event_lookup.py + test_list_active_events.py`; integration suite `tests/bet_maker/test_events_routes.py` (6 tests) confirms route 503 detail unchanged. New tests: `test_get_event_5xx_reason_is_redacted`, `test_get_event_transport_error_reason_is_redacted`, `test_5xx_reason_is_redacted`, `test_transport_error_reason_is_redacted`. mypy + ruff clean.

### WR-03 — test_returns_empty_list_when_lp_empty does not actually verify "empty" — FIXED
- Commit: b445a40
- Files: tests/bet_maker/test_events_routes.py
- Approach: Rewrote the test using the same respx-overlay pattern as `TestGetEvents503`. A function-scoped `respx.mock(base_url=LP_BASE_URL)` intercepts `GET /events` and returns `Response(200, json=[])`, with a fresh `AsyncClient` injected via `app.dependency_overrides[get_line_provider_http_client]`. This is independent of the session-scoped real LP state, so `assert response.json() == []` is now reliable. Removes the comment-acknowledged downgrade to `isinstance(..., list)`.
- Verification: `tests/bet_maker/test_events_routes.py::TestGetEventsAgainstRealLp::test_returns_empty_list_when_lp_empty` passes; full `test_events_routes.py` (6 tests) green.

## Skipped Findings
None.

## Test Impact
- Before: 244 passed
- After: 253 passed
- New tests added:
  - tests/bet_maker/test_http_event_lookup.py: test_get_event_malformed_json_raises_unavailable, test_get_event_missing_key_raises_unavailable, test_get_event_invalid_uuid_raises_unavailable, test_get_event_5xx_reason_is_redacted, test_get_event_transport_error_reason_is_redacted
  - tests/bet_maker/test_list_active_events.py: test_malformed_json_raises_unavailable, test_schema_drift_raises_unavailable, test_5xx_reason_is_redacted, test_transport_error_reason_is_redacted

## Next Steps
Re-run /gsd-code-review 04 to confirm clean.
