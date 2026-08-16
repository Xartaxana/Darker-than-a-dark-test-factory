---
key: "RUN-20260816-1758"
project: "AO3"
issueType: "run"
status: "run-closed"
priority: "p2"
summary: "RUN-20260816-1758"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T18:27:12Z"
updated: "2026-08-16T18:27:12Z"
archived: false
resolution: "done"
---

# RUN-20260816-1758

_Спроецировано из `runs/RUN-20260816-1758.md` (источник правды).
Статус в нашей машине: **Closed**._

# RUN-20260816-1758 — smoke (replay) на dev-local (12)

## Контекст запуска

Триггер: `state/app-under-test.yaml` обновился на новую сборку —
`source_commit aa377e0ec9664fcd5439fec9391638fabf94f448` (versionCode 12,
`dev-local`, `build_source: local`, `apk_sha256
34e2abced39e3754b037919efdcfc819a599ac5f4228cc5a2157faac2a92ce32`, `built_at
2026-08-16T17:53:45Z`, `coalesced_commits: []`). Правило rules.yaml 1
(«Новая сборка → smoke, затем regression»).

Окружение поднято с нуля этим ходом: `. tasks.ps1; Get-Device` → `NO DEVICE`
→ `Start-Emulator -WritableSystem` (вывод несёт «CA visible in apex store:
OK») → `Start-Appium` (health-checked, `:4723`) → `Install-App` (Success) →
sha256 сверен фактом (`Get-FileHash` установленного APK ==
`34E2ABCED39E3754B037919EFDCFC819A599AC5F4228CC5A2157FAAC2A92CE32`, совпадает
с `apk_sha256` из `state/app-under-test.yaml`, регистр не имеет значения).

**Команда**: `pytest -m p0` (`$env:AO3_MODE = "replay"`, через
`Invoke-Pytest`), запущено `run_in_background` и дождано в этом же ходе
(`Get-CimInstance` → PID 17508 венв-python → `Wait-Process -Id 17508 -Timeout
500`, 4 раунда — процесс завершился в четвёртом раунде, ~29.5 мин). 49
selected / 489 collected (440 deselected).

Дословный хвост:
```
tests\canary\test_ao3_selectors.py .................                     [ 34%]
tests\canary\test_tap_zone_guard.py ....                                 [ 42%]
tests\test_backup_restore.py .                                           [ 44%]
tests\test_library.py ..                                                 [ 48%]
tests\test_performance.py ..                                             [ 53%]
tests\test_rating.py ......                                              [ 65%]
tests\test_rating_listing.py .....                                       [ 75%]
tests\test_smoke.py .........                                            [ 93%]
tests\test_visibility.py ...                                             [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
=============== 49 passed, 440 deselected in 1768.32s (0:29:28) ===============
PYTEST_EXIT=0
```

`recoveries this session = 0/2` — счётчик 0, `ENV_ISSUE`-токена в выводе нет
(прогон дошёл до `sessionfinish` без единого device-recovery).

## Падения

Нет — все 49 selected тестов зелёные. Ничего для триажа не остаётся.

## Контекст (для сведения)

Единственный новый коммит в этой сборке относительно предыдущего
smoke-baseline (`27d5cfd193b3e0475b872d5c5c80daadcc299a79`) —
`aa377e0ec9664fcd5439fec9391638fabf94f448` («Fix undo-at-ceiling,
infinite-scroll navigation traps, and copy-URL guard» — BUG-016/018/019/020/071,
issues #7/#9/#10/#11/#43). Дифф — `PROJECT.md` (1 строка),
`app/src/main/assets/ao3_bridge.js` (77 строк) и
`ui/browser/BrowserViewModel.kt` (24 строки). Smoke не показал изменений
поведения на p0-наборе (fix-коммит не задел p0-сценарии напрямую).

## Сверка с baseline (владелец — test-runner, правило 4а CLAUDE.md)

Последний Closed smoke-прогон с полем `source_commit` в frontmatter —
`RUN-20260816-0332` (`source_commit:
27d5cfd193b3e0475b872d5c5c80daadcc299a79`). Проверка предковости ЭТИМ ходом:

```
cd D:\AO3_tests\app-under-test
git merge-base --is-ancestor 27d5cfd193b3e0475b872d5c5c80daadcc299a79 aa377e0ec9664fcd5439fec9391638fabf94f448
EXIT=0
```

`EXIT=0` → `27d5cfd1` **ЯВЛЯЕТСЯ предком** `aa377e0e` — baseline валиден,
нет force-push/переписанной истории в этом окне.

Красно-зелёная дельта против baseline: у `RUN-20260816-0332` все 37
уникальных TC-меток были зелёными; здесь — те же 37 TC-меток, те же 49
тестов, все зелёные. Регрессии не видно на уровне «что было красным / что
стало красным»; содержательный триаж не мой мандат (тут и триажить нечего).

## Дефекты-собратья (D-0043)

Ничего нового не замечено сверх уже задокументированного класса
(device-liveness/webview-race, AT-BUG-026/AT-BUG-047) — этот прогон его не
провоцировал (`recoveries 0/2`). См. также «Дефекты-собратья» в отчёте
regression-прогона этой же сборки (`RUN-20260816-1831`) — там TC-004
(`test_clear_all_ratings`) упал в отдельном pytest-процессе, хотя в ЭТОМ
прогоне тот же тест зелёный: факт для failure-analyst, вердикт (FLAKY/
APP_BUG/ENV_ISSUE) не мой мандат.

## Условия закрытия прогона (Closed)
- [x] Падений нет — триажить нечего, вердикты не требуются.
- [x] Baseline-сверка выполнена (ancestor, EXIT=0).
- [x] `tc_results` заполнен из allure-results этого прогона.
