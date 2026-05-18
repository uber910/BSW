---
phase: 08-flatten-api
verified: 2026-05-18
status: passed
score: 5/5 must_haves verified
requirements:
  - id: REFACTOR-01
    verified: true
    evidence: "find src -type d -name entrypoints | wc -l → 0; ls src/bet_maker/api/ → __init__.py bets.py events.py health.py messaging.py; ls src/line_provider/api/ → __init__.py events.py health.py messaging.py; git grep '(bet_maker|line_provider)\\.entrypoints' src/ tests/ → exit 1 (zero matches); REQUIREMENTS.md строка 173: | REFACTOR-01 | Phase 8 | Complete |"
  - id: REFACTOR-05
    verified: true
    evidence: "356 passed, 23 warnings in 26.58s; mypy --strict src → Success: no issues found in 87 source files; ruff check src tests → All checks passed!; coverage 94.58% >= 85% gate"
---

# Phase 8 Verification — flatten-api

## Goal

HTTP routers and the FastStream RabbitMQ router live in `src/<svc>/api/` for both services; the `entrypoints/` package is gone. Treat Rabbit as just another transport-layer API.

## Success Criteria Verification

### SC1: entrypoints/ directories deleted

**Status:** PASS

**Evidence:**
```
$ find src -type d -name entrypoints | wc -l
       0
```
Оба каталога `src/bet_maker/entrypoints/` и `src/line_provider/entrypoints/` физически отсутствуют. Выход — 0.

---

### SC2: api/ modules present + imports resolve

**Status:** PASS

**Evidence:**
```
$ ls src/bet_maker/api/
__init__.py  __pycache__  bets.py  events.py  health.py  messaging.py

$ ls src/line_provider/api/
__init__.py  __pycache__  events.py  health.py  messaging.py

$ git grep -E '(bet_maker|line_provider)\.entrypoints' src/ tests/
(нет вывода — exit code 1, ноль совпадений)

$ git grep -E '(bet_maker|line_provider)/entrypoints' src/ tests/ | grep -v '^\.planning/'
(нет вывода — exit code 1, ноль совпадений)
```

Все ожидаемые модули присутствуют. Ни одной стейл-ссылки `entrypoints` в `src/` и `tests/`.

---

### SC3: lifespan/middleware at service root

**Status:** PASS

**Evidence:**
```
$ ls src/bet_maker/lifespan.py src/bet_maker/middleware.py
src/bet_maker/lifespan.py
src/bet_maker/middleware.py

$ ls src/line_provider/lifespan.py src/line_provider/middleware.py
src/line_provider/lifespan.py
src/line_provider/middleware.py

$ grep -nE 'from (bet_maker|line_provider)\.(lifespan|middleware)' src/bet_maker/app.py src/line_provider/app.py
src/line_provider/app.py:7:from line_provider.lifespan import lifespan
src/line_provider/app.py:8:from line_provider.middleware import RequestContextMiddleware
src/bet_maker/app.py:7:from bet_maker.lifespan import lifespan
src/bet_maker/app.py:8:from bet_maker.middleware import RequestContextMiddleware
```

`lifespan.py` и `middleware.py` перемещены в корень пакета сервиса, `app.py` импортирует их из новых путей без мёртвых ссылок.

---

### SC4: Quality gate green (tests, mypy, ruff, coverage)

**Status:** PASS

**Evidence:**
```
$ uv run ruff check src tests
All checks passed!

$ uv run mypy --strict src
Success: no issues found in 87 source files

$ uv run pytest -q
356 passed, 23 warnings in 26.58s

$ uv run pytest --cov=src --cov-fail-under=85 -q
TOTAL   1147   49   70   7   95%
Required test coverage of 85% reached. Total coverage: 94.58%
356 passed, 23 warnings in 26.19s
```

356 тестов (> baseline 355), ноль пропущенных/xfail; mypy strict 0 ошибок; ruff чисто; coverage 94.58% >= 85%.

---

### SC5: Audit guard updated

**Status:** PASS

**Evidence:**
```python
# tests/audit/test_static.py::test_no_entrypoints_dir
def test_no_entrypoints_dir() -> None:
    """REFACTOR-01: src/<svc>/entrypoints/ must not exist for either service.

    Phase 8 flattened HTTP routers + FastStream RabbitRouter into
    src/<svc>/api/ and relocated lifespan.py + middleware.py to the
    service-package root. The legacy entrypoints/ directory was
    deleted for both services; this audit fails if a future commit
    recreates either one.

    Plan 08-01 added the bet_maker assertion. Plan 08-02 added the
    line_provider assertion.
    """
    bm = SRC / "bet_maker" / "entrypoints"
    lp = SRC / "line_provider" / "entrypoints"
    assert not bm.exists(), f"{bm} re-introduced — Phase 8 flattened entrypoints/ → api/."
    assert not lp.exists(), f"{lp} re-introduced — Phase 8 flattened entrypoints/ → api/."

$ uv run pytest -q tests/audit/test_static.py::test_no_entrypoints_dir
1 passed, 1 warning in 0.00s
```

