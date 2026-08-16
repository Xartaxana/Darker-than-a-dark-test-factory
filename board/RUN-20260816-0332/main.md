---
key: "RUN-20260816-0332"
project: "AO3"
issueType: "run"
status: "run-closed"
priority: "p2"
summary: "RUN-20260816-0332"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T01:34:20Z"
updated: "2026-08-16T01:34:20Z"
archived: false
resolution: "done"
---

# RUN-20260816-0332

_Спроецировано из `runs/RUN-20260816-0332.md` (источник правды).
Статус в нашей машине: **Closed**._

# RUN-20260816-0332 — smoke (replay) на dev-local (12)

## Контекст запуска

Триггер: `state/app-under-test.yaml` изменился — новая сборка, `source_commit
27d5cfd193b3e0475b872d5c5c80daadcc299a79` (versionCode 12, `dev-local`,
`build_source: local`, `apk_sha256
bf17f15f3b441a1572bc505f2896f603f56b8117862df5a427ff23f17738e7cd`, `built_at
2026-08-16T01:01:26Z`, `coalesced_commits: []`). Правило rules.yaml 1
(«Новая сборка → smoke, затем regression»).

Окружение поднято с нуля этим ходом: `. tasks.ps1; Get-Device` → `NO DEVICE`
→ `Start-Emulator -WritableSystem` (вывод несёт «CA visible in apex store:
OK») → `Start-Appium` (health-checked, `:4723`) → `Install-App` (Success) →
sha256 сверен фактом (`Get-FileHash` установленного APK ==
`bf17f15f3b441a1572bc505f2896f603f56b8117862df5a427ff23f17738e7cd`, совпадает
с `apk_sha256` из `state/app-under-test.yaml`).

**Команда**: `pytest -m p0` (`$env:AO3_MODE = "replay"`, через
`Invoke-Pytest`), запущено `run_in_background` и дождано в этом же ходе
(`Get-CimInstance` → PID 4680 венв-python → `Wait-Process -Id 4680 -Timeout
500`, 3 раунда — процесс завершился в третьем раунде, ~25 мин). 49 selected /
480 collected (431 deselected; коллекция выросла с 467 до 480 — новых p0-тестов
в наборе не добавилось, `49 selected` то же число, что и в baseline).

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
=============== 49 passed, 431 deselected in 1484.02s (0:24:44) ===============
PYTEST_EXIT=0
```

`recoveries this session = 0/2` — счётчик 0, `ENV_ISSUE`-токен в выводе
отсутствовал (прогон дошёл до `sessionfinish` без единого device-recovery).

## Падения

Нет — все 49 selected тестов зелёные. Ничего для триажа не остаётся.

## Контекст (для сведения)

Единственный новый коммит в этой сборке относительно предыдущего smoke-baseline
(`59be96c6398786d33c878dbce33cb1ecde269374`) — `27d5cfd1`
(«Correct two PROJECT.md claims that contradict the code», правки BUG-058/
BUG-065). Дифф — только `PROJECT.md` (7 insertions, 3 deletions), прикладного
кода не касается. Ожидаемо, что smoke не показал изменений поведения.

## Сверка с baseline (владелец — test-runner, правило 4а CLAUDE.md)

Последний Closed smoke-прогон с полем `source_commit` в frontmatter —
`RUN-20260815-0149` (`source_commit:
59be96c6398786d33c878dbce33cb1ecde269374`). Проверка предковости ЭТИМ ходом:

```
cd D:\AO3_tests\app-under-test
git merge-base --is-ancestor 59be96c6398786d33c878dbce33cb1ecde269374 27d5cfd193b3e0475b872d5c5c80daadcc299a79
EXIT=0
```

`EXIT=0` → `59be96c6` **ЯВЛЯЕТСЯ предком** `27d5cfd1` — baseline валиден, нет
force-push/переписанной истории в этом окне.

Красно-зелёная дельта против baseline: у `RUN-20260815-0149` все 37 уникальных
TC-меток (49 тестов) были зелёными; здесь — те же 37 TC-меток, те же 49
тестов, все зелёные. Регрессии не видно на уровне «что было красным / что
стало красным»; содержательный триаж не мой мандат (тут и триажить нечего).

## Дефекты-собратья (D-0043)

Ничего нового не замечено сверх уже задокументированного класса
(device-liveness/webview-race, AT-BUG-026/AT-BUG-047) — этот прогон его не
провоцировал (`recoveries 0/2`).

## Условия закрытия прогона (Closed)
- [x] Падений нет — триажить нечего, вердикты не требуются.
- [x] Baseline-сверка выполнена (ancestor, EXIT=0).
- [x] `tc_results` заполнен из allure-results этого прогона.
