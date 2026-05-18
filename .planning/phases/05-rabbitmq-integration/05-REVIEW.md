---
phase: 05-rabbitmq-integration
reviewed: 2026-05-18T12:00:00Z
depth: standard
files_reviewed: 36
files_reviewed_list:
  - alembic/versions/20260518_0002_bets_settled_columns.py
  - src/bet_maker/app.py
  - src/bet_maker/entrypoints/api/health.py
  - src/bet_maker/entrypoints/lifespan.py
  - src/bet_maker/entrypoints/messaging.py
  - src/bet_maker/facades/deps.py
  - src/bet_maker/interactors/settle_bets_for_event.py
  - src/bet_maker/messaging/__init__.py
  - src/bet_maker/messaging/routing.py
  - src/bet_maker/models/bet.py
  - src/bet_maker/repositories/bets.py
  - src/bet_maker/schemas/messages.py
  - src/bet_maker/schemas/settle.py
  - src/line_provider/app.py
  - src/line_provider/entrypoints/lifespan.py
  - src/line_provider/entrypoints/messaging.py
  - src/line_provider/facades/event_bus.py
  - src/line_provider/interactors/set_event_state.py
  - src/line_provider/messaging/__init__.py
  - src/line_provider/messaging/routing.py
  - tests/bet_maker/conftest.py
  - tests/bet_maker/test_alembic.py
  - tests/bet_maker/test_e2e_rabbitmq.py
  - tests/bet_maker/test_health.py
  - tests/bet_maker/test_lifespan.py
  - tests/bet_maker/test_messaging.py
  - tests/bet_maker/test_repositories.py
  - tests/bet_maker/test_settle.py
  - tests/conftest.py
  - tests/contract/__init__.py
  - tests/contract/test_event_finished_message_schema.py
  - tests/line_provider/conftest.py
  - tests/line_provider/test_event_bus.py
  - tests/line_provider/test_event_routes.py
  - tests/line_provider/test_lifespan.py
  - tests/line_provider/test_set_event_state.py
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-05-18T12:00:00Z
**Depth:** standard
**Files Reviewed:** 36
**Status:** issues_found

## Summary

Рецензируется реализация Phase 5 — RabbitMQ-интеграция: потребитель `bet-maker`, публикатор `line-provider`, миграция Alembic для колонок `settled_at`/`settled_via`, интерактор `settle_bets_for_event`, DLX/DLQ-топология, health-проверки брокера.

Архитектура правильно реализует ключевой инвариант: ставка не зависает в PENDING после завершения события. Manual ack, FOR UPDATE SKIP LOCKED, DLX/DLQ, сквозной `correlation_id` — все присутствуют и корректно соединены.

Найдено два **критических** дефекта: логический баг в публикации сообщений (событие `NEW→NEW` способно вызвать публикацию при определённом race-condition) и непойманный `KeyError` в `settle_bets_for_event`. Четыре **предупреждения** и три **информационных** замечания по надёжности тестов и качеству кода.

---

## Critical Issues

### CR-01: `set_event_state` публикует сообщение при переходе `NEW → NEW` если `previous_state == NEW`

**File:** `src/line_provider/interactors/set_event_state.py:49`

**Issue:** Условие публикации:
```python
if previous_state == EventState.NEW and new_state in _TERMINAL_TO_ROUTING:
```
проверяет `previous_state == NEW` и `new_state in _TERMINAL_TO_ROUTING`. Ключи `_TERMINAL_TO_ROUTING` — это только `FINISHED_WIN` и `FINISHED_LOSE`, поэтому на первый взгляд всё корректно. Однако при no-op переходе `NEW → NEW` функция `store.update()` возвращает `previous_state = NEW`, а `new_state = NEW`, и `NEW not in _TERMINAL_TO_ROUTING` — публикация не происходит.

Реальный баг в другом: функция `store.update()` вызывается **до** проверки `is_transition_allowed`. Если `is_transition_allowed` возвращает `False` и выбрасывает `TransitionForbiddenError`, публикация не происходит — правильно. Но если транзиция разрешена, а `store.update()` по какой-то причине возвращает неожиданный `previous_state` (например, хранилище вернёт терминальный `previous_state`), публикация всё равно не случится — _и это баг_, потому что переход уже записан в хранилище, но сообщение не отправлено.

Реальный критический баг: `set_event_state` получает `new_state: EventState`, а `EventFinishedMessage` принимает `new_state: EventTerminalState`. В строке 52:
```python
EventFinishedMessage(
    ...
    new_state=EventTerminalState(new_state.value),
    ...
)
```
— это явное приведение строковых значений через `EventTerminalState(new_state.value)`. Если в будущем `EventState` добавит терминальное состояние с именем, отличным от существующего в `EventTerminalState` (или значения не совпадут), будет выброшен `ValueError`, который **не поймается** как POISON-сообщение (это не `ValidationError`), а попадёт в catch-all `except Exception` в потребителе и уйдёт в DLQ. Но критически: прямо сейчас `EventTerminalState(new_state.value)` срабатывает без проверки — **в продакшн-коде line-provider нет явной защиты от несоответствия значений двух независимо поддерживаемых enum'ов** (что является прямым следствием дублирования схем в D-28). Это может привести к `ValueError` в runtime при изменении одного из enum'ов.