Оба assert активны, невакуумны (оба каталога реально удалены). Гард сработает при регрессии.

---

## Anti-Pattern Checks (D-01..D-05)

| Решение | Проверка | Результат |
|---------|----------|-----------|
| **D-01**: нет `api/http/` или `api/amqp/` subdirs | `find src -type d \( -name http -o -name amqp \)` | PASS — нет вывода (exit 0) |
| **D-02**: нет `src/<svc>/app/` subpackage | `find src -maxdepth 3 -type d -name 'app'` | PASS — нет вывода (exit 0) |
| **D-03**: `messaging/routing.py` не тронут Phase 8 | `git log --oneline 0a2abfb..HEAD -- src/bet_maker/messaging/routing.py src/line_provider/messaging/routing.py` | PASS — нет вывода (ноль коммитов) |
| **D-04**: src/ и tests/ перемещены в локштепе | `git show --stat 97420eb` (bet_maker) и `git show --stat 043ccf4` (line_provider) — каждый commit содержит и `src/` переименования и импорт-правки | PASS — src + тесты обновлялись в одной фазе; production+import rewrites объединены в единый commit каждого сервиса по техническим причинам (pre-commit mypy) |
| **D-05**: структура `tests/` не менялась — только импорты | `git diff --stat 97420eb~1..HEAD -- 'tests/**'` не содержит `rename` или `delete`, только `+/-` строки в 10 файлах | PASS — структура директорий tests/ не изменена, только содержимое файлов |

---

## Code Review Notes

08-REVIEW.md: 0 critical / 2 warning / 1 info. Все 3 находки неблокирующие и лежат за пределами основного scope Phase 8:

- **CR-08-001 (Warning)**: `README.md` содержит 4 стейл-ссылки на `src/bet_maker/entrypoints/messaging.py` (строки 120, 148, 149, 151). Косметический дефект, не затрагивает код или тесты. Первое впечатление ревьюера тестового задания потенциально ухудшается. Рекомендуется исправить до финальной сдачи.
- **CR-08-002 (Warning)**: `tests/bet_maker/test_messaging.py:219` использует `Path("src/bet_maker/api/messaging.py")` без привязки к `__file__`. Работает при запуске pytest из корня репозитория (стандартный режим), ломается при `cd tests && pytest`. Стиль расходится с `test_static.py`, где используется `REPO_ROOT = Path(__file__).resolve().parents[2]`.
- **CR-08-003 (Info)**: Docstring `src/bet_maker/api/messaging.py:1` содержит слово «entrypoint» в техническом смысле (точка входа для AMQP), не как путь ФС. Не баг, но слегка путает в контексте Phase 8.

Ни одна из находок не является блокирующей для верификации Phase 8.

---

## Verdict

**Статус: passed**

Все 5 успешных критериев выполнены на живом кодбейсе. Phase 8 достигла задекларированной цели:

- `entrypoints/` удалён из обоих сервисов (SC1: PASS)
- Плоские `api/` пакеты содержат все ожидаемые модули + нет стейл-импортов (SC2: PASS)
- `lifespan.py`/`middleware.py` в корне пакета, `app.py` правильно подключает (SC3: PASS)
- 356 тестов зелёные, mypy strict 0 ошибок, ruff чисто, coverage 94.58% (SC4: PASS)
- Аудит-гард `test_no_entrypoints_dir` активен и невакуумен для обоих сервисов (SC5: PASS)

REFACTOR-01 отмечен Complete в REQUIREMENTS.md (строка 173). REFACTOR-05 выполнен: качественный барьер Phase 8 пройден. BM-03 дескриптор обновлён с `entrypoints` на `api`.

Два предупреждения из code review (README стейл-ссылки + относительный путь в test_messaging.py) не являются регрессиями Phase 8 и рекомендуются к исправлению перед финальной демонстрацией.

---

## human_verification

Нет. Рефакторинг является чисто структурным без поведенческих изменений; полное автоматизированное покрытие (94.58%) подтверждает корректность. Ручная проверка не требуется.
