---
key: "RUN-20260804-1301"
project: "AO3"
issueType: "run"
status: "run-blocked"
priority: "p2"
summary: "RUN-20260804-1301"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-04T16:34:03Z"
updated: "2026-08-04T16:34:03Z"
archived: false
resolution: null
---

# RUN-20260804-1301

_Спроецировано из `runs/RUN-20260804-1301.md` (источник правды).
Статус в нашей машине: **Blocked**._

# RUN-20260804-1301 — regression (replay) на 1.10 (11)

**Blocked 2026-08-04T16:34:03Z (factory, координатор /qa-loop 3, переход
`{from: "*", to: Blocked, by: [factory]}` transitions.yaml — «нечего
гонять, не выдумывать вердикт»):** прогон замаскирован SAC-блокировкой
mitmdump.exe (WinError 4551, `core/mitm.py:317`), 69/165 ERROR при setup —
env-блокер устранён коммитом `253d3ff` (запуск через подписанный
`python.exe`), заменяющий прогон `RUN-20260804-1624` (v2, честный, 154/165)
уже триажен/эскалирован (ESC-017). Триажить ЭТОТ прогон содержательно
нечего — 69 ERROR одной сигнатуры не несут отдельного материала сверх уже
известного класса, 1 FAILED (TC-086/П10) подтверждён содержательно и
покрыт тем же вердиктом во v2. Решение Lead 2026-08-04T13:09:32
(routing-log) уже фиксировало «RUN-20260804-1301 не переоткрывается,
остаётся как есть» прозой — этот ход переводит решение в статус, иначе
`status: NeedsTriage` без лока навсегда мехнически матчил бы правило
«Разобрать падения прогона» на каждом проходе (находка этой сессии).
Снятие Blocked — человек/полный Lead, по правилу перехода
`{from: Blocked, to: NeedsTriage, by: [human]}` (если появится причина
реально триажить) либо прямая правка на `Closed` полным Lead.

## Контекст запуска

Триггер: диспатч Lead «ночной плановый прогон» репетиции тёмного дня
(`runs/REHEARSAL-2026-08-04.md`, Б7 карты сева — «ночной прогон стартует
test-runner на T0, ПЕРЕД включением heartbeat»; правила расписания
регрессии в `state/rules.yaml` нет — это Lead-триггер). Контекст: сборка
1.10/11 (`versionCode 11`, `source_commit 63f6aac3`), карта сева П1-П19+D7
уже применена к бордe/артефактам ДО этого прогона (по инструкции
диспетчера, вне owns этого хода).

Окружение поднято ДО старта (не мной): эмулятор `ao3_test_api34` на
дефолтном GPU (`hw.gpu.mode=swiftshader`, сверено диспетчером фактом), CA
mitmproxy в apex store OK, APK versionCode 11 установлен, Appium на
`:4723`. Собственная сверка присутствия устройства (канон): `. D:\AO3_tests\scripts\tasks.ps1; Get-Device` →
`DEVICE: emulator-5554`. Эмулятор/GPU-режим не трогал, как предписано.

**Команда** (канон, зеркалит baseline RUN-20260803-2012):
`Invoke-Pytest tests -m "(p0 or p1) and not live" --alluredir=../runs/RUN-20260804-1301/allure`,
запущена `run_in_background`; foreground-ожидание — `Wait-Process -Timeout
500`, три раунда (~1354 с / 22.6 мин суммарно, в пределах хода).

**PYTEST_EXIT** (дословный хвост pytest):