**Fix:**
```python
# В set_event_state.py добавить явное отображение вместо string-cast:
_EVENT_STATE_TO_TERMINAL: dict[EventState, EventTerminalState] = {
    EventState.FINISHED_WIN: EventTerminalState.FINISHED_WIN,
    EventState.FINISHED_LOSE: EventTerminalState.FINISHED_LOSE,
}

# Строка 52 заменить на:
new_state=_EVENT_STATE_TO_TERMINAL[new_state],
```
Это даст `KeyError` в compile-time-видимом словаре, а не скрытый string-cast, и mypy проверит исчерпанность маппинга.

---

### CR-02: `settle_bets_for_event` — непойманный `KeyError` при неизвестном `terminal_state`

**File:** `src/bet_maker/interactors/settle_bets_for_event.py:58`

**Issue:**
```python
new_status = _TERMINAL_TO_STATUS[terminal_state]
```
Если `terminal_state` — значение `EventTerminalState`, не присутствующее в `_TERMINAL_TO_STATUS` (сейчас там только `FINISHED_WIN` и `FINISHED_LOSE`), то выбросится `KeyError`. Это произойдёт **после** того, как сообщение уже получено из очереди. `KeyError` не является `ValidationError`, `UnsupportedSchemaVersion` или `IntegrityError` — он попадёт в catch-all `except Exception` в `on_event_finished` и приведёт к `reject(requeue=False)`, то есть сообщение уйдёт в DLQ.

Проблема в том, что сейчас enum `EventTerminalState` имеет ровно два значения, поэтому словарь полный. Но это **хрупкий инвариант**: добавление нового терминального состояния в enum без обновления словаря сломает обработку всех сообщений с этим состоянием молча (через DLQ). Нет ни статической, ни рантаймовой защиты. mypy при `strict=True` не поймает неполный `dict` literal.

**Fix:**
```python
# Добавить явную проверку или использовать match:
try:
    new_status = _TERMINAL_TO_STATUS[terminal_state]
except KeyError:
    raise UnsupportedSchemaVersion(
        f"terminal_state={terminal_state!r} has no BetStatus mapping"
    )
```
Это направит неизвестные состояния в ветку POISON (правильное поведение для непарсируемого сообщения), а не в catch-all.

---

## Warnings

### WR-01: `ValidationError` из Pydantic не будет поймана в `on_event_finished` — FastStream парсит payload **до** вызова обработчика

**File:** `src/bet_maker/entrypoints/messaging.py:168`

**Issue:** Обработчик объявлен с типизированным параметром `payload: EventFinishedMessage`. FastStream валидирует и десериализует payload **до вызова функции**. Если `ValidationError` возникает при разборе тела сообщения, FastStream перехватит её сам согласно политике `AckPolicy.MANUAL` и поведение будет определяться настройками FastStream, а **не** блоком `except ValidationError` внутри обработчика. Таким образом, `except ValidationError` в строке 168 никогда не сработает для ошибок десериализации payload — это мёртвая ветка.

На практике в текущей версии FastStream `AckPolicy.MANUAL` отключает автоматическое ack/nack — и если FastStream выбросит ValidationError до вызова хендлера, сообщение зависнет в unacked состоянии до переподключения или истечения таймаута consumer, что нарушает R7/R1.

**Fix:** Добавить `no_ack=False` или убедиться, что FastStream при `AckPolicy.MANUAL` + ошибке десериализации действительно доставляет сообщение в обработчик с `payload` как `dict` или `bytes`. Если нет — обработать это через `middleware` или изменить сигнатуру на `payload: dict[str, Any]` с ручным вызовом `EventFinishedMessage.model_validate(payload)` внутри try-блока, чтобы `ValidationError` гарантированно поималась.

---

### WR-02: `occurred_at` в `EventFinishedMessage` заполняется `deadline` события, а не реальным временем события

**File:** `src/line_provider/interactors/set_event_state.py:55`

**Issue:**
```python
occurred_at=new_event.deadline,
```
`occurred_at` семантически должно быть временем наступления события (момент перехода в терминальное состояние). Вместо этого используется `deadline` — плановый дедлайн события. Если событие завершилось досрочно (например, ставки закрыты раньше дедлайна), `occurred_at` будет отражать будущее время, что семантически некорректно и может вводить в заблуждение при отладке и аудите.

**Fix:**
```python
# Заменить на реальное время перехода:
occurred_at=datetime.now(timezone.utc),
```
Или добавить `finished_at` в результат `store.update()` и использовать его.

---

