---
phase: 07-polish-documentation
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
  - README.md
autonomous: true
requirements: [DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09]
must_haves:
  truths:
    - "REQUIREMENTS.md BM-05 explicitly mentions CANCELLED status as engineering extension of ТЗ"
    - "ROADMAP.md Phase 7 success criteria #1..#6 match the artefacts the rest of Phase 7 will create"
    - "README.md skeleton acknowledges Architecture / Reliability sections will be filled in (or already mentions CANCELLED extension under Reliability TODO)"
    - "No undeclared drift between ./Тестовое задание Middle Python developer.pdf and REQUIREMENTS/ROADMAP for Phase 7 scope"
  artifacts:
    - path: ".planning/phases/07-polish-documentation/07-01-SUMMARY.md"
      provides: "Sync verification result (no-op expected, drift fixes recorded if any)"
  key_links:
    - from: ".planning/phases/07-polish-documentation/07-01-SUMMARY.md"
      to: ".planning/REQUIREMENTS.md / .planning/ROADMAP.md / README.md"
      via: "Drift verification — explicit no-op statement OR minimal-edit fix log"
      pattern: "sync verified|drift fixed"
---

<objective>
Phase 7 starts with the canonical sync-task pattern (P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10 / P6 06-01 — D-23). Sweep REQUIREMENTS.md / ROADMAP.md / README.md against the ТЗ PDF and against the locked-decision artefacts (CONTEXT.md D-01..D-23). Expected outcome — no-op (Phase 6 D-25 already locked the BM-05 CANCELLED-extension wording). If any drift is found, apply a minimal-edit fix in this plan; otherwise commit `sync verified, no changes`.

Purpose: ensure downstream Phase 7 plans (OpenAPI polish, audit static tests, AUDIT.md, README final) build on a known-good baseline. Catch any drift that survived Phase 1-6.

Output: SUMMARY.md recording either (a) "drift verified absent" or (b) the exact minimal edits applied with before/after snippets.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/07-polish-documentation/07-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@./Тестовое задание Middle Python developer.pdf
@README.md
</context>

<threat_model>
N/A — documentation phase; no new attack surface. Sync-task only reads + makes minimal text edits to markdown files.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Verify REQUIREMENTS.md against ТЗ PDF and CONTEXT.md D-05</name>
  <read_first>
    - ./Тестовое задание Middle Python developer.pdf (especially p.2 "Bet может иметь один из трёх статусов" + p.3 API diagram)
    - .planning/REQUIREMENTS.md (full file — focus on BM-05, DOC-01..04, QA-01, QA-09)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md (D-25 CANCELLED extension wording)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-05, D-23)
  </read_first>
  <action>
    Read ТЗ PDF and cross-reference against REQUIREMENTS.md. Verify the following invariants:

    1. **BM-05 wording** must already contain text such as "Статусы ставки: `PENDING | WON | LOST | CANCELLED` (Phase 6 / D-03). `CANCELLED` — recovery-статус: ставка помечается reconciler'ом при 404 от line-provider ... — инженерная трактовка ТЗ (memory `feedback_verify_against_tz`)". This was added in P6 plan 06-01.
       - If present verbatim → no edit, proceed.
       - If wording differs (drift) → write a minimal-edit fix making the CANCELLED-extension call-out explicit and self-contained on the BM-05 line. Do not rephrase unrelated parts of BM-05.

    2. **Traceability table** at bottom of REQUIREMENTS.md — verify Phase 7 rows: DOC-01 / DOC-02 / DOC-03 / DOC-04 / QA-01 / QA-09 all map to "Phase 7" with Status `Pending`. (BM-12 / QA-08 must be `Complete` from P6.) If any cell is wrong, apply minimal-edit fix.

    3. **Phase 7 distribution line** (currently "Phase 7 (Polish + Documentation): 5 requirements"). Count current Phase 7 IDs: DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09 = 6 IDs. If the count says 5, fix to 6. If the count says 6 already, no edit.

    If any edits applied — keep them minimal, do not touch unrelated sections. Use the Edit tool, not Write.
  </action>
  <verify>
    <automated>grep -c "CANCELLED" .planning/REQUIREMENTS.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "CANCELLED" .planning/REQUIREMENTS.md` returns ≥ 1 (BM-05 mentions CANCELLED)
    - `grep "feedback_verify_against_tz" .planning/REQUIREMENTS.md` returns at least one line (BM-05 references the memory)
    - `grep -E "^\| DOC-0[1-4] \| Phase 7 \| Pending" .planning/REQUIREMENTS.md` returns 4 lines
    - `grep -E "^\| QA-0(1|9) \| Phase 7 \| Pending" .planning/REQUIREMENTS.md` returns 2 lines
    - `grep -E "Phase 7 \(Polish \+ Documentation\): 6 requirements" .planning/REQUIREMENTS.md` returns 1 line
  </acceptance_criteria>
  <done>BM-05 CANCELLED-extension wording present; Phase 7 traceability rows + per-phase count line both reflect the 6-ID set (DOC-01..04, QA-01, QA-09).</done>
</task>

<task type="auto">
  <name>Task 2: Verify ROADMAP.md Phase 7 SC#1..#6 + Plans line</name>
  <read_first>
    - .planning/ROADMAP.md (Phase 7 section)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-02, D-18..D-22)
    - .planning/REQUIREMENTS.md (Phase 7 requirement IDs — verify ROADMAP `Requirements:` line matches)
  </read_first>
  <action>
    Verify ROADMAP.md Phase 7 block:

    1. **`Requirements:` line** for Phase 7 must list exactly: `DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09` (no extras, no missing). If list differs, apply minimal-edit fix.

    2. **Success Criteria #1..#6** — verify each SC matches what Phase 7 actually delivers (per CONTEXT.md). In particular:
       - SC#1: copy-pasteable reviewer walkthrough — matches D-04.
       - SC#2: dedicated sections Architecture / Development / Reliability — matches D-02.
       - SC#3: mypy strict zero errors — matches D-12.
       - SC#4: pytest-cov ≥80% threshold (existing pyproject has 85 — ROADMAP minimum 80 is fine; D-17). No edit needed.
       - SC#5: OpenAPI tags/summaries/response_model/examples + FastStream AsyncAPI `/asyncapi` — matches D-06..D-11.
       - SC#6: every PITFALLS.md "Looks Done But Isn't" 18-item checklist verified — matches D-18..D-22.

    3. **`Plans:`** line for Phase 7 — currently "**Plans**: TBD". After this plan-set is laid out, the orchestrator will update this; do NOT pre-write the plan-list here (the planner orchestrator handles that). Leave `TBD` or update minimally to reflect total plan count if the orchestrator instructs in a later step.

    Drift expected: none. If present, minimal-edit fix.
  </action>
  <verify>
    <automated>grep -E "DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09" .planning/ROADMAP.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -E "^\*\*Requirements\*\*: DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09$" .planning/ROADMAP.md` returns 1 line (Phase 7 Requirements list intact)
    - Phase 7 SC table has 6 numbered success criteria (`grep -cE "^\s*[1-6]\." .planning/ROADMAP.md` ≥ 6 in the Phase 7 region — visual cross-check)
    - No edits applied unless drift found; if applied, recorded in 07-01-SUMMARY.md under "Drift fixes"
  </acceptance_criteria>
  <done>ROADMAP.md Phase 7 Requirements list matches Phase 7 ID set; SC#1..#6 cover the artefacts Phase 7 plans 02-12 will deliver.</done>
