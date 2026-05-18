---
phase: 06-reconciliation-job
plan: 11
type: execute
wave: 6
depends_on: [10]
files_modified:
  - .planning/ROADMAP.md
  - .planning/REQUIREMENTS.md
autonomous: false
requirements: [BM-12, QA-08]
tags: [phase-gate, coverage, doc-sync, roadmap-checkboxes]

must_haves:
  truths:
    - "Full test suite green: `uv run pytest -x` exits 0"
    - "Coverage ≥80% across both packages: `uv run pytest --cov=src --cov-fail-under=80` exits 0"
    - "mypy --strict src/ exits 0; ruff check src/ tests/ exits 0"
    - "ROADMAP.md Phase 6 progress row updated to N/N Complete with completion date"
    - "ROADMAP.md Phase 6 Plans block all checkboxes [x]"
    - "REQUIREMENTS.md BM-12 status flipped from [ ] to [x] and QA-08 status flipped to [x]; traceability table updated"
    - "Phase 6 directory has SUMMARY.md files for all 11 plans (06-01-SUMMARY.md..06-11-SUMMARY.md)"
  artifacts:
    - path: ".planning/ROADMAP.md"
      provides: "All Phase 6 plan checkboxes ticked; Phase row marked Complete with date"
      contains: "11/11"
    - path: ".planning/REQUIREMENTS.md"
      provides: "BM-12 + QA-08 flipped to [x] in body AND traceability table"
      contains: "BM-12.*Complete"
  key_links:
    - from: ".planning/ROADMAP.md Phase 6"
      to: "tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py"
      via: "QA-08 acceptance directly traces to Scenario b passing"
      pattern: "QA-08|test_drop_publish_reconciler_recovers_won"
---

<objective>
Close Phase 6. Confirm the entire phase artefact set is green, coverage gate met, and documentation reflects the actual delivered state.

Three gates this plan validates:

1. **Test gate**: `uv run pytest -x --cov=src --cov-fail-under=80` exits 0. This is the canonical green light.
2. **Static-check gate**: `uv run mypy src/` + `uv run ruff check src/ tests/` both exit 0.
3. **Doc-sync gate**: `BM-12` and `QA-08` are marked complete in REQUIREMENTS.md (body + traceability table); the Phase 6 progress row in ROADMAP.md says `11/11 | Complete | <date>`; all 11 plan checkboxes in the Phase 6 `Plans:` block are `[x]`.

Includes one `checkpoint:human-verify` task at the end to give the developer a moment to skim the artefact set before declaring the phase done.

Purpose: This is the last quality-gate. No production code changes; just verification, doc updates, and a human ack so the developer is in the loop before claiming Core Value defence-in-depth is mechanically proven.