### WR-03: Доступ к приватному атрибуту `broker._connection_kwargs` в тестах — хрупкая связь с internal API FastStream

**File:** `tests/bet_maker/conftest.py:67`, `tests/bet_maker/conftest.py:139`, `tests/line_provider/conftest.py:26`

**Issue:**
```python
rabbit_router.broker._connection_kwargs["url"] = amqp_url
```
`_connection_kwargs` — приватный атрибут FastStream. Его структура может измениться в любом патч-релизе FastStream, что сломает все тесты, требующие реального RabbitMQ, без каких-либо явных ошибок о несовместимости API (только `KeyError` или AttributeError в runtime).

Это ключевой механизм подмены URL для testcontainers RabbitMQ, поэтому риск — не просто «тест не работает», а «тест продолжает работать, но подключается к неправильному брокеру», если структура ключей изменится.

**Fix:** Использовать переменную окружения до инициализации `RabbitRouter`. Поскольку `router` создаётся на уровне модуля, нужно гарантировать, что `os.environ["BET_MAKER_RABBITMQ_URL"]` установлен до первого импорта модуля. Это уже делается в conftest, но `_connection_kwargs` патч нужен только потому, что модуль уже импортирован к моменту установки env. Рефакторинг: выносить роутер в фабрику или принимать URL из настроек ленивым образом.

---

### WR-04: `asyncio.get_event_loop()` в E2E тесте — устаревший API, вызывает DeprecationWarning в Python 3.10+

**File:** `tests/bet_maker/test_e2e_rabbitmq.py:74`

**Issue:**
```python
loop = asyncio.get_event_loop()
deadline_poll = loop.time() + 5.0
while loop.time() < deadline_poll:
```
`asyncio.get_event_loop()` устарел в Python 3.10 и вызывает `DeprecationWarning` если вызывается вне running coroutine без явно установленного event loop. В pytest-asyncio с `asyncio_mode="auto"` внутри async-функции правильный способ — `asyncio.get_running_loop()`.

**Fix:**
```python
loop = asyncio.get_running_loop()
deadline_poll = loop.time() + 5.0
while loop.time() < deadline_poll:
```

---

## Info

### IN-01: Тест `test_integrity_error_rejects` не делает никаких утверждений

**File:** `tests/bet_maker/test_messaging.py:136-149`

**Issue:** Тест публикует сообщение, которое должно вызвать `IntegrityError` → `reject`, но не содержит ни одного `assert`. Тест проходит независимо от поведения обработчика — он не доказывает ничего. `TestRabbitBroker` не проверяет, что был вызван `reject`, а не `ack`.

**Fix:** Добавить spy на `msg.reject` либо проверить, что `settle_mock` была вызвана и не прошла ack:
```python
settle_mock = AsyncMock(side_effect=integ)
with patch("bet_maker.entrypoints.messaging._settle_with_retry", new=settle_mock):
    async with TestRabbitBroker(router.broker) as br:
        await br.publish(...)
settle_mock.assert_called_once()
```

---

### IN-02: `created_at` и `updated_at` в модели `Bet` объявлены без `timezone=True`

**File:** `src/bet_maker/models/bet.py:73-80`

**Issue:**
```python
created_at: Mapped[datetime] = mapped_column(
    server_default=func.now(),
    nullable=False,
)
updated_at: Mapped[datetime] = mapped_column(
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
)
```
В отличие от `settled_at` (строка 82-85, `sa.DateTime(timezone=True)`), `created_at` и `updated_at` не имеют явного `sa.DateTime(timezone=True)`. PostgreSQL вернёт `timestamp without time zone`. Python получит naive datetime без tzinfo. Это несоответствие: `settled_at` timezone-aware, `created_at`/`updated_at` — нет.

**Fix:**
```python
created_at: Mapped[datetime] = mapped_column(
    sa.DateTime(timezone=True),
    server_default=func.now(),
    nullable=False,
)
updated_at: Mapped[datetime] = mapped_column(
    sa.DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
)
```

---

### IN-03: `asyncio.sleep(2.0)` в E2E тесте — жёстко заданная задержка, источник нестабильности в CI

**File:** `tests/bet_maker/test_e2e_rabbitmq.py:131`

**Issue:**
```python
await asyncio.sleep(2.0)
```
После публикации poison-сообщения тест ждёт фиксированные 2 секунды перед проверкой DLQ. На медленном CI-окружении этого может не хватить; на быстром — это ненужная задержка. Аналогичного polling-loop, как в первом E2E-тесте, здесь нет.

**Fix:** Заменить на polling-loop с проверкой DLQ:
```python
deadline = asyncio.get_running_loop().time() + 5.0
got = None
while asyncio.get_running_loop().time() < deadline:
    got = await dlq.get(fail=False, timeout=0.2)
    if got is not None:
        break
    await asyncio.sleep(0.1)
assert got is not None, "DLQ has 0 messages — poison routing failed"
```

---

_Reviewed: 2026-05-18T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
