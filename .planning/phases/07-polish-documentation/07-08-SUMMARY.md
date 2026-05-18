---
plan: 07-08-asyncapi-smoke-tests
status: complete
date: 2026-05-18
---

# Plan 07-08 — AsyncAPI Smoke Tests

## Purpose

Verify FastStream's default `/asyncapi` endpoint is exposed on both services
per CONTEXT.md D-10. A regression that drops `app.include_router(rabbit_router)`
would silently strip the endpoint — these smoke tests catch that.

## Files Created

- `tests/bet_maker/test_asyncapi_smoke.py` — `TestAsyncAPISmoke::test_asyncapi_endpoint_returns_200` (class style, `loop_scope="session"`)
- `tests/line_provider/test_asyncapi_smoke.py` — `test_asyncapi_endpoint_returns_200` (plain async-def style; conftest provides session client)

## Test Run

```
$ uv run pytest -q tests/bet_maker/test_asyncapi_smoke.py tests/line_provider/test_asyncapi_smoke.py
2 passed, 5 warnings in 5.55s
```

Both endpoints return 200 with non-empty body and content-type containing
`html` (FastStream UI render).

## Test Node IDs (for 07-AUDIT.md reference)

- `tests/bet_maker/test_asyncapi_smoke.py::TestAsyncAPISmoke::test_asyncapi_endpoint_returns_200`
- `tests/line_provider/test_asyncapi_smoke.py::test_asyncapi_endpoint_returns_200`

## Decisions Honored

- D-10: smoke test only; no manual schema construction (FastStream auto-generates)
- D-11: snapshot NOT committed; reviewer can `curl :8001/asyncapi -o asyncapi.json` per README §Next-step extensions

## Commits

- `e32884a` test(07-08): /asyncapi smoke tests on both services (D-10)
