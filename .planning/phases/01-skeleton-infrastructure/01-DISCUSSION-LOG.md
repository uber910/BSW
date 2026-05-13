# Phase 1: Skeleton + Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 1-skeleton-infrastructure
**Areas discussed:** Layout (pyproject), Dockerfile + docker-compose, CI + pre-commit, Tests scaffold + README, Shared code, mypy в pre-commit, Порты, CI триггеры

---

## Layout: pyproject organisation

| Option | Description | Selected |
|--------|-------------|----------|
| Single root pyproject | bsw distribution, packages line_provider + bet_maker под src/, один uv.lock. CLAUDE.md preference | ✓ |
| uv workspace с двумя под-pyproject | Members = src/line_provider + src/bet_maker (STACK.md). Отдельные distributions | |
| Single root + bsw_common shared | Один pyproject, три пакета: line_provider, bet_maker, bsw_common | |

**User's choice:** Single root pyproject (рекомендую).
**Notes:** Решает конфликт STACK.md (workspace) vs CLAUDE.md (single pyproject) в пользу читаемости для ревьюера. Минус — отказ от dep-изоляции; в test-task контексте не критично.

---

## Dockerfile strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Один Dockerfile + ARG SERVICE | Multi-stage builder с uv sync → slim runtime, non-root, ARG выбирает entrypoint | ✓ |
| Два Dockerfile (по одному на сервис) | docker/line-provider.Dockerfile + docker/bet-maker.Dockerfile, больше явности, дублирование builder | |
| Один Dockerfile без ARG, entrypoint в compose | Universal image, compose определяет command, одна сборка | |

**User's choice:** Один Dockerfile + ARG SERVICE (рекомендую).
**Notes:** DRY, одна точка правды для базы. ARG прокидывается в `ENV` runtime stage, чтобы exec-form CMD `["python","-m","${SERVICE}"]` работал.

---

## CI workflow design

| Option | Description | Selected |
|--------|-------------|----------|
| Один job lint+typecheck+test | ubuntu-latest, Python 3.10.20 pin, uv cache по uv.lock | ✓ |
| Split jobs (lint / typecheck / test) | Параллельно, faster fail-fast, но больше setup-ячеек | |
| Split + service containers уже в P1 | PG/RMQ в GH Actions для integration job | |

**User's choice:** Один job lint+typecheck+test (рекомендую в P1).
**Notes:** P1 без бизнес-логики — split-jobs дают marginal benefit. PG/RMQ services добавим в P3/P5 когда появится integration coverage.

---

## Tests scaffold + README depth

| Option | Description | Selected |
|--------|-------------|----------|
| Smoke /health + README stub | tests/{service}/test_health.py через httpx ASGITransport. README: бейджи + curl + TODO-разделы | ✓ |
| Только import-smoke + minimal README | pytest на импорт пакетов, README 1 экран | |
| Smoke /health + скелет README с разделами Architecture/Development/Reliability + TODO | Больше видимость, риск drift до P7 | |

**User's choice:** Smoke /health + README stub (рекомендую).
**Notes:** Smoke реально проверяет, что `build_app()` работает и /health возвращает корректный JSON. README — заглушка с CI-бейджем и quick-start, P7 расширит.

---

## Shared code organisation

| Option | Description | Selected |
|--------|-------------|----------|
| src/_shared/ | Приватный внутри-репо пакет, оба сервиса импортируют from _shared.logging import configure | |
| Дублировать копии | Идентичные файлы infrastructure/logging.py в каждом пакете. Изоляция, drift риск | |
| bsw_common как отдельный dist | Третий пакет в src/, объявлен в packages= | |

**User's choice:** `src/config/` (пользовательский ответ — third path).
**Notes:** Пользователь предложил название `config` вместо `_shared`/`bsw_common`. Закодировано в CONTEXT.md D-02 как internal-only пакет `src/config/` с `logging.py`, `settings_base.py`, `time.py`. Импорт `from config.logging import configure_structlog`. Не отдельный distribution — просто папка под `[tool.hatch.build.targets.wheel] packages`.

---

## mypy в pre-commit?

| Option | Description | Selected |
|--------|-------------|----------|
| Только в CI | Pre-commit: ruff + housekeeping, mypy только CI — быстрый коммит | |
| mypy в pre-commit + CI | mypy --strict на каждом коммите. Ранний catch, +5-15s | ✓ |

**User's choice:** mypy в pre-commit + CI.
**Notes:** Type drift ловится локально до push. Configured как local hook (`entry: uv run mypy --strict src`, `pass_filenames: false`), чтобы запускать на всём проекте за раз — это быстрее, чем мини-инвокации.

---

## Ports

| Option | Description | Selected |
|--------|-------------|----------|
| 8000 line-provider, 8001 bet-maker | Совпадает с curl-примером в ROADMAP success criteria 2 | ✓ |
| 8080 line-provider, 8081 bet-maker | 8000 часто занят dev-сервисами; но ломает ROADMAP curl-пример | |

**User's choice:** 8000 / 8001 (реком.).
**Notes:** Если на хосте занят 8000 — это переопределяется в `docker-compose.override.yml` (gitignored), production-mapping не трогаем.

---

## CI triggers

| Option | Description | Selected |
|--------|-------------|----------|
| push на main + PR в main | Стандарт, экономит GH Actions minutes | |
| push на любые ветки + PR | CI на каждый push, полный feedback на feature-ветке | ✓ |

**User's choice:** push на любые ветки + PR.
**Notes:** Для test-task важна видимость зелёного бейджа на каждом коммите feature-ветки.

---

## Claude's Discretion

- Точная структура `src/line_provider/` и `src/bet_maker/` — следуем ARCHITECTURE.md «paste-ready tree» 1:1, planner может коррективы вносить.
- Версия `astral-sh/setup-uv` action — последняя стабильная.
- `interval/timeout/retries` для compose-healthcheck'ов — planner подбирает совместимые с `start_period: 10s`.
- Точный синтаксис uv 0.11 для dev-deps (`tool.uv.dev-dependencies` vs `[dependency-groups] dev`) — выбрать актуальный.

---

## Deferred Ideas

- PG/RabbitMQ services в GH Actions — в P3/P5.
- pytest-cov coverage gate — в P7 (QA-09 ≥80%).
- `alembic upgrade head` на старте bet-maker — в P3 (миграции появятся вместе с моделями).
- pyupgrade hook — покрыт ruff UP rule set, отдельный hook не нужен.
- OpenAPI tags/summaries/examples — в P7 (DOC-01..04).
- Полные разделы README (Architecture/Development/Reliability) — в P7.
- Idempotency-Key, OpenTelemetry, Prometheus, Grafana — v2 per REQUIREMENTS.md.
