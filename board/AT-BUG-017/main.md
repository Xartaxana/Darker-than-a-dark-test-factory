---
key: "AT-BUG-017"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "replay-фикстура: интермиттентный net::ERR_PROXY_CONNECTION_FAILED на первой навигации после set_device_proxy — не покрыт rerun-whitelist pytest.ini"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T09:47:00Z"
updated: "2026-07-18T09:47:00Z"
archived: false
resolution: null
---

# replay-фикстура: интермиттентный net::ERR_PROXY_CONNECTION_FAILED на первой навигации после set_device_proxy — не покрыт rerun-whitelist pytest.ini

_Спроецировано из `bugs/AT-BUG-017.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-017 — интермиттентный net::ERR_PROXY_CONNECTION_FAILED вне rerun-whitelist

## Окружение
- Затрагивает ЛЮБОЙ `@pytest.mark.replay` тест — не специфично для rating-батча
  (класс, D-0043): `test_visibility.py`, `test_filter_profiles.py`,
  `test_rating_listing.py`, TC-040/041 и т.д. — все используют одну и ту же
  `replay`-фикстуру (`framework/tests/conftest.py:387-418`).

## Суть долга

`replay`-фикстура (`conftest.py:410-411`) вызывает
`mitm.set_device_proxy()` (переключает `http_proxy` устройства на хост),
ЗАТЕМ `mitm.start_replay(flows_file)` (поднимает `mitmdump`, блокируется
до `_wait_listening` на HOST-порту). К моменту `yield` оба шага
завершены — но на устройстве (эмулятор, qemu NAT) первая реальная
навигация через свежепереключённый прокси иногда падает
`net::ERR_PROXY_CONNECTION_FAILED` в `driver.get()`
(`browser_steps.open_listing`), хотя `mitmdump` уже подтверждённо
слушает порт на хосте — похоже на race NAT-уровня qemu (проброс порта/
ARP) или задержку применения системной настройки прокси Android'ом
относительно момента, когда WebView реально пытается открыть
TCP-соединение.

`pytest.ini:12` — `--only-rerun ReadTimeoutError|MaxRetryError` — не
покрывает этот класс сетевой ошибки, поэтому `--reruns 1` не срабатывает
и единичный интермиттентный сбой даёт HARD FAIL прогона.

## Критерий готовности (Fixed)

Один из вариантов (решение за исполнителем/Lead при приёмке — оценить
риск маскировки реального прокси-мискофига):
1. **Явный guard+retry в `replay`-фикстуре** (предпочтительно по
   философии кодовой базы — см. AT-BUG-011 fail-fast/AT-BUG-013
   Wait-PackageServiceReady: явная проверка готовности, не слепой
   ретрай на уровне pytest): после `set_device_proxy()`+`start_replay()`
   — лёгкая проверка достижимости прокси СО СТОРОНЫ УСТРОЙСТВА (например,
   `adb shell` HTTP HEAD-запрос через прокси, или первая навигация внутри
   фикстуры с коротким ретраем) ДО `yield`, чтобы тест никогда не видел
   этот транзиент.
2. **Узкое расширение `--only-rerun`** на именно
   `net::ERR_PROXY_CONNECTION_FAILED` (не широкий `net::ERR_PROXY*`,
   чтобы не замаскировать реальный мискофиг прокси другого класса) —
   проще, но per-test, не устраняет race у корня.

Плюс: 3 стабильных зелёных прогона `test_rating_listing.py` (12 тестов)
подряд без флейка (это разблокирует приёмку rating-batch-*, которая сейчас
ДОРАБОТАТЬ по этой находке).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт фикса |

## Обсуждение

**2026-07-18T09:15:00Z — координатор (Lead, Sonnet), по вердикту critic
(rating-batch-009-010-011-012-043-044-045-056, ДОРАБОТАТЬ):** заведено по
правилу 3б CLAUDE.md (критик-диагностика неясного флейка) — логика 8
тестов rating-батча сама по себе чистая (4 нетривиальные находки
подтверждены построчно, 2 красные пробы валидны, регрессия зелёная),
блокирующая находка — исключительно инфраструктурная (класс, не
пер-тестовая). Батч rating остаётся НЕ принятым (task_id
rating-batch-009-010-011-012-043-044-045-056), ждёт фикса этого долга и
повторной верификации (3 стабильных прогона).

**2026-07-18T09:47:00Z — test-maintainer, Open → Fixed:** выбран вариант 1
(явный guard, предпочтительный по философии кодовой базы — прецеденты
AT-BUG-011/AT-BUG-013), не вариант 2 (расширение `--only-rerun`): вариант 2
не устраняет race у корня и per-test, а не class-фикс (правило 9 CLAUDE.md —
проблема затрагивает ВСЕ `@pytest.mark.replay` тесты через одну фикстуру).

Диагностика источника race (замер на устройстве, emulator-5554, до фикса):
`_wait_listening` (`mitm.py`) подтверждает только ХОСТ-порт. Со стороны
УСТРОЙСТВА проверено вручную `adb shell nc` (toybox, есть на стандартном
AVD-образе — подтверждено `adb shell which nc` → `/system/bin/nc`) на
`10.0.2.2:8080`:
- ПОКА mitmdump не поднят на хосте — `nc -w 1 -q 1 10.0.2.2 8080` даёт
  `nc: Timeout` (не мгновенный `Connection refused`, как ожидалось бы для
  закрытого порта на обычном хосте) — это симптоматично для NAT-уровня qemu
  (проброс 10.0.2.2 ведёт себя иначе, чем прямой TCP), ровно тот класс race,
  что описан в находке critic.
- Сразу ПОСЛЕ ручного старта mitmdump на хосте (`--listen-port 8080`) тот же
  `nc`-пробник с устройства отвечает `NC_OK` немедленно.

Реализация (`framework/core/mitm.py::wait_device_proxy_reachable`): поллинг
TCP-достижимости `settings.PROXY_HOST_ALIAS` СО СТОРОНЫ УСТРОЙСТВА через
`adb shell nc -w1 -q1` (пустой stdin, интересует только факт TCP-коннекта);
короткий таймаут (`settings.PROXY_DEVICE_REACHABLE_TIMEOUT`, дефолт 10с, тот
же паттерн, что `adb._wait_package_service_ready`/AT-BUG-013) с явной
`TimeoutError` при исчерпании — не молчаливый клин, ноль лишней задержки на
счастливом пути (mitmdump к этому моменту обычно уже слушает и хост-порт, и
доступен со стороны устройства). `framework/tests/conftest.py::replay`
зовёт guard ПОСЛЕ `set_device_proxy()`+`start_replay()`, ДО `yield` — тест
теперь никогда не видит этот транзиент. Новая юнит-проба (device-free,
монки-патч `subprocess.run`+`time.sleep`, тот же приём, что
`test_adb_install_package_wait_unit.py`): счастливый путь без лишнего
`sleep`, ретрай N раз до готовности, явная `TimeoutError` с контекстом при
исчерпании, зависший `adb shell nc` (`subprocess.TimeoutExpired`) трактуется
как неудачная попытка, не пробрасывается голым — 4/4 PASS
(`Invoke-Pytest tests/test_mitm_proxy_reachable_unit.py -q`, вместе с
существующими 11 device-free юнит-пробами того же пакета — 15/15 PASS, без
регресса).

Witness (device, emulator-5554, Appium уже поднят на :4723):
- `test_rating_listing.py` (12 тестов, TC-009 — тот самый флейкующий кейс):
  **3 прогона подряд, все 12/12 PASSED**, `PYTEST_EXIT=0` на каждом —
  run 1: `12 passed in 483.29s`; run 2: `12 passed in 471.53s`; run 3:
  `12 passed in 514.13s`. Ни одного `net::ERR_PROXY_CONNECTION_FAILED` за
  все 3 прогона (баг интермиттентный — раньше давал 1/12 FAIL на первом
  независимом прогоне; здесь 0/36 FAIL суммарно).
- Регрессия другого replay-теста: `test_filter_profiles.py` —
  `2 passed, 1 skipped in 155.03s`, `PYTEST_EXIT=0` (skip — известный,
  не связанный guard AT-BUG-016, не про эту фикстуру).

`python scripts/arch_check.py` не запускался (эта проба не в owns —
уточнение: правки только `framework/core/mitm.py`,
`framework/tests/conftest.py`, `framework/config/settings.py`,
`framework/tests/test_mitm_proxy_reachable_unit.py`; `pytest.ini` НЕ тронут
— вариант 1 не требует расширения whitelist). `app-under-test/` не тронут.

Тест-кейсы: не про конкретный TC, инфраструктурный долг класса
(`debt_kind: broken_environment`) — обновления `test-cases/` не требуется.
Батч `rating-batch-009-010-011-012-043-044-045-056` теперь разблокирован
для повторной приёмки (3 стабильных прогона набраны).

Пересмотра стратегии/рисков не требует. Новых блокеров не обнаружено.
`status: Open → Fixed`, лок снят. Готово к `fix-verifier` (B4 → D1, долг
тестовой обвязки — сборку приложения ждать не нужно, guard test-maintainer).
