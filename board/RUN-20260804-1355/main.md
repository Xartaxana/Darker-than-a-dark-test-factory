---
key: "RUN-20260804-1355"
project: "AO3"
issueType: "run"
status: "run-closed"
priority: "p2"
summary: "RUN-20260804-1355"
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

# RUN-20260804-1355

_Спроецировано из `runs/RUN-20260804-1355.md` (источник правды).
Статус в нашей машине: **Closed**._

# RUN-20260804-1355 — canary на 1.10 (versionCode 11)

## Контекст запуска

Перепрогон-замена RUN-20260804-1317 по вердикту ENV_ISSUE триажа: прежний
canary-прогон шёл на swiftshader (программный рендер) вопреки предпосылке
TC-078 (`AO3_EMU_GPU=host`), что дало WebDriverException при WEBVIEW-switch
("loader has changed while resolving nodes") на TC-078 — 9/10 passed.

Эмулятор был поднят заранее failure-analyst'ом (~13:37 локального,
`Start-Emulator -WritableSystem -Gpu host`; CA переустановлен store=134
apex=134, Appium :4723 ready) — эта сессия его не перезапускала. Присутствие
устройства сверено канонически:

```
. D:\AO3_tests\scripts\tasks.ps1; Get-Device
DEVICE: emulator-5554
```

Конфигурация GPU сверена ФАКТОМ из
`tools/avd/ao3_test_api34.avd/hardware-qemu.ini` (не пересказом):

```
hw.gpu.enabled = true
hw.gpu.mode = host
```

Сборка: `state/app-under-test.yaml` (versionCode 11, source_commit 63f6aac,
build_type debug, апк не переустанавливался — та же инсталляция, что была на
момент RUN-20260804-1317).

Команда прогона (канон): `. D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/canary -m live`
(фон, PID 6848 venv-python дождан `Wait-Process`).

## Дословный pytest-хвост (witness)

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\AO3_tests\framework
configfile: pytest.ini
plugins: allure-pytest-2.16.0, rerunfailures-16.4
collected 23 items / 13 deselected / 10 selected

tests\canary\test_ao3_selectors.py ..........                            [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
================ 10 passed, 13 deselected in 193.72s (0:03:13) ================
PYTEST_EXIT=0
```

`recoveries this session = 0/2` — device-liveness guard ни разу не
срабатывал, N=0, дословную строку дублировать в теле не требуется (правило
test-runner: дублирование обязательно только при N>0).

## Падения и триаж

Падений нет — 10/10 passed, включая ранее красный TC-078
(`test_main_pairing_checkbox_availability_live`), под host GPU прошёл зелёным.

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| — | — | — | — | — |

## Cloudflare-сигнатура

Не встречена как рантайм-событие. В result.json каждого теста присутствует
статическое имя шага "...устойчиво к Cloudflare bot-check, R-03)" —
это боилерплейт-описание устойчивости навигационного хелпера (одинаковое во
всех тестах, design-referenced), НЕ факт реального challenge/interstitial:
поиск по `challenge|cf-ray|cf-mitigated` в allure-results результата не дал
(проверено с позитивным контролем — совпадение по "checkbox" в тех же
файлах нашлось).

## Условия закрытия прогона (Closed)
- [x] Падений нет — таблица триажа пуста, вердиктов не требуется
- [x] APP_BUG не создавался (нет падений)
- [ ] Карта покрытия (`state/coverage-map.md`) не перегенерирована в этом ходе
      (canary-перепрогон замены не меняет состав TC регрессии/смока; при
      необходимости — отдельным шагом coverage_map.py)
