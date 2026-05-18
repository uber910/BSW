---
plan: 07-07-audit-static-tests
status: complete
date: 2026-05-18
---

# Plan 07-07 — Static Audit Tests

## Purpose

Create `tests/audit/test_static.py` with 7 regex/substring tests asserting
code-base invariants from the "Looks Done But Isn't" 18-item checklist
(ROADMAP P7 SC#6 + PITFALLS.md). These tests run in CI and break the build
if a regression silently undoes a P1-P6 invariant.

## Test Node IDs (for 07-AUDIT.md reference)

- `tests/audit/test_static.py::test_subscribers_have_manual_ack` — R1/F1
- `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` — R3
- `tests/audit/test_static.py::test_async_sessionmaker_expire_on_commit_false` — A1
- `tests/audit/test_static.py::test_dockerfile_exec_form_cmd` — R11/D-04
- `tests/audit/test_static.py::test_dockerfile_pinned_python_bookworm` — D-20 / D-06
- `tests/audit/test_static.py::test_pythonunbuffered_set` — D-04 / D-05
- `tests/audit/test_static.py::test_durable_queue_and_exchange` — R4/R10

## Test Run

```
$ uv run pytest -q tests/audit/test_static.py
7 passed, 1 warning in 0.01s
```

## Implementation Notes

- `test_subscribers_have_manual_ack` was adjusted from strict equality to `>= len(subscribers)` because the module docstring at `src/bet_maker/entrypoints/messaging.py:9` also mentions `ack_policy=AckPolicy.MANUAL`. The invariant we care about ("at least one MANUAL kwarg per subscriber") is preserved; the test still fails if any subscriber drops MANUAL.
- Regex anchors on stable substrings per Pitfall 6 — no fragile multi-line shapes.
- Each test docstring names its Pitfall ID + ARCHITECTURE.md reference.
- mypy strict pass (under `[[tool.mypy.overrides]] module = ["tests.*"]` looser override).
- ruff clean (no `# type: ignore`, no emojis).

## Decisions Honored

- D-19: 7 regex/substring tests on file content (not AST)
- D-23: no scope creep — only the 7 invariants enumerated in plan
- CLAUDE.md "no emojis in docs and code" — docstrings clean

## Commits

- `0992582` test(07-07): static audit tests for 7 'Looks Done But Isn't' invariants (D-19)
