---
phase: 07-polish-documentation
plan: 11
type: execute
wave: 3
depends_on: [02, 03, 04, 05, 06, 07, 08]
files_modified: []
autonomous: true
requirements: [QA-01]
must_haves:
  truths:
    - "uv run mypy src — zero errors across both line_provider and bet_maker packages"
    - "grep -rn \"# type: ignore\" src/ returns zero results (no type-ignores in production code)"
    - "If any # type: ignore appears in plans 07-02..07-08, document the rationale OR remove it"
    - "Verification-only plan — no code edits expected (RESEARCH.md A5 — already verified empty before P7 work)"
  artifacts:
    - path: ".planning/phases/07-polish-documentation/07-11-SUMMARY.md"
      provides: "mypy strict verification record + type:ignore audit log"
  key_links:
    - from: ".planning/phases/07-polish-documentation/07-11-SUMMARY.md"
      to: ".github/workflows/ci.yml::steps::Mypy strict"
      via: "CI step uv run mypy src already enforces; this plan re-verifies end-to-end"
      pattern: "uv run mypy src"
---

<objective>
Final mypy strict verification per CONTEXT.md D-12 + D-13. This is a **verification-only plan** — RESEARCH.md A5 already confirmed `grep -rn "# type: ignore" src/` returns zero results today, and plans 07-02..07-08 all assert mypy strict zero errors at task acceptance time.

Purpose: codify the verification in a single phase-level pass, document any `# type: ignore` rationale if discovered (none expected), and produce a SUMMARY confirming QA-01 is satisfied end-to-end.

Output: no code changes. SUMMARY.md records the audit. AUDIT.md row #17 references this plan's verification.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-polish-documentation/07-CONTEXT.md
@.planning/phases/07-polish-documentation/07-RESEARCH.md
@.planning/phases/07-polish-documentation/07-AUDIT.md
@.planning/REQUIREMENTS.md
</context>

<threat_model>
N/A — verification-only plan; no code change, no attack surface.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Verify mypy strict + audit # type: ignore in src/</name>
  <files></files>
  <read_first>
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-12, D-13, D-14)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (A5 — empty grep verified)
    - .planning/REQUIREMENTS.md (QA-01)
    - .github/workflows/ci.yml (Mypy strict step — confirm in place)
  </read_first>
  <action>
    Run the following verification commands. **No file edits in this task** — the plan is a verification-only pass per D-12/D-13.

    1. **mypy strict zero errors:**
       ```bash
       uv run mypy src
       ```
       Expected output: ends with `Success: no issues found in N source files` (N is the production file count, currently ~75 after plans 07-02..07-08 add `errors.py` × 2).
       If errors are reported → STOP, surface as gap; this plan is verification-only and cannot fix mypy errors. The mypy strict gate is enforced by CI from P1 (verified in CONTEXT.md D-13), so an error here means a regression slipped past CI — investigate via `git log -p` and either revert or fix in a follow-up plan.

    2. **No `# type: ignore` in src/:**
       ```bash
       grep -rn "# type: ignore" src/ || echo "GREP_RESULT: empty"
       ```
       Expected output: `GREP_RESULT: empty` (or zero matches printed — `grep -rn` returns non-zero exit code on no matches, hence the `|| echo` fallback).

       If any `# type: ignore` is found:
       - Note exact location (`file:line`).
       - Categorise: is it on a critical path (UoW, repositories, consumer handler, reconciler, interactors, schemas) per D-12 first bullet, OR on a framework boundary (FastAPI / FastStream dispatch, dependency overrides in tests) per D-12 second bullet?
       - **Critical path:** STOP — must be removed or justified-and-removed. Surface as gap; this plan does not edit code, but the gap blocks Phase 7 phase-gate (plan 07-12).
       - **Framework boundary:** acceptable IF an inline comment explains why. Document in SUMMARY.md.

    3. **No `# type: ignore` in tests/audit/ (the new package from plan 07-07):**
       Even though tests have a looser mypy override (`disallow_untyped_defs = false` per D-14), the new audit-static tests should be clean.
       ```bash
       grep -rn "# type: ignore" tests/audit/ || echo "GREP_RESULT: empty"
       ```
       Expected: `GREP_RESULT: empty`.

    4. **CI step verification:**
       ```bash
       grep -A 1 "name: Mypy strict" .github/workflows/ci.yml
       ```
       Expected output:
       ```
             - name: Mypy strict
               run: uv run mypy src
       ```
       If different, surface as drift — but per CONTEXT.md D-13 this is already in place from P1.

    5. **pyproject.toml override invariant (D-14):**
       Verify that the `[tool.mypy]` block in `pyproject.toml` still has the `tests.*` override with `disallow_untyped_defs = false` (or equivalent). Phase 7 must NOT remove this override.
       ```bash
       grep -A 2 "module = \[\"tests\." pyproject.toml
       ```
       Expected: at least one match with `disallow_untyped_defs = false` or similar relaxation. If absent, surface as drift — but this should have been in place from P1.

    Record all four command outputs in the plan SUMMARY.
  </action>
  <verify>
    <automated>uv run mypy src</automated>
  </verify>
  <acceptance_criteria>
    - `uv run mypy src` exits 0 with "Success: no issues found in N source files" for N ≥ 70 (current file count + 2 errors.py from plan 07-02)
    - `grep -rn "# type: ignore" src/` returns no matches (exit code non-zero — expected)
    - `grep -rn "# type: ignore" tests/audit/` returns no matches
    - `grep -A 1 "name: Mypy strict" .github/workflows/ci.yml` shows `run: uv run mypy src`
    - `grep -B 1 -A 2 "module = \[\"tests" pyproject.toml` shows the `disallow_untyped_defs = false` override preserved
    - No files modified in this task: `git diff` shows zero file changes
  </acceptance_criteria>
  <done>QA-01 verified end-to-end: mypy strict zero errors, zero # type: ignore in src/, CI step intact, tests override preserved.</done>
</task>

</tasks>

<verification>
- `uv run mypy src` — Success
- `grep -rn "# type: ignore" src/` — empty
- `grep -rn "# type: ignore" tests/audit/` — empty
- `git diff` — zero changes (verification-only plan)
- 07-AUDIT.md row #17 already cites this verification + the CI step
</verification>

<success_criteria>
- mypy strict passes on `src/` with zero errors
- Zero `# type: ignore` in `src/` (RESEARCH.md A5 invariant preserved through Phase 7)
- Zero `# type: ignore` in `tests/audit/` (new package stays clean)
- `tests.*` mypy override preserved in pyproject.toml (D-14)
- No code changes in this plan — pure verification
- 07-11-SUMMARY.md documents all four checks with output
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-11-SUMMARY.md` containing:
- Output of `uv run mypy src` (exit code + last line)
- Output of `grep -rn "# type: ignore" src/` (expected: empty)
- Output of `grep -rn "# type: ignore" tests/audit/` (expected: empty)
- CI step grep result
- pyproject.toml override grep result
- Sign-off: QA-01 verified, no changes applied
- Commit: `docs(07): mypy strict verification — QA-01 verified, no changes` (commit only the SUMMARY)
</output>
