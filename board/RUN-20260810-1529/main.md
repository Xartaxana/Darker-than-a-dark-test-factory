---
key: "RUN-20260810-1529"
project: "AO3"
issueType: "run"
status: "run-closed"
priority: "p2"
summary: "RUN-20260810-1529"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T00:00:00Z"
updated: "2026-07-02T00:00:00Z"
archived: false
resolution: "done"
---

# RUN-20260810-1529

_Спроецировано из `runs/RUN-20260810-1529.md` (источник правды).
Статус в нашей машине: **Closed**._

# RUN-20260810-1529 — canary (live) на dev-local (versionCode 12)

## Контекст запуска

Триггер: `state/rules.yaml` — «Ежедневный canary на live AO3» (нет
canary-RUN за текущие сутки UTC; последний — RUN-20260804-1355). Манифест:
`suite: [canary], mode: live`. Сборка — `state/app-under-test.yaml`:
version_name dev-local, versionCode 12, `source_commit 6f884d97`, APK на
устройстве консистентен (не переустанавливался).

**Env-предпосылка TC-078** (`test-cases/canary/TC-078.md` «Заметки»,
AT-BUG-021): live-прогон этого кейса стабилен ТОЛЬКО под `AO3_EMU_GPU=host`.

### Подготовка окружения (честно, включая свои промахи)

1. На входе эмулятор уже был поднят, но под `-gpu swiftshader_indirect
   -writable-system` (командная строка процесса сверена
   `Get-CimInstance Win32_Process` — не тот GPU-режим, что требует TC-078).
   Убил (`adb emu kill`, факт — процесс qemu исчез) и перезапустил
   `Start-Emulator -Gpu host` (без `-WritableSystem`).
2. Сверка ФАКТОМ `hw.gpu.mode = host` в `hardware-qemu.ini` — OK. Пробный
   прогон ПОЛНОГО canary-каталога (`tests/canary`, 23 items, без `-m`)
   упал 13 ошибками setup — все replay-подтесты: `mitm-CA не установлена
   в системном хранилище (требуется -writable-system)` (`AT-BUG-011`).
   Это мой промах: перезапуск без `-WritableSystem` потерял CA. Живой
   продуктовый вывод не при чём — 10 live-тестов из тех же 23 прошли
   зелёными в этом же прогоне.
3. Исправление: убил эмулятор повторно (факт — процесс исчез), поднял
   заново `Start-Emulator -Gpu host -WritableSystem` — вывод завершился
   строкой `CA visible in apex store: OK`. Повторная сверка GPU-режима
   ФАКТОМ — `hw.gpu.mode = host` (не изменился). `Get-Device` →
   `DEVICE: emulator-5554`. Appium (`:4723/status`) — `ready:true` (тот же
   процесс, пережил рестарт эмулятора).
4. Диагностический прогон ПОЛНОГО `tests/canary` (23 items) после фикса
   CA: 20 passed, 3 errors — все с ОДНОЙ идентичной сигнатурой
   `TimeoutError: mitmdump не занял порт 8080 за 15s` (`core/mitm.py:358`,
   replay-фикстура), рассеянные по прогону (test 8/23, 15/23, 21/23) —
   класс совпадает с описанием фейл-фаст правила (2+ идентичных
   Timeout на одном вызове/шаге). Пост-фактум диагностика: `Get-Device`
   → `DEVICE: emulator-5554`, Appium `ready:true`, зомби-процессов
   `mitmdump.exe`, держащих порт 8080, не найдено — среда на момент
   диагностики выглядит здоровой (не устойчивая деградация). Это
   ОТДЕЛЬНЫЙ (не device-liveness guard'а) класс env-флейка — отмечен
   ниже как замеченный сиблинг, не входит в итоговый результат этого
   прогона (см. следующий пункт).
5. Пересмотрел canon: правило «Ежедневный canary на live AO3»
   (`state/rules.yaml`) явно ссылается на established live-baseline
   RUN-20260804-1355 (10/10, `-m live`, 13 deselected из тех же 23) —
   ЭТО canonical scope дневного canary, не полный каталог 23 (полный
   набор с replay-парами я гонял только как диагностику, сверх мандата).
   Финальный (отчётный) прогон — канон: `Invoke-Pytest tests/canary -m
   live`, эмулятор/GPU/CA без изменений от шага 3.

Итоговая команда (канон, зеркалит RUN-20260804-1355):
`. D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/canary -m live`,
фон (`run_in_background`), PID venv-python (7964) дождан `Wait-Process`.

## Дословный pytest-хвост (witness, финальный канонический прогон)

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\AO3_tests\framework
configfile: pytest.ini
plugins: allure-pytest-2.16.0, rerunfailures-16.4
collected 23 items / 13 deselected / 10 selected

tests\canary\test_ao3_selectors.py ..........                            [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
================ 10 passed, 13 deselected in 224.69s (0:03:44) ================
PYTEST_EXIT=0
```

`recoveries this session = 0/2` — N=0, ENV_ISSUE-токен строкой не открыт;
дублирование в теле не требуется (правило — обязательно только при N>0).

## Падения и триаж

Падений нет — 10/10 passed, включая env-чувствительный TC-078
(`test_main_pairing_checkbox_availability_live`) под `hw.gpu.mode=host`.

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| — | — | — | — | — |

## Дефекты-собратья (D-0043) — доклад

1. **Сиблинг замечен в диагностическом (не отчётном) прогоне полного
   `tests/canary` (23 items) на шаге 4 подготовки**: 3 setup-ошибки с
   ОДНОЙ идентичной сигнатурой `TimeoutError: mitmdump не занял порт
   8080 за 15s` (`core/mitm.py:358`, вызывается из `start_replay` через
   фикстуру `replay`) — тот же класс, что уже задокументирован в самом
   коде как `AT-BUG-043` (см. докстринг `core/mitm.py::
   _spawn_and_wait_listening`, «AT-BUG-043 attempt 2»). Три падения
   рассеяны по ходу 12-минутного прогона (не подряд), пост-фактум
   диагностика (Get-Device/Appium/поиск зомби-mitmdump) не нашла живого
   блокера — не подтверждаю и не опровергаю причину (не моя роль),
   докладываю факт для failure-analyst/Lead: не входит в итоговый
   canary-результат (тот прогон не был канонической целью хода), но это
   тот же класс, что уже трижды встречался этому репо
   (`AT-BUG-043`/mitm-стартовый race) — по карте осей это фреймворковый
   риск replay-инфраструктуры под нагрузкой `-Gpu host`, не продуктовый
   дефект.
2. Собственный env-промах шага 1-2 (потеря CA при рестарте эмулятора без
   `-WritableSystem`) — не новый класс дефекта, а известное требование
   (`AT-BUG-011`), зафиксировано для полноты witness, не как находка.

## Условия закрытия прогона (Closed)
- [x] Падений нет — таблица триажа пуста, вердиктов не требуется
- [x] APP_BUG не создавался (нет падений)
- [ ] Карта покрытия (`state/coverage-map.md`) не перегенерирована в этом
      ходе (canary-прогон не меняет состав TC регрессии/смока; при
      необходимости — отдельным шагом `coverage_map.py`)
