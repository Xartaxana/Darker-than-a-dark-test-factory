---
id: AT-BUG-082
title: "TC-112 (test_favorite_rating_does_not_download_when_auto_download_off) падает на assert_work_not_in_files_tab при прогоне ВСЕГО test_downloads.py, но 1/1 зелёный в изолированном перезапуске — order/state-зависимый флейк, не трогает Settings/find_row_sibling код"
type: test_debt
debt_kind: flaky_test
severity: major
status: Open
found_in: "test-maintainer, AT-BUG-080 rework verification pass (полный tests/test_downloads.py, 2026-08-17)"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-112"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-17T01:06:32Z"
updated: "2026-08-17T01:06:32Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-082 — TC-112 падает на `assert_work_not_in_files_tab` только внутри полного `test_downloads.py`, зелёный в изоляции

## Окружение

Долг тестовой системы (`type: test_debt`, `debt_kind: flaky_test`), поверхность —
`framework/tests/test_downloads.py::test_favorite_rating_does_not_download_when_auto_download_off`
(TC-112) / `framework/steps/library_steps.py::assert_work_not_in_files_tab`.
Эмулятор `emulator-5554`, API 34, replay (`work_with_download.mitm`).

## Обнаружено

Найдено ПОПУТНО при верификации rework-фикса `AT-BUG-080` (критик-вход, Б1-Б4) —
НЕ относится к самому фиксу, см. «Анализ». Полный прогон `Invoke-Pytest
tests/test_downloads.py -q` (после rework-правок `base_screen.py`/
`settings_screen.py`): `1 failed, 16 passed in 1882.49s`, единственное падение —
7-й тест по порядку (`......F..........`), TC-112:

```
AssertionError: работа «A Loved Test Work» неожиданно присутствует на вкладке FILES
steps\library_steps.py:85: AssertionError
```

Шаг перед этим (`assert_download_icon_shown`) прошёл штатно (карточка на вкладке
FAVORITE показывала download-, не open-иконку) — то есть на момент ЭТОЙ проверки
файл ещё не выглядел скачанным; следующий Then (проверка вкладки FILES) уже
увидел работу там.

## Изолирующее наблюдение (не в AT-BUG-080)

`Invoke-Pytest "tests/test_downloads.py::test_favorite_rating_does_not_download_when_auto_download_off" -q`
(тот же узел, ОДИН, без соседей по файлу) — **PASSED**, `1 passed in 116.89s`.

Тело теста НЕ обращается ни к одному из мест, которые правил rework `AT-BUG-080`
(`SettingsScreen`, `BaseScreen.find_row_sibling`/`tap_row_sibling`/
`swipe_to_text`/`swipe_up_to_text` — не импортируются и не вызываются нигде в
цепочке `app_steps.wait_app_ready` → `rating_steps.open_work_page` →
`rating_steps.rate_current_work` → `app_steps.open_tab` →
`library_steps.assert_work_in_tab`/`assert_download_icon_shown`/
`assert_work_not_in_files_tab`; сверено чтением тела теста и грепом импортов
файла). Given кейса — дефолтное состояние `Auto-download` (OFF) ПОСЛЕ
`clean_state`, тумблер в Settings вообще не трогается. Изолированный прогон
ПОСЛЕ тех же rework-правок (`base_screen.py`/`settings_screen.py` в текущем
рабочем дереве, без отката) дал PASS. **Правка критик-входа AT-BUG-080
round2 (N2), применена симметрично здесь:** сам ТЕСТ не исполняет
изменённый код, но падение order/state-зависимое, а СОСЕДНИЕ тесты того же
файла (`test_downloads.py`) изменённый код исполняют (`tap_row_sibling`/
`_settle_clipped_anchor` меняют тайминги между тестами серии) — по правилу
14 (каузальный негатив) «не исполнялось в самом тесте» ≠ «вклад исключён».
Вклад rework-правок в это падение **НЕ исключён и НЕ подтверждён**;
исключающий прогон (полный `test_downloads.py` на пред-rework дереве) не
делался.

## Анализ (предварительный, гипотеза не подтверждена изолирующим экспериментом)

Симптом — order/state-зависимый: красный ТОЛЬКО внутри полного файла (после 6
предыдущих тестов того же файла), зелёный при изолированном перезапуске узла.
Кандидаты (НЕ проверены по отдельности, простая гипотеза по классу):
- state-утечка между тестами того же файла, несмотря на `app_steps.clean_state()`
  в фикстурах (например, download-директория/Room `filter_profiles`-аналог для
  downloads не полностью очищается `pm clear` в высоконагруженной серии, либо
  фоновый `DownloadRepository`-таймер предыдущего теста дописывает файл уже
  ПОСЛЕ `clean_state` следующего);
- гонка в `assert_work_not_in_files_tab`/`LibraryScreen.has_work` — тот же класс,
  что `AT-BUG-081` (Then читает состояние раньше, чем оно устаканилось), но в
  другом слое (Compose-список вкладки FILES, не Room).

Не расширяю scope AT-BUG-080 починкой этого — другой класс дефекта (order/state
между тестами `test_downloads.py`, не swipe/bounds-геометрия и не
`find_row_sibling`). Доклад + баг, диспетчеризация фикса — за Lead/очередь B4.

## Критерий готовности (Fixed)

- [ ] Локализована причина (state-утечка между тестами ИЛИ гонка чтения вкладки
      FILES) — изолирующим экспериментом (например, парный прогон двух соседних
      тестов файла, или логкат `DownloadRepository` вокруг момента падения).
- [ ] Красная проба/регресс-проверка: полный `test_downloads.py` даёт зелёный
      TC-112 минимум 2 раза подряд ПОСЛЕ фикса.
- [ ] Если причина — гонка чтения вкладки FILES (не state-утечка), проверить
      остальные `assert_work_*_in_files_tab`-callers на тот же класс (класс, не
      экземпляр).

## Обсуждение

**[test-maintainer @ 2026-08-17T01:06:32Z]** Заведён ПОПУТНО при верификации
rework-фикса `AT-BUG-080` (критик-вход, блокеры Б1-Б4). Полный
`tests/test_downloads.py` дал 1 красный из 17 (TC-112); изолированный
перезапуск ТОГО ЖЕ узла — зелёный. Тело теста не обращается ни к одному из
мест, изменённых rework'ом (`SettingsScreen`/`find_row_sibling`/
`tap_row_sibling`/`_swipe_search` — не в цепочке вызовов этого теста), но
(см. правку критик-входа выше) вклад соседних тестов серии НЕ исключён —
только сам тест изолированно чист. Не путать с `BUG-014`
(app_bug, Verified, cc201f7) — тот класс про правку тега/заметки на уже-Favorite
работе (edge-vs-level), этот тест вообще не редактирует метаданные.
