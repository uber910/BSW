---
phase: 07-polish-documentation
plan: 06
type: execute
wave: 1
depends_on: [01]
files_modified:
  - .github/workflows/ci.yml
autonomous: true
requirements: [QA-09]
must_haves:
  truths:
    - "CI Pytest step invokes uv run pytest with --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85"
    - "Coverage gate at 85% enforced in CI"
    - "pyproject.toml [tool.coverage.run] source = [\"src/line_provider\", \"src/bet_maker\"] already in place (verified — no edit needed)"
    - "No new dependencies — pytest-cov already in dev-deps (verified — version 7.1.0)"
  artifacts:
    - path: ".github/workflows/ci.yml"
      provides: "GitHub Actions CI workflow with coverage gate"
      contains: "--cov-fail-under=85"
  key_links:
    - from: ".github/workflows/ci.yml::steps::Pytest"
      to: "pyproject.toml::tool.coverage.run.source"
      via: "Bare --cov reads source list from pyproject"
      pattern: "uv run pytest .* --cov "
---

<objective>
Extend the CI Pytest step to enforce ≥85% coverage per CONTEXT.md D-15. One-line replacement in `.github/workflows/ci.yml` — no other CI changes; no codecov / coveralls integration (D-16); no `pyproject.toml` edit (coverage source + fail_under already configured from P3).

Per RESEARCH.md Pitfall 2: use **bare `--cov` (no argument)** so pytest-cov honours `[tool.coverage.run] source = ["src/line_provider", "src/bet_maker"]` from `pyproject.toml`. Passing `--cov=<path>` would override that and break multi-package coverage.

`--cov-fail-under=85` on CLI is belt-and-braces: it duplicates `[tool.coverage.report] fail_under = 85` in pyproject. Explicit CLI flag makes the gate visible in green/red CI output and guards against pyproject drift.

Output: 1-line edit in `.github/workflows/ci.yml`. CI runs locally via `uv run pytest -q --cov --cov-fail-under=85` for verification.
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
<!-- Current .github/workflows/ci.yml — Pytest step (verbatim) -->
```yaml
      - name: Pytest
        run: uv run pytest -q
```

<!-- pyproject.toml — relevant blocks (DO NOT EDIT, just reference) -->
```toml
[tool.coverage.run]
source = ["src/line_provider", "src/bet_maker"]
branch = true

[tool.coverage.report]
fail_under = 85
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

<!-- pytest-cov 7.1.0 already in dev-deps — verified per RESEARCH.md -->
</interfaces>
</context>

<threat_model>
N/A — CI workflow edit, no production code change. Coverage gate enforces quality, no security surface.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Extend CI Pytest step with coverage gate</name>
  <files>.github/workflows/ci.yml</files>
  <read_first>
    - .github/workflows/ci.yml (full file — locate the `name: Pytest` step)
    - .planning/phases/07-polish-documentation/07-PATTERNS.md (CI workflow extension pattern)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-15, D-17)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (Pitfall 2 — bare --cov, NOT --cov=path)
  </read_first>
  <action>
    Edit `.github/workflows/ci.yml` using the Edit tool. Replace the existing Pytest step exactly:

    BEFORE:
    ```yaml
          - name: Pytest
            run: uv run pytest -q
    ```

    AFTER:
    ```yaml
          - name: Pytest
            run: uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85
    ```

    **Critical (Pitfall 2 from RESEARCH.md):** Use bare `--cov` with no argument. Do NOT use `--cov=src/`, `--cov=src/line_provider`, or any other path argument — that would override `[tool.coverage.run] source = [...]` in pyproject.toml and silently exclude one of the two packages from the report.

    **Do NOT edit `pyproject.toml`** — the `[tool.coverage.run] source` list and `[tool.coverage.report] fail_under = 85` are already in place from P3 (verified). Per CONTEXT.md D-15: explicit CLI flag `--cov-fail-under=85` is a belt-and-braces measure that duplicates pyproject but makes the gate visible in CI output.

    **Verify the edit locally before committing** (this is the equivalent of running the CI step):
    ```bash
    uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85
    ```
    This must:
    1. Run the full test suite (~295 tests + 12+ new tests from plans 07-02..07-05).
    2. Report coverage by-file for both `src/line_provider/` and `src/bet_maker/`.
    3. Write `coverage.xml` to repo root.
    4. Exit 0 if total coverage ≥ 85%; exit 1 otherwise.

    If coverage is below 85%, this plan FAILS (gap closure handled by plan 07-12 phase-gate). Document any drop in plan SUMMARY.

    Per CONTEXT.md D-23 (no scope creep): if running `--cov` reveals coverage <85%, do NOT add new tests in this plan — surface the gap to plan 07-12 phase-gate which can either accept the drop or trigger gap-closure planning.

    Run `cat .github/workflows/ci.yml | grep -A 1 "name: Pytest"` and verify the run line contains `--cov-fail-under=85`.

    No mypy/ruff impact (yaml-only edit).
  </action>
  <verify>
    <automated>uv run pytest -q --cov --cov-report=term-missing --cov-fail-under=85</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "name: Pytest" .github/workflows/ci.yml` returns 1 (step still present, single instance)
    - `grep -c -- "--cov-fail-under=85" .github/workflows/ci.yml` returns 1
    - `grep -c -- "--cov-report=xml" .github/workflows/ci.yml` returns 1
    - `grep -c -- "--cov-report=term-missing" .github/workflows/ci.yml` returns 1
    - `grep -E "uv run pytest -q --cov[^=]" .github/workflows/ci.yml` returns 1 line (bare `--cov`, not `--cov=path` — character after `--cov` is space or end-of-token)
    - `grep -F -- "--cov=" .github/workflows/ci.yml` returns 0 (no path argument to --cov; only --cov-report and --cov-fail-under may match this substring)
    - `uv run pytest -q --cov --cov-fail-under=85` exits 0 locally (coverage ≥ 85%)
    - File `coverage.xml` written to repo root after local run (artefact for optional future codecov)
    - No edits to `pyproject.toml`: `git diff pyproject.toml` returns empty
  </acceptance_criteria>
  <done>CI Pytest step enforces ≥85% coverage; local pytest run with same flags exits 0; pyproject.toml untouched.</done>
</task>

</tasks>

<verification>
- `uv run pytest -q --cov --cov-report=term-missing --cov-fail-under=85` — exits 0; total coverage report ≥ 85% across both packages
- `cat coverage.xml | head -3` — valid XML (covers integration with future codecov if added)
- `grep -F "fail_under = 85" pyproject.toml` — already there (no edit)
- `grep -F "source = [\"src/line_provider\", \"src/bet_maker\"]" pyproject.toml` — already there (no edit)
- `git diff .github/workflows/ci.yml` — one line changed (Pytest step `run:`)
- `git diff pyproject.toml` — empty (no edit)
</verification>

<success_criteria>
- `.github/workflows/ci.yml` Pytest step uses bare `--cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85`
- Local invocation with the same flags exits 0 (full suite green AND coverage ≥ 85%)
- No `pyproject.toml` changes (configuration already in place from P3)
- No new dependencies installed (pytest-cov already in dev-deps)
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-06-SUMMARY.md` recording:
- Before/after of the Pytest step yaml
- Local `pytest --cov` output (final coverage percentage, by-file breakdown summary)
- coverage.xml presence (yes/no)
- Confirmation pyproject.toml NOT edited
</output>
