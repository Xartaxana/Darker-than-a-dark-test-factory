---
key: "RUN-20260815-0149"
project: "AO3"
issueType: "run"
status: "run-closed"
priority: "p2"
summary: "RUN-20260815-0149"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-14T23:57:00Z"
updated: "2026-08-14T23:57:00Z"
archived: false
resolution: "done"
---

# RUN-20260815-0149

_Спроецировано из `runs/RUN-20260815-0149.md` (источник правды).
Статус в нашей машине: **Closed**._

# RUN-20260815-0149 — smoke (replay) на dev-local (12)

## Контекст запуска

Триггер: `state/app-under-test.yaml` изменился — новая локальная сборка,
`source_commit 59be96c6398786d33c878dbce33cb1ecde269374`, `coalesced_commits:
[85fbed44, 7a43fab8, 07805a9f, f8e66c33, bc32c275, 2a1ceca6, 24b7b13a, 6e64b1fb]`
(9 коалесцированных коммитов), `apk_sha256
bf17f15f3b441a1572bc505f2896f603f56b8117862df5a427ff23f17738e7cd`, `built_at
2026-08-14T23:14:07Z`, `version_code 12` (dev-local, build_source: local).
Правило rules.yaml 1 («Новая сборка → smoke, затем regression»).

Окружение поднято с нуля этим ходом: `. tasks.ps1; Get-Device` → `NO DEVICE`
(эмулятор был не поднят) → `Start-Emulator -WritableSystem` («CA visible in
apex store: OK») → `Start-Appium` (health-checked, `:4723`) → `Install-App`
(Success).

**Команда**: `pytest -m p0` (`$env:AO3_MODE = "replay"`, через `Invoke-Pytest`),
запущено `run_in_background` и дождано в этом же ходе (`Get-CimInstance` →
`Wait-Process -Id 16776 -Timeout 500`, 4 раунда — процесс живёт ~28 мин, дольше
одного окна ожидания). 49 selected / 467 collected (418 deselected).

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
=============== 49 passed, 418 deselected in 1667.11s (0:27:47) ===============
PYTEST_EXIT=0
```

`recoveries this session = 0/2` — счётчик 0, `ENV_ISSUE`-токен в выводе
отсутствовал (прогон дошёл до `sessionfinish` без единого device-recovery).

## Падения

Нет — все 49 selected тестов зелёные. Ничего для триажа не остаётся.

## Контекст триажа (не мой мандат, для сведения)

Среди 9 коалесцированных коммитов этой сборки — фиксы трёх известных багов,
ожидающих D1-верификацию: `7a43fab8` (BUG-059, счётчик снекбара фонового
открытия), `07805a9f` (BUG-067, auto-READ теряет downloadPath), `85fbed44`
(BUG-069, Copy URL debug-кнопка). Ни один из соответствующих TC не входит в
p0-набор smoke (TC-176, связанный с BUG-059 по записи `regression_status`
предыдущего прогона, в smoke-выборке отсутствует) — верификация вне периметра
этого прогона, что ожидаемо и не сюрприз. Также 6 новых коммитов вносят фичи
(EPUB download, library rating через внешний ридер, shared-folder sync,
e-ink mode, volume-button scrolling, floating page-turn buttons, private
GitLab snippet sync), ещё не в `docs/feature-registry.yaml` и не покрытые
существующим smoke-набором — их отсутствие в выводе выше ожидаемо.

## Сверка с baseline (владелец — test-runner, правило 4а CLAUDE.md)

Последний Triaged (фактически Closed, все действия по вердиктам закрыты)
smoke-прогон с полем `source_commit` в frontmatter — `RUN-20260811-0405`
(`source_commit: cc201f789f0fb123722bbba7b29b8e0c6412dac1`). Проверка
предковости ЭТИМ ходом:

```
. D:\AO3_tests\scripts\env.ps1
git -C D:\AO3_tests\app-under-test merge-base --is-ancestor cc201f789f0fb123722bbba7b29b8e0c6412dac1 59be96c6398786d33c878dbce33cb1ecde269374
EXIT=0
```

`EXIT=0` → `cc201f78` **ЯВЛЯЕТСЯ предком** `59be96c6` — baseline валиден,
force-push/переписанной истории в этом окне нет.

Красно-зелёная дельта против baseline: у `RUN-20260811-0405` было 3 красных
(TC-078, TC-118, TC-009) — все впоследствии закрыты как `ENV_ISSUE`/`TEST_BUG`
и триажем/test-maintainer доведены до зелёного состояния (см. тело того
отчёта, разделы «Резолюция test-maintainer»). В этом прогоне те же три TC —
зелёные. Все прочие TC baseline — тоже зелёные и здесь. Регрессии не видно
на уровне «что было красным / что стало красным»; содержательный триаж не
мой мандат.

## Дефекты-собратья (D-0043)

Ничего нового не замечено сверх уже задокументированного класса
(device-liveness/webview-race, AT-BUG-026/AT-BUG-047) — этот прогон его не
провоцировал (`recoveries 0/2`).

## Условия закрытия прогона (Closed)
- [x] Падений нет — триажить нечего, вердикты не требуются.
- [x] Baseline-сверка выполнена (ancestor, EXIT=0).
- [x] `tc_results` заполнен из allure-results этого прогона.