```
tests\canary\test_ao3_selectors.py EEEEEEEEE                             [  5%]
tests\canary\test_tap_zone_guard.py EEEE                                 [  7%]
tests\test_backup_restore.py .                                           [  8%]
tests\test_device_liveness_guard_unit.py ..............                  [ 16%]
tests\test_downloads.py ...EEEEEE                                        [ 22%]
tests\test_filter_profiles.py EFEEE                                      [ 25%]
tests\test_infinite_scroll.py EE                                         [ 26%]
tests\test_library.py .                                                  [ 27%]
tests\test_library_filters.py ..........                                 [ 33%]
tests\test_mitm_port_race_unit.py ...........                            [ 40%]
tests\test_mitm_upstream_guard_unit.py ....                              [ 42%]
tests\test_performance.py .EE                                            [ 44%]
tests\test_rating.py EE                                                  [ 45%]
tests\test_rating_listing.py EEEEEEEEEEEEEEEE                            [ 55%]
tests\test_reading_ux.py EEEEEE                                          [ 58%]
tests\test_replay_ca_check_unit.py .....                                 [ 61%]
tests\test_replay_infra_probe.py E                                       [ 62%]
tests\test_saf_infra_probe.py ...                                        [ 64%]
tests\test_security_backup_privacy.py ..                                 [ 65%]
tests\test_security_file_access.py .                                     [ 66%]
tests\test_security_manifest.py ..                                       [ 67%]
tests\test_seed_db_schema_race_unit.py .....                             [ 70%]
tests\test_settings_ratings_fail_closed_unit.py .......................  [ 84%]
tests\test_side_panel.py E                                               [ 84%]
tests\test_smoke.py ........                                             [ 89%]
tests\test_tabs.py .EEEEEEEEEE                                           [ 96%]
tests\test_visibility.py EEEEEE                                          [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
FAILED tests/test_filter_profiles.py::test_rename_filter_profile_to_duplicate_name
= 1 failed, 95 passed, 148 deselected, 3 warnings, 69 errors in 1354.17s (0:22:34) =
```

`PYTEST_EXIT=1` (ненулевой из-за 1 failed + 69 errors). Полный лог (13396
строк, cp1251) — `scratchpad`-копия сессии, allure-результаты — `runs/RUN-20260804-1301/allure/`
(709 файлов, 165 `*-result.json` — по одному на каждый из 165 selected
тестов).

`recoveries this session = 0/2` — N=0, ENV_ISSUE-токен строкой не открыт
(device-liveness guard ни разу не срабатывал; см. ниже отдельный, НЕ
покрытый этим счётчиком, env-инцидент).

## КРИТИЧЕСКАЯ НАХОДКА — массовый идентичный env-сигнатурный сбой, вне карты сева

**Факт, не вердикт (триаж — конвейеру).** 69 из 165 отобранных тестов
упали `ERROR at setup` с ОДНОЙ И ТОЙ ЖЕ сигнатурой на протяжении ВСЕГО
прогона (от первого теста на 5% до последнего на 100%, во всех
mitm/replay-зависимых test-файлах: `canary/test_ao3_selectors.py`,
`canary/test_tap_zone_guard.py`, `test_downloads.py`,
`test_filter_profiles.py`, `test_infinite_scroll.py`,
`test_performance.py`, `test_rating.py`, `test_rating_listing.py`,
`test_reading_ux.py`, `test_replay_infra_probe.py`, `test_side_panel.py`,
`test_tabs.py`, `test_visibility.py`):

```
tests\conftest.py:709: in replay
    mitm.start_replay(flows_file)
core\mitm.py:378: in start_replay
    _proc = _spawn_and_wait_listening([...])
core\mitm.py:317: in _spawn_and_wait_listening
    proc = subprocess.Popen(args)
...
E   OSError: [WinError 4551] Политика управления приложениями заблокировала этот файл
```

(перекодировано из cp1251 для читаемости; `args` = запуск
`D:\AO3_tests\framework\.venv\Scripts\mitmdump.exe --listen-host
0.0.0.0 --listen-port 8080 --server-replay ...`.) Файл `mitmdump.exe`
физически на месте и не менялся (`LastWriteTime 02.07.2026`, 108358
байт — позитивная проверка, не «файла нет»); ошибка — блокировка
СПУСКА процесса политикой управления приложениями Windows (класс Windows
Defender Application Control / Smart App Control / AppLocker), не
файловая/сетевая проблема. `Get-Device` в момент диагностики — устройство
живое; `recoveries=0/2` — device-liveness guard эту категорию не
покрывает (проблема на хосте, не на эмуляторе/Appium).

