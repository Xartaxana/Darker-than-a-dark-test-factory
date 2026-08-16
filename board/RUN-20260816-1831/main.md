---
key: "RUN-20260816-1831"
project: "AO3"
issueType: "run"
status: "run-needstriage"
priority: "p2"
summary: "RUN-20260816-1831"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T20:07:50Z"
updated: "2026-08-16T20:07:50Z"
archived: false
resolution: null
---

# RUN-20260816-1831

_Спроецировано из `runs/RUN-20260816-1831.md` (источник правды).
Статус в нашей машине: **NeedsTriage**._

# RUN-20260816-1831 — regression (replay) на dev-local (12)

## Контекст запуска

Триггер: тот же `state/app-under-test.yaml` (`source_commit
aa377e0ec9664fcd5439fec9391638fabf94f448`), правило rules.yaml 1, шаг 2 после
зелёного smoke (`RUN-20260816-1758`). Окружение переиспользовано из
smoke-хода (эмулятор/Appium/APK уже подняты этим же ходом, device не
освобождался между сегментами).

## Селекция (D1, `scripts/impact_select.py`)

```
python scripts/impact_select.py
Диапазон: 27d5cfd193b3e0475b872d5c5c80daadcc299a79..aa377e0ec9664fcd5439fec9391638fabf94f448 (app-under-test/)
Файлов изменено: 3

## ignore
- PROJECT.md

## wide_impact
- app/src/main/assets/ao3_bridge.js

## rules (области)
- app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt → browser, tabs, rating, visibility, filter-profiles, downloads, library

## unknown (вне карты)
- нет

## Решение
**FULL REGRESSION** (wide_impact: app/src/main/assets/ao3_bridge.js)
```

Диапазон по умолчанию (`coalesced_commits: []` в `state/app-under-test.yaml`
→ родитель самого `source_commit`) разрешился в
`27d5cfd193b3e..aa377e0ec966` — ровно предыдущий smoke/regression
baseline-коммит (сверено: `git log --oneline` в этом диапазоне даёт ровно
один коммит `aa377e0` «Fix undo-at-ceiling, infinite-scroll navigation traps,
and copy-URL guard», BUG-016/018/019/020/071, issues #7/#9/#10/#11/#43;
`git show --stat` подтверждает изменённые файлы: `PROJECT.md` (1),
`app/src/main/assets/ao3_bridge.js` (77), `.../BrowserViewModel.kt` (24)).

`ao3_bridge.js` матчит `wide_impact` карты (`state/impact-map.yaml:22`) →
fail-safe **FULL REGRESSION**, селекция не сузила набор (`rules`-совпадение
по `BrowserViewModel.kt` избыточно при уже сработавшем `wide_impact`).
`selection.mode: full`.

## Исполнение (сегментация, проактивная — известный класс убийства
харнессом длинных фоновых pytest-процессов ~45–60 мин, см. `RUN-20260815-0337`
и предшественники)

**Команда**: `pytest tests -m "(p0 or p1) and not live"` (`$env:AO3_MODE =
"replay"`, через `Invoke-Pytest`). Dry-run `--collect-only -q` подтвердил
**290 selected / 489 collected** (199 deselected) ДО старта, разбит на 2
сегмента по границам файлов (сумма 150 + 140 = 290, совпадает с dry-run —
ни один тест не пропущен и не задвоен между сегментами):

Сегмент 1 (canary + adb/env/library/downloads/filter-profiles/mitm-port-race,
150 selected из 176 collected):
```
pytest tests/canary/test_ao3_selectors.py tests/canary/test_bridge_init_retry.py
  tests/canary/test_tap_zone_guard.py tests/test_adb_run_as_file_or_raise_unit.py
  tests/test_backup_restore.py tests/test_default_env_state_guard_unit.py
  tests/test_device_liveness_guard_unit.py tests/test_downloads.py
  tests/test_filter_profiles.py tests/test_infinite_scroll.py tests/test_library.py
  tests/test_library_background_open.py tests/test_library_filters.py
  tests/test_library_tab_scroll_state.py tests/test_mitm_port_race_unit.py
  -m "(p0 or p1) and not live"
```
Дословный хвост:
```
tests\test_library_tab_scroll_state.py ....                              [ 92%]
tests\test_mitm_port_race_unit.py ...........                            [100%]

AT-BUG-026 device-liveness guard: recoveries this session = 0/2
========= 150 passed, 26 deselected, 2 warnings in 2887.51s (0:48:07) =========
PYTEST_EXIT=0
```
(2 warnings — синтетические `UserWarning` внутри самих unit-тестов
`test_default_env_state_guard_unit.py`/`test_device_liveness_guard_unit.py`,
проверяющих механизм предупреждения guard'а; они НЕ отражают реальное
device-recovery — итоговая строка счётчика (`recoveries this session = 0/2`,
`ENV_ISSUE`-токена нет) печатается ПОСЛЕ warnings summary и является
источником истины.)

