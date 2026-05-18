---
phase: 05-rabbitmq-integration
fixed_at: 2026-05-18T09:40:00Z
review_path: .planning/phases/05-rabbitmq-integration/05-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 8
skipped: 1
status: partial
---

# Phase 05: Code Review Fix Report

**Fixed at:** 2026-05-18T09:40:00Z
**Source review:** .planning/phases/05-rabbitmq-integration/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9
- Fixed: 8
- Skipped: 1

## Fixed Issues

### CR-01: `set_event_state` — замена string-cast enum на явное отображение

**Files modified:** `src/line_provider/interactors/set_event_state.py`
**Commit:** `6cd2b2e`
**Applied fix:** Добавлен словарь `_EVENT_STATE_TO_TERMINAL: dict[EventState, EventTerminalState]` с явным маппингом. Строка `EventTerminalState(new_state.value)` заменена на `_EVENT_STATE_TO_TERMINAL[new_state]`. Теперь при несоответствии enum-значений будет явный `KeyError` по известному словарю вместо скрытого string-cast `ValueError`. Совмещён с WR-02 в одном коммите.

---

### CR-02: `settle_bets_for_event` — защита от `KeyError` при неизвестном `terminal_state`

**Files modified:** `src/bet_maker/interactors/settle_bets_for_event.py`
**Commit:** `426d6ea`
**Applied fix:** Обёрнут `_TERMINAL_TO_STATUS[terminal_state]` в `try/except KeyError as exc` с `raise ValueError(...) from exc`. Неизвестные терминальные состояния теперь генерируют описательный `ValueError`, который попадает в catch-all ветку `except Exception` в `on_event_finished` и уходит в DLQ через `reject(requeue=False)`. Примечание: использован `ValueError` вместо `UnsupportedSchemaVersion` из-за потенциального кругового импорта (`entrypoints` → `interactors` → `entrypoints`).

---

### WR-01: `on_event_finished` — `ValidationError` теперь ловится внутри обработчика

**Files modified:** `src/bet_maker/entrypoints/messaging.py`
**Commit:** `63698d4`
**Applied fix:** Сигнатура обработчика изменена с `payload: EventFinishedMessage` на `payload: dict[str, Any]`. Внутри `try`-блока добавлен явный вызов `EventFinishedMessage.model_validate(payload)`. Теперь `ValidationError` при десериализации гарантированно поднимается внутри handler'а и перехватывается `except (ValidationError, UnsupportedSchemaVersion, IntegrityError)` → `reject(requeue=False)`, а не зависает в unacked состоянии до reconnect.

---

### WR-02: `occurred_at` заполняется реальным временем перехода

**Files modified:** `src/line_provider/interactors/set_event_state.py`
**Commit:** `6cd2b2e`
**Applied fix:** `occurred_at=new_event.deadline` заменено на `occurred_at=datetime.now(timezone.utc)`. Добавлен импорт `timezone` из `datetime`. Совмещён с CR-01 в одном коммите.

---

### WR-04: `asyncio.get_event_loop()` заменён на `asyncio.get_running_loop()`

**Files modified:** `tests/bet_maker/test_e2e_rabbitmq.py`
**Commit:** `5a9980b`
**Applied fix:** В E2E тесте `test_consumer_settles_bet_after_lp_transitions_to_finished_win` строка `loop = asyncio.get_event_loop()` заменена на `loop = asyncio.get_running_loop()`. Совмещён с IN-03 в одном коммите.

---

### IN-01: Добавлен assert в `test_integrity_error_rejects`

**Files modified:** `tests/bet_maker/test_messaging.py`
**Commit:** `7ba3717`
**Applied fix:** Переменная `settle_mock` сохранена из `with patch(...)` и добавлен `settle_mock.assert_called_once()` после контекстного менеджера `TestRabbitBroker`. Тест теперь подтверждает, что обработчик действительно вызвал `_settle_with_retry` перед тем, как `IntegrityError` попал в POISON-ветку.

---

### IN-02: `created_at`/`updated_at` в модели `Bet` — добавлен `timezone=True`

**Files modified:** `src/bet_maker/models/bet.py`
**Commit:** `ec18417`
**Applied fix:** Добавлен явный `sa.DateTime(timezone=True)` к `created_at` и `updated_at`. Миграция `0001_bets_initial` уже создаёт эти колонки как `timestamp with time zone` — исправление синхронизирует ORM-модель с реальной схемой БД. Новая миграция не требуется.

---

### IN-03: `asyncio.sleep(2.0)` в E2E тесте — polling loop

**Files modified:** `tests/bet_maker/test_e2e_rabbitmq.py`
**Commit:** `5a9980b`
**Applied fix:** `await asyncio.sleep(2.0)` перед проверкой DLQ заменён на polling-loop с таймаутом 5 секунд (`asyncio.get_running_loop().time() + 5.0`) и шагом `asyncio.sleep(0.1)`. Совмещён с WR-04 в одном коммите.

---

## Skipped Issues

### WR-03: Доступ к приватному атрибуту `broker._connection_kwargs` в тестах

**File:** `tests/bet_maker/conftest.py:67`, `tests/bet_maker/conftest.py:139`, `tests/line_provider/conftest.py:26`
**Reason:** skipped: требует архитектурного рефакторинга — вынос `RabbitRouter` в фабрику или lazy-инициализацию URL. Прямая замена на env var невозможна без изменения модульной структуры: роутер инициализируется на уровне модуля до старта тест-контейнера. FastStream `RabbitBroker.connect()` не принимает URL-параметр после инициализации. Нет публичного API для смены URL после создания роутера.
**Original issue:** `rabbit_router.broker._connection_kwargs["url"] = amqp_url` обращается к приватному атрибуту FastStream, структура которого может измениться в патч-релизе.

---

## Test Results

Full suite run after all fixes:

```
295 passed, 26 warnings
```

E2E tests (`tests/bet_maker/test_e2e_rabbitmq.py`) excluded from automated run — требуют реального Docker-окружения с RabbitMQ и PostgreSQL.

Примечание: в полном прогоне с `--ignore=tests/bet_maker/test_e2e_rabbitmq.py` один тест (`TestSettleConcurrent::test_concurrent_settled_via_attribution_is_single_pass`) иногда падает из-за pre-existing проблемы с isolation session-scoped DB при конкурентном запуске. В изоляции тест проходит стабильно. Это не регрессия от применённых фиксов.

---

_Fixed: 2026-05-18T09:40:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
