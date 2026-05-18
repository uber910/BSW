---
id: 20260518-batch1-cleanup
status: complete
created: 2026-05-18
completed: 2026-05-18
slug: batch1-cleanup
description: Низкорисковые правки по фидбеку — batch №1 (6 пунктов)
---

# SUMMARY: Batch №1 — low-risk cleanup

Все 6 пунктов закрыты атомарными коммитами. Архитектурные пункты фидбека (Repository выпил, shared-код, новый UoW pattern, `entrypoints/` → `api/`) отложены в batch №2 — будет отдельной фазой через `/gsd-plan-phase`.

## Commits

| Item | Commit | Diff |
|---|---|---|
| 1 | `a8e468f` `fix(quick): BetStatus.CANCELLED uppercase + PG ENUM rename` | 5 files, +28 −81 |
| 2 | `e03c788` `refactor(quick): strip GSD planning markers from src comments` | 35 files, +290 −302 |
| 3 | `adbc560` `refactor(quick): remove utc_now() wrapper` | 12 files, +67 −92 |
| 4 | `1625698` `refactor(quick): rename DI Annotated aliases *Dep → *Dependency` | 6 files, +34 −32 |
| 5 | `b639a08` `refactor(quick): drop dead bits from Dockerfile` | 2 files, +1 −11 |
| 6 | `ef2bbf9` `refactor(quick): move alembic to src/bet_maker/` | 14 files, +20 −20 |

## Quality gates

- **ruff check src tests** — clean
- **mypy --strict src** — 89 файлов, 0 ошибок
- **pytest** — 355 passed, coverage gate ≥85% сохраняется
- **docker build .** — успешно собирается; smoke `python -c 'import line_provider, bet_maker, config'` зелёный
- **alembic -c src/bet_maker/alembic.ini history** — корректно резолвит 4 ревизии

## Решения, зафиксированные при исполнении

- **BetStatus.CANCELLED**: не редактировал миграцию 0003 (она «уже отгружена»), добавил отдельную 0004 с `ALTER TYPE bet_status RENAME VALUE 'cancelled' TO 'CANCELLED'`. Downgrade обратим. Удалил `tests/bet_maker/migrations/test_0003_cancelled.py` как устаревший — финальная форма ENUM теперь проверяется в `test_alembic.py`.
- **utc_now**: ушёл целиком; в тестах перешли на `freezegun.freeze_time`. Добавлен dev-dep `freezegun>=1.5,<2`.
- **GSD-комменты**: 35 src-файлов прошлись через очистку (агент). Сохранили WHY-прозу (транзакции, локи, FastStream-caveats, asyncpg-нюансы); удалили все ссылки на `D-NN`, фазы, планы, риски, Anti-Pattern, requirement IDs, файлы планирования. Тесты не трогали — отдельный проход при необходимости.
- **Dockerfile**: убран мёртвый `ARG SERVICE` (нигде не читался), curl из builder-стадии, suicide-CMD. `command:` в compose остаётся exec-form — статический аудит перенесён туда (`tests/audit/test_static.py::test_compose_command_exec_form`).
- **alembic**: переехал в `src/bet_maker/alembic/` + `src/bet_maker/alembic.ini`. Использовал `%(here)s` interpolation в alembic.ini, чтобы конфиг работал из любой cwd. Dockerfile упростился — отдельные COPY больше не нужны, всё едет внутри `src/`.

## Open / handed off to batch №2

- `entrypoints/` → `api/` (включая FastStream consumer)
- Repository выпил (заменить на selectors для чтения и interactors для записи)
- shared-код в monorepo (DB engine, structlog config, lifespan helpers — кандидаты на общий пакет рядом с `src/config`)
- UnitOfWork по образцу `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/` — передавать как dependency