Output: Two doc files updated; pytest+coverage+mypy+ruff all green; human acknowledgement of the QA-08 e2e log.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/phases/06-reconciliation-job/06-VALIDATION.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run full test suite + coverage + static checks; assemble metrics</name>
  <files>(no file modifications — pure verification)</files>
  <read_first>
    - .planning/phases/06-reconciliation-job/06-VALIDATION.md §Manual-Only Verifications (gate list)
  </read_first>
  <action>
    Run, in order, the four gate commands. Capture each output for the SUMMARY.md (TLDR per command):

    1) `uv run pytest -x -q tests/` — must exit 0. Record the "passed" count.
    2) `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80 tests/` — must exit 0. Record the total coverage percentage and any modules below 80%.
    3) `uv run mypy src/` — must exit 0. Record the file count typechecked.
    4) `uv run ruff check src/ tests/` — must exit 0.

    If any command fails:
    - Do NOT mark the phase complete.
    - Open a GAP item (write `.planning/phases/06-reconciliation-job/06-11-GAPS.md` with the failing command + tail of output).
    - Return to whichever plan owns the failing area.

    If all four pass: proceed to Task 2.
  </action>
  <verify>
    <automated>uv run pytest -x --cov=src --cov-fail-under=80 -q tests/ && uv run mypy src/ && uv run ruff check src/ tests/</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -x -q tests/` exits 0
    - `uv run pytest --cov=src --cov-fail-under=80 -q tests/` exits 0 (coverage gate held)
    - `uv run mypy src/` exits 0
    - `uv run ruff check src/ tests/` exits 0
    - No GAPS file was created (or if created, it has been resolved and deleted before this gate)
  </acceptance_criteria>
  <done>All four gate commands exit 0; metrics recorded for Task 2.</done>
</task>

<task type="auto">
  <name>Task 2: Update REQUIREMENTS.md (BM-12 + QA-08 → [x]) and ROADMAP.md (Phase 6 → Complete, all checkboxes ticked)</name>
  <files>.planning/REQUIREMENTS.md, .planning/ROADMAP.md</files>
  <read_first>
    - .planning/REQUIREMENTS.md (full file — locate BM-12 and QA-08 lines + their traceability rows)
    - .planning/ROADMAP.md (Phase 6 progress row at line ~221 + Phase 6 Plans block at lines ~196-208 — both need updating)
  </read_first>
  <action>
    A) `.planning/REQUIREMENTS.md`:
    - Change `- [ ] **BM-12**:` to `- [x] **BM-12**:` (keep the rest of the line, including the Plan 06-01 doc-sync extension, intact).
    - Change `- [ ] **QA-08**:` to `- [x] **QA-08**:`.
    - In the traceability table at the bottom:
      - The row `| BM-12 | Phase 6 | Pending |` → `| BM-12 | Phase 6 | Complete (Plan 06-10) |`
      - The row `| QA-08 | Phase 6 | Pending |` → `| QA-08 | Phase 6 | Complete (Plan 06-10) |`
    - Update the footer line "Last updated: ..." to "Last updated: 2026-05-18 after Phase 6 completion (Plan 06-11 — BM-12, QA-08 complete)".

    B) `.planning/ROADMAP.md`:
    - In the Phases header list near the top: change `- [ ] **Phase 6: Reconciliation job**` → `- [x] **Phase 6: Reconciliation job**`.
    - In the `### Phase 6: Reconciliation job` body, in the `Plans:` block, tick every box: replace every `- [ ] 06-` with `- [x] 06-` (this is the eleven entries 06-01..06-11). Use Edit tool repeatedly, OR a single sed-like replacement bounded to the Phase 6 section.
    - Update the `**Plans:** 11 plans across 7 waves (0..6)` line to `**Plans:** 11/11 plans executed (Phase 6 complete 2026-05-18)`.
    - In the bottom Progress table: change the row `| 6. Reconciliation job | 0/? | Not started | - |` to `| 6. Reconciliation job | 11/11 | Complete | 2026-05-18 |`.

    Do NOT mark Phase 7 as complete; that is the next phase.

    C) Sanity-grep after edits:
    - `grep -c "\[x\] \*\*BM-12\*\*" .planning/REQUIREMENTS.md` == 1
    - `grep -c "\[x\] \*\*QA-08\*\*" .planning/REQUIREMENTS.md` == 1
    - `grep -cE "^- \[ \] 06-[0-9]{2}-" .planning/ROADMAP.md` == 0 (all 11 Phase 6 plans ticked)
    - `grep -c "11/11 plans executed (Phase 6 complete" .planning/ROADMAP.md` == 1
    - `grep -c "6\. Reconciliation job .* Complete" .planning/ROADMAP.md` == 1
  </action>
  <verify>
    <automated>grep -c "\[x\] \*\*BM-12\*\*" .planning/REQUIREMENTS.md && grep -c "\[x\] \*\*QA-08\*\*" .planning/REQUIREMENTS.md && [ "$(grep -cE '^- \[ \] 06-[0-9]{2}-' .planning/ROADMAP.md)" = "0" ]</automated>
  </verify>
  <acceptance_criteria>
    - All grep counts from the action's "Sanity-grep" sub-section match
    - `git diff --stat .planning/REQUIREMENTS.md .planning/ROADMAP.md` shows only those two files changed
    - No phase OTHER than Phase 6 has its checkboxes ticked by this plan (sanity: `grep -c "11/11 plans executed (Phase 6 complete" .planning/ROADMAP.md` == 1; no spurious "Phase 7 complete" string)
  </acceptance_criteria>
  <done>BM-12 and QA-08 marked complete in body + traceability; Phase 6 progress row says 11/11 Complete; all 11 plan boxes ticked.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Human ack of QA-08 acceptance log</name>
  <files>(no files — checkpoint observes Task 1 + Task 2 results)</files>
  <action>Pause for human verification. Task 1 produced the green pytest/coverage/mypy/ruff outputs; Task 2 updated REQUIREMENTS.md and ROADMAP.md. This task asks the human to skim the 11 SUMMARY.md files and the QA-08 e2e PASSED line before declaring the phase complete. No automated work; the operator follows the steps in <how-to-verify> and types "approved" or describes the failing item in <resume-signal>.</action>
  <what-built>
    Phase 6 production:
    - `BetStatus.CANCELLED` + Alembic 0003 (autocommit_block ALTER TYPE)
    - `BetRepository.get_pending_event_ids()`
    - `cancel_bets_for_event` interactor + `CancelResult` DTO
    - `src/bet_maker/jobs/reconciler.py` (loop + tick + per-event decision tree)
    - Two new `BetMakerSettings` fields
    - Lifespan create_task / cancel-first sequencing
    - `/health` 4th check
    - Two new `Annotated` Dep aliases in `facades/deps.py`

    Test coverage:
    - 11 stub test files turned into ~48 real test methods.
    - 5 integration tests (SC#4 race + SC#1 respx).
    - 3 e2e tests (SC#5 a/b/c — QA-08).

    Doc sync:
    - REQUIREMENTS.md BM-05/BM-12 mention CANCELLED; BM-12/QA-08 ticked.
    - ROADMAP.md Phase 6 Goal/SC#1/SC#5/Plans/Progress updated.
  </what-built>
  <how-to-verify>
    1. Read the per-plan SUMMARY.md files at `.planning/phases/06-reconciliation-job/06-NN-SUMMARY.md` for N=01..10 and verify each says "Done" / lists expected tests passing.
    2. Run `uv run pytest -x --cov=src --cov-fail-under=80 -q tests/` and confirm exit 0 + coverage ≥ 80% on screen.
    3. Run `uv run pytest -x -q tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py -v` and visually confirm `test_drop_publish_reconciler_recovers_won PASSED` — THIS is the QA-08 acceptance signal.
    4. Open `.planning/ROADMAP.md` and confirm Phase 6 row is `11/11 | Complete | 2026-05-18`.
    5. (Optional) Manual smoke: `docker compose down -v && docker compose up -d`, wait for healthy, `curl :8001/health` and confirm body contains `"reconciler": "ok"`.
  </how-to-verify>
  <resume-signal>Type "approved" if all five checks pass, or describe the failing item.</resume-signal>
  <verify>Human operator confirms each of the 5 steps in <how-to-verify> passed; types "approved" in chat to resume execute-plan. No automated verification — this is a human gate.</verify>
  <done>Operator has typed "approved" (or equivalent) after confirming all 5 checks; the phase is officially closed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| developer review → doc state | This plan is the say-do parity gate before phase closure |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-11-01 | Tampering (premature green) | phase-gate checkboxes | mitigate | Task 1 BLOCKS the doc edits behind passing tests + coverage; Task 3 inserts a human ack of the QA-08 e2e specifically |
| T-06-11-02 | Repudiation (incorrect completion claim) | traceability table | mitigate | "Complete (Plan 06-10)" attribution lets future audits trace the exact closing plan |
</threat_model>

<verification>
- `uv run pytest -x --cov=src --cov-fail-under=80 -q tests/` exits 0.
- `uv run mypy src/ && uv run ruff check src/ tests/` exits 0.
- `grep -cE "^- \[ \] 06-" .planning/ROADMAP.md` == 0.
- Human approver signs "approved" on Task 3.
</verification>

<success_criteria>
- All tests green; coverage ≥80%; mypy + ruff clean.
- REQUIREMENTS.md BM-12 + QA-08 ticked; traceability table updated.
- ROADMAP.md Phase 6 row says 11/11 Complete with date; all 11 plan checkboxes ticked.
- Developer has acknowledged the QA-08 e2e PASSED line in pytest output.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-11-SUMMARY.md` containing:
- Final pytest summary (passed count).
- Final coverage percentage.
- Path to all 11 plan SUMMARY.md files (one bullet each).
- Confirmation of REQUIREMENTS.md + ROADMAP.md edits (grep counts).
- Quote of the human's approval signal from Task 3.
</output>