Segment 1 allure-результаты сохранены копией (`framework/allure-results` →
`runs/RUN-20260816-1831/seg1-raw` временно, затем объединены — см. ниже) ДО
старта сегмента 2 (иначе `--clean-alluredir` их бы стёр).

Сегмент 2 (mitm-upstream/parse-tabs/performance/pull-app-file/rating*/
reading-ux/rename/replay/residual-proxy/saf/security*/seed-db/settings*/
side-panel/smoke/swipe/tabs/visibility/volume-paging, 140 selected из 178
collected):
```
pytest tests/test_mitm_upstream_guard_unit.py tests/test_parse_persisted_tabs_unit.py
  tests/test_performance.py tests/test_pull_app_file_fail_closed_unit.py
  tests/test_rating.py tests/test_rating_listing.py tests/test_reading_ux.py
  tests/test_rename_name_verification_unit.py tests/test_replay_ca_check_unit.py
  tests/test_replay_infra_probe.py tests/test_residual_proxy_guard_unit.py
  tests/test_saf_infra_probe.py tests/test_security_backup_privacy.py
  tests/test_security_file_access.py tests/test_security_manifest.py
  tests/test_seed_db_schema_race_unit.py tests/test_settings.py
  tests/test_settings_ratings_fail_closed_unit.py tests/test_side_panel.py
  tests/test_smoke.py tests/test_swipe_to_text_settle_unit.py tests/test_tabs.py
  tests/test_visibility.py tests/test_volume_paging.py -m "(p0 or p1) and not live"
```
Дословный хвост:
```
tests\test_smoke.py ......F.                                             [ 85%]
tests\test_swipe_to_text_settle_unit.py .                                [ 86%]
tests\test_tabs.py ............                                          [ 95%]
tests\test_visibility.py ......                                          [ 99%]
tests\test_volume_paging.py .                                            [100%]

================================== FAILURES ===================================
___________________________ test_clear_all_ratings ____________________________
...
    def open_clear_all_dialog(self):
        assert self.swipe_to_text("Clear all ratings"), "секция «Clear all ratings» не найдена прокруткой"
        els = self.driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textStartsWith("Clear")')
        target = next((e for e in els if e.text.strip() != "Clear all ratings"), None)
>       assert target is not None, "кнопка «Clear…» не найдена"
               ^^^^^^^^^^^^^^^^^^
E       AssertionError: кнопка «Clear…» не найдена

screens\settings_screen.py:38: AssertionError
=========== short test summary info ============
FAILED tests/test_smoke.py::test_clear_all_ratings - AssertionError: кнопка «...
AT-BUG-026 device-liveness guard: recoveries this session = 0/2
==== 1 failed, 139 passed, 38 deselected, 1 warning in 2769.97s (0:46:09) =====
PYTEST_EXIT=1
```
(warning здесь — та же синтетическая природа, `test_residual_proxy_guard_unit.py`
проверяет сам механизм; `recoveries this session = 0/2` — источник истины,
`ENV_ISSUE`-токена нет ни в одном сегменте.)

Оба сегмента дошли до `sessionfinish` штатно (`PYTEST_EXIT=0` и `PYTEST_EXIT=1`
соответственно — второй код 1 отражает контентное падение TC-004, не среду).

## Слияние allure-результатов

Оба сегмента исполняли НЕПЕРЕСЕКАЮЩИЕСЯ множества файлов (проактивный сплит
по границам файлов, не повторный прогон одного и того же диапазона после
убийства) — witness слияния (дословный вывод скрипта-анализа):
```
seg1 unique tests: 150
seg2 unique tests: 140
overlap historyIds: 0
combined unique tests: 290
status counts: {'passed': 289, 'failed': 1}
```
`290` совпадает с `290 selected` полного набора (dry-run `--collect-only`
ДО старта) — расхождений/пропавших тестов между сегментами нет, пересечений
по `historyId` нет (в отличие от прецедента `RUN-20260815-0337`, где
убийство харнесса создало 13 пересекающихся историй — здесь харнесс не
убивал процесс, сплит был превентивным, а не восстановительным).
`runs/RUN-20260816-1831/allure/` содержит объединённые сырые файлы обоих
сегментов (1611 файлов).

## Падения (факт, без вердикта — не мандат test-runner)

| Тест (TC) | Ошибка (кратко) | Allure статус |
|---|---|---|
| test_clear_all_ratings (TC-004, `@pytest.mark.p0`) | `AssertionError: кнопка «Clear…» не найдена` после `swipe_to_text("Clear all ratings")` в `settings_screen.py:38` (`test_smoke.py`) | failed |

Триаж не выношу (не мандат test-runner) — факт для failure-analyst.