Это НЕ входит в карту сева репетиции (`runs/REHEARSAL-2026-08-04.md`):
ожидались точечные красные TC-085/086 (П10), TC-129/130 (П11) + фон
(TC-114/115 BUG-014, TC-139 BUG-015, бэклог TC-043/093). Вместо этого
mitmdump-спавн заблокирован ДЛЯ ВСЕХ tests, использующих fixture
`replay` — 69 узлов вместо ожидаемых ~4-6 предметных, включая маскировку
самих ожидаемых красных (TC-114/115/139/043/093 упали тоже, но по ЭТОЙ
причине, а не по своей содержательной — их «настоящий» статус на этой
сборке этим прогоном не подтверждён). Единственный содержательный
FAILED (не ERROR) — `test_rename_filter_profile_to_duplicate_name`
(TC-086) — прошёл setup (эта конкретная параметризация не требует
`replay`) и упал на `TimeoutException` при поиске `content-desc="Renam3"`
(соответствует ожидаемому П10 по карте сева).

Не чинил (вне границ роли и вне owns этого хода: `framework/`-код —
non-goals). Флаг для немедленного разбора Lead/failure-analyst — по
масштабу (42% отобранного набора) это выглядит как системная
env-деградация хоста между RUN-20260803-2012 (тот же класс тестов был
100% зелёным на mitmdump) и этим прогоном, а не содержательные дефекты
приложения/тестов.

## Падения — факт (без вердиктов, полный список см. `tc_results` в шапке)

| Категория | Кол-во | Пример TC | Сигнатура |
|---|---|---|---|
| ERROR at setup (mitmdump spawn blocked) | 69 | TC-013, TC-032, TC-067, TC-114, TC-129, TC-139, TC-043, TC-093 и др. | `OSError: [WinError 4551] Политика управления приложениями заблокировала этот файл` (см. находку выше) |
| FAILED (реальный ассерт/степ) | 1 | TC-086 | `selenium.common.exceptions.TimeoutException` на `content-desc="Renam3"` (ожидаемо по карте сева П10) |

Известные фоновые/сеяные узлы карты (TC-114/115, TC-139, TC-085/086,
TC-129/130, TC-043/093) присутствуют в списке красных, но 8 из 9
замаскированы вышеописанным env-сбоем (упали в setup, не дошли до своего
содержательного шага) — триаж не может подтвердить их «настоящую»
красноту этим прогоном, кроме TC-086 (прошла setup, красная по существу).

## Дефекты-собратья (D-0043) — доклад

1. **Основная находка раздела выше** — класс «Windows application-control
   policy блокирует спавн `mitmdump.exe`» — новый класс, ранее не
   встречавшийся в этом репозитории (RUN-20260803-2012 тем же mitmdump
   отработал штатно на той же машине несколькими часами ранее). Не
   расследовал корень (антивирус/групповая политика/недавнее обновление
   Defender) — не моя роль; факт для Lead.
2. Список 69 ERROR-узлов структурно совпадает с ЛЮБЫМ тестом, чья fixture
   `replay` идёт через `mitm.start_replay` — то есть это не про
   конкретные test-файлы, а про саму fixture-инфраструктуру; если
   аналогичная политика затронет `Install-MitmCA`/emulator-side
   компоненты в будущих прогонах — тот же класс.

## Условия закрытия прогона (Closed)

- [ ] Каждое падение имеет вердикт и связанное действие — НЕ выполнено
  (входит в границы failure-analyst/триажа конвейера, не test-runner)
- [ ] Для APP_BUG существует или создан BUG-файл — не применимо на этом шаге
- [ ] Карта покрытия (`state/coverage-map.md`) перегенерирована — не выполнялось (за qa-loop)

**Статус:** `NeedsTriage` — 70 красных узлов (1 failed + 69 error), из них
подавляющее большинство (69) несут ОДНУ идентичную env-сигнатуру вне
карты сева репетиции; требуется срочный разбор Lead/failure-analyst ДО
триажа по существу (иначе триаж будет разбирать симптом, не причину).
