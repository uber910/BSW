---
plan: 07-10-readme-final
status: complete
date: 2026-05-18
---

# Plan 07-10 — README Final Pass

## Purpose

Final README rewrite per CONTEXT.md D-01..D-05: 7 sections, ASCII diagram,
5-step reviewer walkthrough, 6-point Reliability + CANCELLED-extension
paragraph, 7/7 Project status complete.

## Sections (7)

1. Header + 2 badges (CI + Shields.io coverage) + description
2. Quick start (preserved verbatim + walkthrough pointer + OpenAPI/AsyncAPI URLs added)
3. Reviewer walkthrough (NEW — 5-step curl sequence per D-04)
4. Architecture (NEW — ASCII 6-stroke diagram + layers + RMQ topology + reconciler + ARCHITECTURE.md link)
5. Reliability (NEW — 6-point list + CANCELLED extension + PITFALLS.md + 07-AUDIT.md links)
6. Development (preserved + coverage gate command added)
7. Next-step extensions (NEW — 6 deferred items: TTL cache, Prometheus, AsyncAPI snapshot, codecov, API hardening, REL hardening)
8. Project status (7/7 complete)

## Self-Checks

- `wc -l README.md` → 217 ≥ 150
- `grep -c "^## " README.md` → 7
- `grep -c "coverage-85%25-brightgreen" README.md` → 1 (badge URL)
- `grep -cE "^\| [1-7] \| .* \| complete \|" README.md` → 7 (all 7 phases complete)
- `grep -c "CANCELLED" README.md` → 3 (architecture mention + extension paragraph + Reliability §5)
- `grep -c "feedback_verify_against_tz" README.md` → 1 (memory reference in CANCELLED paragraph)
- `grep -c "PITFALLS.md" README.md` → 2 (header + Reliability link)
- `grep -c "07-AUDIT.md" README.md` → 1 (Reliability link)
- No emojis (visual review — CLAUDE.md rule honored)

## Decisions Honored

- D-01: Russian primary, no English translation
- D-02: 7-section order (Quick start → walkthrough → Architecture → Reliability → Development → Next-step → Project status)
- D-03: 6-stroke ASCII diagram (LP↔reviewer, LP→RMQ, RMQ→BM, RMQ→DLX, BM→PG, BM→LP reconciler)
- D-04: 5-step curl walkthrough (sleep+observe = step 6, total 6 lines but conceptually 5 ops)
- D-05: 6-point Reliability list with source-file references + dedicated CANCELLED paragraph
- D-16: Shields.io static badge (no codecov)
- CLAUDE.md no-emoji rule honored
- `OWNER/REPO` placeholder preserved per RESEARCH.md Pitfall 9

## Commits

- `9afa454` docs(07-10): README final pass — Architecture + Reliability + walkthrough (D-01..D-05)