## Контекст триажа (не мой мандат, для сведения failure-analyst)

`TC-004` («Clear all ratings») в ЭТОМ ЖЕ прогонном окне (та же сборка
`aa377e0e`, тот же эмулятор/APK, без переустановки) уже отработал ЗЕЛЁНЫМ
дважды: в предшествующем smoke-прогоне (`RUN-20260816-1758`, отдельный
pytest-процесс, ~1.5 ч до этого падения) и в baseline-прогоне на предыдущей
сборке. Здесь — падение в ОТДЕЛЬНОМ pytest-процессе (сегмент 2 regression) на
шаге поиска кнопки `Clear…` после прокрутки к «Clear all ratings» (не сам
свайп — свайп прошёл, `assert` на свайпе не сработал). Изменённый в этой
сборке код (`BrowserViewModel.kt`, `ao3_bridge.js`) касается undo-at-ceiling/
infinite-scroll/copy-URL — Settings-экран и диалог сброса рейтингов
докстрином коммита не упоминаются, но триаж (совпадение/несовпадение с
диффом сборки) не мой мандат — передаю факт как есть, включая наблюдение,
что тот же тест зелёный в соседнем прогоне той же сборки (возможный
кандидат FLAKY, вердикт не мой).

## Дефекты-собратья (D-0043)

Ничего нового сверх уже задокументированного класса (device-liveness/
webview-race AT-BUG-026/AT-BUG-047) не замечено — `recoveries 0/2` в обоих
сегментах, `ENV_ISSUE`-токена нет. Отдельно отмечаю (не расширяя scope):
падение TC-004 в этом прогоне при зелёном итоге того же теста в соседнем
прогоне той же сборки — потенциальный кандидат в класс «нестабильный
UI-тайминг» (сиблинг TC-154/TC-176 из `RUN-20260815-0337`, где падения тоже
были специфичны к сборке/процессу, а не воспроизводились системно), но
подтверждение класса — не мой мандат.

## Сверка с baseline (владелец — test-runner, правило 4а CLAUDE.md)

Последний Triaged/Closed regression-прогон с полем `source_commit` в
frontmatter — `RUN-20260816-0334` (`source_commit:
27d5cfd193b3e0475b872d5c5c80daadcc299a79`, `status: Closed`, `selection:
{mode: impact, areas: []}` — сама 0 тестов не гоняла). Ближайший ПОЛНЫЙ
regression-прогон с реальным исполнением — `RUN-20260815-0337`
(`source_commit: 59be96c6398786d33c878dbce33cb1ecde269374`). Проверка
предковости ЭТИМ ходом (относительно ближайшего Closed regression с
`source_commit`, `RUN-20260816-0334`):

```
cd D:\AO3_tests\app-under-test
git merge-base --is-ancestor 27d5cfd193b3e0475b872d5c5c80daadcc299a79 aa377e0ec9664fcd5439fec9391638fabf94f448
EXIT=0
```

`EXIT=0` → baseline **ЯВЛЯЕТСЯ предком** текущей сборки, валиден (не
force-push). `RUN-20260816-0334` сам не исполнял тестов (impact-селекция
дала `areas: []` на документационном диффе) — красно-зелёную дельту
сверяем с предыдущим full regression `RUN-20260815-0337`
(`source_commit: 59be96c6398786d33c878dbce33cb1ecde269374`): там
`TC-004: passed` (строка 15 frontmatter) — тест НЕ новый, присутствовал в
наборе и был зелёным. Дельта для failure-analyst: **TC-004 green→red**
именно в контексте полного регресса (тот же тест зелёный в соседнем
smoke этой же сессии, `RUN-20260816-1758`, `TC-004: passed`, и в
предыдущем smoke-baseline `RUN-20260816-0332`). `TC-154`/`TC-176`
(исторические падения `RUN-20260815-0337`) — здесь оба зелёные,
регрессии по ним не привнесено.

## Условия закрытия прогона (NeedsTriage)
- [ ] TC-004 (`test_clear_all_ratings`) требует вердикта failure-analyst
  (APP_BUG / TEST_BUG / SITE_CHANGED / ENV_ISSUE / FLAKY) и связанного
  действия.
- [x] Baseline-сверка выполнена (ancestor, EXIT=0).
- [x] `tc_results` заполнен из объединённых allure-results обоих сегментов
  (только `TC-xxx`-идентификаторы кейсов; внутренние `AT-BUG-xxx`/`ESC-xxx`
  regression-lock unit-тесты и служебный `TC-183-premise-...` — не кейсы
  `test-cases/`, в `tc_results` не включены).
- [x] `selection` зафиксирован (full, wide_impact-причина, диапазон явно
  указан).
- [ ] Карта покрытия (`state/coverage-map.md`) — НЕ перегенерирована (прогон
  не Closed).
