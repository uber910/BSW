# Phase 7: Polish + Documentation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 07-polish-documentation
**Mode:** `--auto` (single-pass, recommended-option selection without AskUserQuestion)
**Areas discussed:** README structure, OpenAPI polish, AsyncAPI publication, mypy strict cleanup, coverage gate, "Looks Done But Isn't" audit, sync-task verification

---

## README structure (DOC-01..04)

| Option | Description | Selected |
|--------|-------------|----------|
| Russian primary, single README | Соответствует существующей `.planning/`-документации, CLAUDE.md и ТЗ; технические термины без перевода | ✓ |
| Russian primary + English summary в начале | Двойной maintenance, нет ценности для русскоязычного reviewer'а | |
| English-only | Конфликтует с ТЗ и существующими артефактами | |

**Selected:** Russian primary, single README.
**Notes:** ASCII-диаграмма inline (D-03), 8-секционная структура (D-02), 5-шаговый Reviewer walkthrough (D-04), Reliability с CANCELLED-extension абзацем (D-05).

---

## OpenAPI metadata polish

| Option | Description | Selected |
|--------|-------------|----------|
| Inline `summary` + `responses` + `Body(examples=...)` на каждом route | Минимум новых модулей; FastAPI v0.115+ syntax | ✓ |
| Централизованный `openapi.json` override через `app.openapi_schema` | Дублирует source-of-truth, расходится с docstrings | |
| Без правок (полагаемся на docstrings) | Существующие docstrings есть, но `responses={...}` для error-веток отсутствует — теряется visibility 422/503/404 | |

**Selected:** Inline metadata enrichment.
**Notes:** Новая Pydantic-схема `ErrorDetail` на каждом сервисе (D-09); `Body(..., openapi_examples=...)` v2 syntax (D-08).

---

## AsyncAPI publication

| Option | Description | Selected |
|--------|-------------|----------|
| FastStream default `/asyncapi` endpoint | Без ручной схемы; auto-генерация из декораторов | ✓ |
| Manual asyncapi.json snapshot в `docs/` | Дублирует source-of-truth, рассинхронизируется | |
| Без AsyncAPI | Конфликтует с ROADMAP P7 SC#5 | |

**Selected:** Default `/asyncapi` endpoint на обоих сервисах.
**Notes:** Snapshot не коммитим (D-11); reviewer может `curl :8001/asyncapi -o asyncapi.json` per Next-step extensions.

---

## mypy strict cleanup (QA-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Финальный pass + audit `# type: ignore` на критических путях | Минимальные правки, CI gate уже зелёный с P1 | ✓ |
| Расширить strict на тесты | Шумные правки fixture/hooks с малым value | |
| Поднять mypy до `--strict-equality` + `--warn-unreachable` | Out of scope; current strict уже включает их | |

**Selected:** Минимальный final pass.
**Notes:** `# type: ignore` audit на UoW/repositories/handler/reconciler — должно быть пусто; на границах FastAPI/FastStream dispatch допустимо с inline-комментарием (D-12).

---

## Coverage gate (QA-09)

| Option | Description | Selected |
|--------|-------------|----------|
| `--cov --cov-fail-under=85` в CI + Shields.io static badge | Простая настройка, без внешних сервисов; уже совпадает с pyproject `fail_under=85` | ✓ |
| Codecov / Coveralls интеграция | Требует регистрации, токенов, push в третью сторону — overkill | |
| Только pyproject `fail_under` без CI флага | CI не валит build при падении coverage — теряется gate | |

**Selected:** CI флаг + статический badge.
**Notes:** 85% планка (D-17) — выше ROADMAP-минимума 80, совпадает с current pyproject.

---

## "Looks Done But Isn't" audit (ROADMAP P7 SC#6)

| Option | Description | Selected |
|--------|-------------|----------|
| `07-AUDIT.md` таблица + `tests/audit/test_static.py` для grep/AST-проверяемых items | Структурированный артефакт + автоматизация где возможно | ✓ |
| Только Markdown-таблица без автоматизации | Audit не зафиксирован в CI; рискует рассинхронизироваться | |
| Только pytest-тесты без Markdown | Reviewer'у нужен compact обзор; markdown даёт его | |

**Selected:** AUDIT.md + tests/audit/test_static.py.
**Notes:** 18 items, из них 8 автоматизированы grep/AST (D-19), 4 покрыты existing P3/P5/P6 тестами (D-21/D-22), 4 manual-only (`docker compose down` exit-code, `docker volume ls`, RMQ Management UI screenshot, Decimal exact roundtrip — последний покрыт P3) — D-20.

---

## Sync-task verification (Plan 07-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Sync-task проверка с возможным no-op исходом | Соответствует pattern'у P2..P6; memory `feedback_verify_against_tz` | ✓ |
| Пропустить sync-task в Phase 7 | Нарушает паттерн; рискует пропустить drift между ТЗ и итоговой документацией | |
| Полностью переписать REQUIREMENTS/ROADMAP | Out of scope; артефакты уже актуальны после P6 D-25 | |

**Selected:** Sync-task с no-op-возможным исходом.
**Notes:** Sync включает сверку CANCELLED-статуса (P6 D-25) против схем + ТЗ (память `feedback_verify_against_tz`); ожидаемый исход — `sync verified, no changes` (D-23).

---

## Claude's Discretion

- Точный URL Shields.io badge (статический vs query-параметризованный) — planner.
- Расположение `ErrorDetail` (`schemas/errors.py` отдельный модуль vs встроить) — planner; рекомендован отдельный модуль.
- Стиль static-audit-тестов (`ast` vs regex) — planner; recommended regex для скорости.
- Количество запросов в Reviewer walkthrough (5 vs 6) — planner; recommended 5.
- Уровень детализации ASCII-диаграммы (минимум vs детальная) — planner; recommended средняя (6-stroke).
- Опциональный `contact={...}` в FastAPI app — planner может опустить.

## Deferred Ideas

- TTL cache `GET /events` (P4 D-01) — README §Next-step extensions.
- Codecov / Coveralls интеграция.
- AsyncAPI snapshot в репо.
- English README перевод.
- Prometheus / OpenTelemetry / Grafana (v2 OBS-01..03).
- `Idempotency-Key` / API versioning / Rate limiting / RFC7807 (v2 API-01..04).
- Quorum queues / Outbox / Saga (v2 REL-01..03).
- Multi-region / Kubernetes / Helm.
- mypy strict на тестах.
- EventState parity test (nice-to-have, P6 deferred).
- README в отдельной branch / MkDocs site.
