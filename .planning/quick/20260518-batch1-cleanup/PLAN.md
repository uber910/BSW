---
id: 20260518-batch1-cleanup
status: in-progress
created: 2026-05-18
slug: batch1-cleanup
description: Низкорисковые правки по фидбеку — батч №1 (6 пунктов)
---

# Quick Task: Batch №1 — low-risk cleanup

Источник: пользовательский фидбек после закрытия milestone v1.
Разделение фидбека на два батча согласовано: batch №1 (этот) — мелочи и точечные правки; batch №2 — архитектурный рефакторинг (Repository выпил, shared-код, новый UoW pattern) — будет отдельной фазой через `/gsd-plan-phase`.

## Объём (6 пунктов)

| # | Пункт | Файлы (ориентир) |
|---|---|---|
| 1 | `BetStatus.CANCELLED = "cancelled"` → `"CANCELLED"` + alembic-миграция `ALTER TYPE bet_status ADD VALUE 'CANCELLED'` | `src/bet_maker/schemas/bets.py`, `src/bet_maker/models/bet.py`, новая миграция |
| 2 | Стрип GSD-комментариев в `src/**` (см. правило ниже) | `src/**/*.py` |
| 3 | Удалить `utc_now()` обёртку, заменить на `datetime.now(UTC)`; тесты — на `freezegun` | `src/config/time.py`, 6 call-sites, 4 тест-файла |
| 4 | DI-алиасы `Dep` → `Dependency` | `src/bet_maker/facades/deps.py`, `src/line_provider/facades/deps.py`, все usage |
| 5 | Упрощение Dockerfile | `Dockerfile`, может затронуть `docker-compose.yml` |
| 6 | `alembic/` → `src/bet_maker/alembic/`, `alembic.ini` → `src/bet_maker/alembic.ini` | `alembic.ini`, `alembic/env.py`, `Dockerfile`, `docker-compose.yml` |

## Контракт каждого пункта

- Отдельный atomic commit с префиксом `refactor(quick)` или `fix(quick)`.
- После каждого: `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest -q` — всё зелёное.
- `--cov-fail-under=85` сохраняется.

## Правило стрипа GSD-комментариев (item 2)

**Удалить:** упоминания `D-NN`, `(Phase N)`, `Plan NN-NN`, `Anti-Pattern N`, `(R5)`, `(P5)`, имена планинг-файлов (`CONTEXT.md`, `REVIEW.md`, `VERIFICATION.md`, `ARCHITECTURE.md`), маркер `TZ:`.
**Сохранить:** содержательную часть — *почему* так, *что* это даёт. Если после стрипа остаётся осмысленный текст — оставляем; если только GSD-bookkeeping без сути — удаляем целиком.

## Порядок исполнения

```
1 → 2 → 3 → 4 → 5 → 6
```
Линейно, потому что:
- item 4 (rename `Dep` → `Dependency`) ломает usages, проще делать после стрипа комментов (item 2), чтобы не правил merge в shrinkнутых строках;
- item 6 (alembic переезд) трогает Dockerfile, делается после item 5.

## Открытое решение, зафиксированное в plan

- **`freezegun` как dev-dep.** При удалении `utc_now()` тесты, которые сейчас `monkeypatch.setattr("…utc_now", lambda: …)`, переводятся на `freeze_time`. Альтернатива — патчить `datetime.datetime.now` напрямую — хуже по эргономике. freezegun ≈ industry standard, легковесный.

## Out of scope

- Repository → selectors+interactors (batch №2)
- shared/config monorepo cleanup (batch №2)
- UoW по образцу Metrikus (batch №2)
- `entrypoints/` → `api/` flat (batch №2)
