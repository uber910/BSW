# Phase 9: UoW redesign + Repository removal - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 09-uow-repository-removal
**Areas discussed:** Abstract тип (ABC vs Protocol), Metrikus shape (literal vs structural), Selector signatures, Audit fate

---

## Abstract тип — ABC или Protocol

| Option | Description | Selected |
|--------|-------------|----------|
| ABC + @abstractmethod (Metrikus-style) | class AbstractUnitOfWork(ABC) с @abstractmethod на __aenter__/__aexit__/session. Наследование явное; mypy strict ловит пропущенные методы при инстанциировании PostgresUnitOfWork. Прямое зеркало Metrikus-эталона. | ✓ |
| Protocol (structural typing) | class UnitOfWork(Protocol), runtime_checkable опционально. Согласуется с EventLookup. FakeUoW в тестах не наследуется. Но отходит от Metrikus-эталона, на который явно ссылается roadmap. | |
| ABC + рядом Protocol-alias | AbstractUnitOfWork(ABC) + параллельно UnitOfWorkProto(Protocol). Два имени одного контракта — over-engineering. | |

**User's choice:** ABC + @abstractmethod (Metrikus-style)
**Notes:** Лежит в основе D-01/D-02. Roadmap явно ссылается на Metrikus → ABC ближе к источнику; mypy strict выигрывает на explicit inheritance.

---

## Зеркалить Metrikus буквально или только структурно

| Option | Description | Selected |
|--------|-------------|----------|
| Структурное зеркало | Abstract+Postgres pair + session property. Commit в clean __aexit__ автоматически. Anti-Pattern 1 + test_uow_has_no_public_commit_or_rollback сохраняются. Интеракторы пишут в uow.session напрямую (SQLAlchemy 2.0 API). | ✓ |
| Буквальное зеркало | Public async commit()/rollback() + execute(entity)/delete(entity) + query/fetch/fetch_one. Требует удалить test_uow_has_no_public_commit_or_rollback и пересмотреть Anti-Pattern 1. | |
| Гибрид | Структурное + явный commit/rollback для сложных сценариев. execute/delete/query игнорируем. | |

**User's choice:** Структурное зеркало
**Notes:** Лежит в основе D-03/D-04. Сохраняем Anti-Pattern 1 и существующий аудит. Интерактор работает через `uow.session.add/execute/flush` напрямую — это уже идиоматичный SQLAlchemy 2.0 API.

---

## Сигнатура selectors после удаления repositories

| Option | Description | Selected |
|--------|-------------|----------|
| Все selectors берут AsyncSession | list_bets/get_bet_by_id уже принимают session. get_pending_locked(session, event_id) и get_pending_event_ids(session) переезжают с той же сигнатурой. Интерактор передаёт uow.session явно. Единый контракт. | ✓ |
| Lock-selectors берут uow, read-only — session | get_pending_locked(uow, event_id) подчёркивает lock-семантику; read-only — прежние. Неровный контракт. | |
| Все selectors берут uow | Максимальная униформность; read-only роуты придётся вращать в UoW. Излишняя церемониальность для pure read. | |

**User's choice:** Все selectors берут AsyncSession
**Notes:** Лежит в основе D-05/D-06/D-07. Selector = thin SQL wrapper над session, без знаний про UoW (соответствует формулировке roadmap «thin SQL wrappers, no commit/flush»). Lock-selectors получают `uow.session` от вызывающего интерактора внутри `async with uow:`.

---

## Судьба аудита test_repositories_use_for_update_skip_locked

| Option | Description | Selected |
|--------|-------------|----------|
| Переименовать + перенацелить | test_pending_locked_selector_uses_for_update_skip_locked → src/bet_maker/selectors/get_pending_locked.py. R3 инвариант остаётся под static-сетью на новом seam. Быстрый, детерминированный, без PG. | ✓ |
| Удалить аудит | Полагаемся на test_reconciler_consumer_race + test_settle concurrent. Меньше кода, но теряем скоростную static-канарейку. | |
| Перенацелить + расширить | Добавить «no repositories/ dir» (assert not exists). Дублирует success criteria #3 (no `class BetRepository`). | |

**User's choice:** Переименовать + перенацелить
**Notes:** Лежит в основе D-08/D-09. Static-аудит остаётся, просто на новом seam. Дополнительный «no repositories dir» аудит не добавляем — это уже покрывается DOD #3 success criteria phase 9.

---

## Claude's Discretion

- Файловое размещение (`src/bet_maker/uow/{abstract.py, postgres.py}` vs одиночный `src/bet_maker/facades/uow.py`) — планнеру решить по объёму concrete-кода.
- Имя абстрактного класса (`AbstractUnitOfWork` vs `UnitOfWork`) — default Metrikus-имя.
- DI-провайдер остаётся factory-style (не generator); current paттерн (interactor сам делает `async with uow:`) — инвариант v1.0.
- Гранулярность планов в plan-phase: рекомендован порядок abstract+concrete → интеракторы по одному → selectors → удаление repositories + переименование audit.
- Удаление/переписывание `tests/bet_maker/test_repositories.py` и `tests/bet_maker/repositories/test_get_pending_event_ids.py` — default переписать под `tests/bet_maker/selectors/...`.

## Deferred Ideas

- SingleStore / Blob UoW реализации (Metrikus имеет, нам не нужно — v2).
- `uow.session.execute()` обёртки (`uow.execute`, `uow.fetch`) — SQLAlchemy 2.0 API уже идиоматично, рассмотреть только если кодовая база разрастётся.
- Shared `AbstractUnitOfWork` в shared-пакете — phase 10 (REFACTOR-04); сейчас не возникает дублирования (LP UoW не имеет).
- Generator-style DI provider (`async with uow: yield uow`) — отложено, текущий factory-style v1.0 сохраняется.
- `runtime_checkable` на Protocol — Protocol-ветка отброшена.
