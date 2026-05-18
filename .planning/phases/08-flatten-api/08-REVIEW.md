---
phase: 08-flatten-api
depth: standard
files_reviewed: 28
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
date: 2026-05-18
---

# Phase 8 Code Review — flatten-api

## Summary

Проверено 28 файлов рефакторинга Phase 8: перенос `entrypoints/` → `api/` + плоский layout `lifespan.py`/`middleware.py` в корне пакета. Импорты полностью обновлены — ни одного стейла `<svc>.entrypoints` в `src/` и `tests/`. Аудит-гард `test_no_entrypoints_dir` активен и невакуумен: оба каталога физически отсутствуют. Инварианты FastAPI/FastStream сохранены: `AckPolicy.MANUAL`, `durable=True`, `Channel(prefetch_count=10)`, `router.broker.publish` без второго `RabbitBroker`. Обнаружено одно предупреждение с реальным риском: README.md содержит 4 стейл-ссылки на `src/bet_maker/entrypoints/messaging.py`, которые могут ввести в заблуждение ревьюеров тестового задания. Второе предупреждение касается относительного пути `Path("src/bet_maker/api/messaging.py")` в `test_messaging.py` — он работает при запуске pytest из корня репозитория, но может сломаться при изменении CWD. Одна информационная находка: устаревший слоевой дескриптор в README.md (`entrypoints/`).

## Findings

### CR-08-001 — README.md содержит 4 стейл-ссылки на `src/bet_maker/entrypoints/messaging.py`
**Severity:** Warning
**File:** `README.md:120,148,149,151`
**Category:** convention

Три абзаца раздела «Reliability» и один пункт архитектурного описания слоёв ссылаются на `src/bet_maker/entrypoints/messaging.py`, который после Phase 8 не существует. Для тестового задания, где первое впечатление ревьюера формируется через README, это серьёзный косметический дефект: ссылка ведёт в несуществующий файл, что противоречит только что выполненному рефакторингу. Исправление: заменить три вхождения `src/bet_maker/entrypoints/messaging.py` на `src/bet_maker/api/messaging.py`, строку 120 обновить с `entrypoints/` на `api/` + добавить, что `lifespan.py`/`middleware.py` теперь в корне пакета.

---

### CR-08-002 — `test_messaging.py` использует относительный путь без привязки к `__file__`
**Severity:** Warning
**File:** `tests/bet_maker/test_messaging.py:219`
**Category:** test

```python
src = Path("src/bet_maker/api/messaging.py").read_text()
```

Путь относительный (без `Path(__file__).resolve().parents[N]`), тогда как все остальные аналогичные статические читалки в `tests/audit/test_static.py` используют `REPO_ROOT = Path(__file__).resolve().parents[2]`. pytest запускается из корня репозитория, поэтому в текущей конфигурации тест проходит. Но если кто-то запустит pytest из другой директории (например `cd tests && pytest`), тест упадёт с `FileNotFoundError` вместо осмысленного сообщения об ассерции. Исправление: заменить на `Path(__file__).resolve().parents[2] / "src" / "bet_maker" / "api" / "messaging.py"`.

---

### CR-08-003 — Docstring `src/bet_maker/api/messaging.py:1` сохраняет слово "entrypoint" в первой строке
**Severity:** Info
**File:** `src/bet_maker/api/messaging.py:1`
**Category:** convention

Заголовок модуля: `"""bet-maker AMQP consumer entrypoint."""`. Слово «entrypoint» здесь описывает роль модуля (точка входа для AMQP), а не путь в файловой системе, поэтому технически не является стейлом. Аналогично `src/line_provider/api/messaging.py:1`: `"""line-provider AMQP entrypoint (publisher-only)."""`. При этом оба файла переехали именно из `entrypoints/`. Для консистентности с Phase 8 (полное устранение концепции «entrypoints») можно заменить на «bet-maker AMQP consumer — FastStream RabbitRouter (consumer side)» и «line-provider AMQP publisher — FastStream RabbitRouter (publisher side)». Это не баг и не нарушение конвенций, но снимает потенциальную путаницу при следующем обзоре.

---

## No Further Issues

Все 28 файлов в части импортов, типизации, FastAPI/FastStream-паттернов и конвенций проекта проходят проверку. Ключевые инварианты:

- `from <svc>.entrypoints...` — 0 вхождений в `src/` и `tests/`
- `find src -type d -name entrypoints` — 0 результатов (проверено)
- `test_no_entrypoints_dir` — активен, невакуумен, оба assert срабатывают на отсутствующие директории
- `AckPolicy.MANUAL` присутствует ровно на одном `@router.subscriber` в `bet_maker/api/messaging.py`
- `durable=True` у `RabbitQueue` и `RabbitExchange` в `bet_maker/api/messaging.py`
- `Channel(prefetch_count=10)` — объявлен в `RabbitRouter`
- `router.broker.publish(...)` в `RabbitEventBus` — использует разделяемый брокер, не создаёт второй `RabbitBroker`
- late-import `from bet_maker.api.messaging import router` в `deps.py:90` — корректный паттерн для разрыва циклических импортов
- cross-service импорты в `test_e2e_rabbitmq.py`: строка 113 (`line_provider.api.messaging`) и строка 131 (`bet_maker.api.messaging`) — оба обновлены на новые пути
- `tests/bet_maker/conftest.py:149` (`line_provider.api.messaging`) и `conftest.py:76` (`bet_maker.api.messaging`) — обновлены
- `tests/line_provider/conftest.py:22`, `test_lifespan.py` — все используют `line_provider.api.messaging`
- `src/bet_maker/api/__init__.py` и `src/line_provider/api/__init__.py` — пустые, корректный минимализм согласно D-02
- Секретов, `print()`-отладки, эмодзи, лишних комментариев в коде — не обнаружено
- mypy strict и ruff zero-warnings: подтверждены CI-прогоном (356 тестов, coverage 94.58%)