</task>

<task type="auto">
  <name>Task 3: Verify README.md skeleton anchors CANCELLED extension placeholder</name>
  <read_first>
    - README.md (full file — focus on `## Reliability` / `## Architecture` placeholder sections)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-05 — CANCELLED extension narrative)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md (D-25)
  </read_first>
  <action>
    Read README.md as-is. Current state:
    - `## Architecture` section is a TODO placeholder pointing at `.planning/research/ARCHITECTURE.md`.
    - `## Reliability` section is a TODO placeholder mentioning durable queue / manual ack / DLQ / reconciler / FOR UPDATE SKIP LOCKED.
    - Project status table marks all phases as `pending` / `in progress`.

    Per D-23, Phase 7 sync-task only ensures README is consistent with REQUIREMENTS.md + ROADMAP.md before plans 07-02..07-12 rewrite it. Specifically: the Reliability TODO must already reference (or have room to reference) the CANCELLED extension. The current TODO line is "TODO: гарантии durable queue, manual ack, DLQ, reconciliation job, `FOR UPDATE SKIP LOCKED`. Будет наполнено в Phase 7." — this is acceptable as-is; final wording lands in plan 07-10.

    **No edit to README.md in this task.** Simply confirm placeholder sections exist (so plan 07-10 can replace them) and the badge URL placeholder `OWNER/REPO` is unchanged (P5/P6 did not commit a real org/repo).

    If any of the following are missing, surface as drift and apply minimal-edit fix:
    - `## Architecture` heading exists (line ~79).
    - `## Reliability` heading exists (line ~83).
    - `## Project status` heading + 7-row table exists (lines ~87-98).

    If all three present, write "README skeleton verified intact" to the plan SUMMARY.
  </action>
  <verify>
    <automated>grep -cE "^## (Architecture|Reliability|Project status|Quick start|Development)$" README.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -cE "^## (Architecture|Reliability|Project status|Quick start|Development)$" README.md` returns 5
    - `grep -cE "^\| [1-7] \| " README.md` returns 7 (Project status rows for 7 phases)
    - README.md NOT modified unless drift found; if modified, diff recorded in 07-01-SUMMARY.md
  </acceptance_criteria>
  <done>README.md skeleton placeholders (Architecture / Reliability / Project status) intact and ready for plan 07-10 final pass.</done>
</task>

</tasks>

<verification>
- Run `grep -c "CANCELLED" .planning/REQUIREMENTS.md` — must be ≥ 1.
- Run `grep -E "DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09" .planning/ROADMAP.md` — must return Phase 7 Requirements line.
- Run `grep -cE "^## (Architecture|Reliability|Project status|Quick start|Development)$" README.md` — must return 5.
- Run `uv run pytest -q` — full suite still green (sync-task only edits markdown).
- Run `uv run mypy src` — still zero errors.
</verification>

<success_criteria>
- REQUIREMENTS.md BM-05 explicitly documents CANCELLED extension with reference to memory `feedback_verify_against_tz`.
- ROADMAP.md Phase 7 Requirements line matches the 6-ID set.
- README.md skeleton sections (Architecture / Reliability / Project status) intact.
- 07-01-SUMMARY.md records either "sync verified, no changes" OR explicit minimal-edit diffs.
- Test suite green; mypy strict zero errors (no production code changed).
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-01-SUMMARY.md` containing:
- Files inspected
- Drift findings (expected: none)
- Edits applied (expected: none — but if any, before/after snippet for each)
- Commit hash (one commit either way: `docs(07): sync verified, no changes` OR `docs(07): minimal drift fix in REQUIREMENTS.md`)
</output>
