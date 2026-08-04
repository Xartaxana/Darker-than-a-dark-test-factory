---
key: "RUN-20260804-1624"
project: "AO3"
issueType: "run"
status: "run-needstriage"
priority: "p2"
summary: "RUN-20260804-1624"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-04T16:24:46Z"
updated: "2026-08-04T16:24:46Z"
archived: false
resolution: null
---

# RUN-20260804-1624

_Спроецировано из `runs/RUN-20260804-1624.md` (источник правды).
Статус в нашей машине: **NeedsTriage**._

# RUN-20260804-1624 — regression (replay) на 1.10 (11)

## Контекст запуска

Триггер: прямая инструкция координатора — повторный «ночной плановый прогон»
репетиции тёмного дня, ЗАМЕНА `runs/RUN-20260804-1301.md` (тот прогон дал
95/165 passed + 1 failed + 69 ERROR одной сигнатурой `WinError 4551`, Smart App
Control блокировал spawn `mitmdump.exe`; причина устранена коммитом `253d3ff`
— spawn теперь через подписанный `python.exe`; живая replay-проба зелёная ДО
этого прогона). `RUN-20260804-1301.md` не трогался, остаётся как есть.

Окружение поднято заранее (не мной): эмулятор `ao3_test_api34` (`emulator-5554`,
GPU `swiftshader_indirect` дефолт — не менял), CA mitmproxy в сторе, APK v1.10
(versionCode 11), Appium на `:4723`. Сверено `Get-Device` → `DEVICE:
emulator-5554` дважды (до старта и после обоих сегментов прогона).

**Команда**: канон RUN-20260803-2012 — `pytest tests -m "(p0 or p1) and not
live" ` (`AO3_MODE=replay`), 165 selected / 313 collected (148 deselected).

## Находка: фоновый job снова убит харнессом на ~60-минутной отметке (рецидив)

Тот же класс, что зафиксирован в `runs/RUN-20260803-2012.md` («Находка»,
дефект-собрат №1): полный прогон запущен через `run_in_background`,
foreground `Wait-Process -Timeout 500` вызывался повторно (канон 07-19) —
6 раундов, ~60 минут. На последнем раунде системное `task-notification`
сообщило `status: killed`; сам pytest-процесс не дожил до `sessionfinish`
(вывод обрывается на 89%, `tests\test_tabs.py ..` без завершающей строки
файла/summary). `Get-Device` сразу после обрыва → `DEVICE: emulator-5554`
(эмулятор жив), Appium (`node.exe`) и `qemu-system-x86_64.exe` тоже живы —
обрыв НЕ связан со средой приложения, это лимит времени жизни фонового job'а
самого Bash-тула (~60 мин), теперь наблюдался дважды подряд на этом же классе
прогона (RUN-20260803-2012 и этот).

**Восстановление** (тот же метод, что в RUN-20260803-2012): `allure-results`
первого сегмента (150/165 json-результатов) забэкаплены в scratchpad ДО
перезапуска (`--clean-alluredir` иначе стёр бы их). Недостающие 15 тестов
(9 хвостовых `test_tabs.py` + весь `test_visibility.py`, 6 тестов) — сверены
явно через `--collect-only` (165 node id, порядок совпал с терминальным
выводом) и прогнаны отдельной командой с явным списком node id
(`Invoke-Pytest tests/test_tabs.py::<...> ... tests/test_visibility.py`,
без маркерного фильтра — коллекция дала ровно «collected 15 items», совпало
с ожиданием). Второй сегмент отработал штатно, дошёл до `sessionfinish`,
`PYTEST_EXIT=1` (2 failed, 13 passed, 543.16s). Результаты обоих сегментов
слиты в `framework/allure-results/` (150 + 15 = 165 уникальных, дублей нет —
разные UUID).

**Суммарная длительность**: первый сегмент ~59.7 мин (`bwy8da4vf.output`:
CreationTime 15:09:40 → LastWriteTime последнего allure-результата 16:09:19)
+ второй сегмент 9:03 (543.16s) ≈ 69 мин — укладывается в ожидаемые 60-70 мин.

**recoveries**: второй (завершившийся) сегмент напечатал терминальную строку
`AT-BUG-026 device-liveness guard: recoveries this session = 0/2` — в
frontmatter перенесено `recoveries: "0/2"`. Первый (убитый) сегмент до
`sessionfinish` не дожил и такую строку не печатал вовсе — его recoveries
неизвестны (не «0», а не измерены), причина явно эта: обрыв процесса
харнессом, не приложением. Ни в одном из двух сегментов не было ENV_ISSUE-токена.

## Итог

165 уникальных тестов, **154 passed, 11 failed (broken+failed по Allure), 0
skipped**. Полный сравнительный дословный pytest-хвост второго сегмента (witness):

```
tests\test_tabs.py ......FF.                                             [ 60%]
tests\test_visibility.py ......                                          [100%]
...
FAILED tests/test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged[tab_markers.mitm]
FAILED tests/test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab[tab_markers.mitm]
================== 2 failed, 13 passed in 543.16s (0:09:03) ===================
PYTEST_EXIT=1
```

Первый сегмент (убит харнессом, без итоговой строки) дошёл дословно до:

```
tests\test_downloads.py ......FF.                                        [ 22%]
tests\test_filter_profiles.py FF...                                      [ 25%]
tests\test_infinite_scroll.py FF                                         [ 26%]
...
tests\test_rating_listing.py .....F....F..F..                            [ 55%]
...
tests\test_tabs.py ..
```
(обрыв здесь, без PYTEST_EXIT).

## Падения — факт + артефакты (без вердиктов, триаж — failure-analyst)

| Тест (TC) | Allure-статус | Сообщение (кратко) | Известные ссылки |
|---|---|---|---|
| test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs (TC-043) | broken | `WebDriverException: A new session could not be created ... no such execution context: loader has changed while re...` | `bugs/AT-BUG-047.md` (Open, test_debt на TC-043, найден в RUN-20260803-2012) — **сигнатура В ЭТОМ прогоне другая**, чем зафиксирована в AT-BUG-047 (там `cannot determine loading status from no such window`); дедуп/новизна — за failure-analyst |
| test_filter_profiles.py::test_rename_filter_profile_keeps_query_string (TC-085) | broken | `TimeoutException`: не найден `xpath ('My saved search' → 'Rename3')` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_filter_profiles.py::test_rename_filter_profile_to_duplicate_name (TC-086) | broken | `TimeoutException`: не найден `xpath ('Profile B' → 'Rename3')` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_rating_listing.py::test_add_freeform_tag_persists (TC-090) | broken | `TimeoutException`: не дождался DOM-элемента `li#work_900000002.work.blurb [data-ao3-rate-btn]` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_downloads.py::test_edit_tag_on_already_saved_work_via_panel_does_not_redownload (TC-114) | failed | `AssertionError: download-иконка не появилась у «A Loved Test Work»` | `red_lock: "BUG-014"` в `test-cases/downloads/TC-114.md` (намеренный замок открытого бага, тот же класс, что в RUN-20260803-2012) |
| test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload (TC-115) | failed | то же сообщение, второе место вызова | `red_lock: "BUG-014"` в `test-cases/downloads/TC-115.md` |
| test_infinite_scroll.py::test_infinite_scroll_off_keeps_native_pagination (TC-129) | broken | `TimeoutException`: ожидание replay-запроса не поймано (не долистали список) | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_infinite_scroll.py::test_infinite_scroll_on_loads_next_page_in_background (TC-130) | broken | `TimeoutException`: **идентичное** сообщение TC-129 (тот же шаг ожидания replay-запроса) | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_tabs.py::test_kill_relaunch_without_deep_link_keeps_tabs_unchanged (TC-134) | failed | `AssertionError: позиция 0 вне диапазона: всего вкладок в prefs 0` | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab (TC-135) | broken | `TimeoutError`: маркер `.../works?ao3_tab_marker=1` не появился в `ao3_settings.xml` за 20с | нет red_lock; в RUN-20260803-2012 этот TC был passed |
| test_rating_listing.py::test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos (TC-139) | failed | `AssertionError: data-kudo-clicked неожиданно = 1, ожидали стабильно 0 через 3.0с` | `red_lock: "BUG-015"` в `test-cases/rating/TC-139.md` (намеренный замок открытого бага) |

Артефакты (скриншоты/logcat/page_source) — стандартно приложены фреймворком к
каждому allure-результату в `framework/allure-results/`.

## Дефекты-собратья (D-0043) — доклад

1. **Рецидив «фоновый job убит харнессом ~на часовой отметке»** — см. раздел
   «Находка» выше. Уже задокументирован как дефект-собрат №1 в
   `runs/RUN-20260803-2012.md`; наблюдается второй раз подряд на этом же
   классе прогона (полный `(p0 or p1) and not live`, ~165 тестов, 60-70 мин).
   Не app-дефект — ограничение процесса test-runner'а/харнесса. Для Lead:
   канон 07-19 (foreground `Wait-Process`) фактически НЕ спасает от лимита
   времени жизни самого фонового `run_in_background`-job'а — двух прецедентов
   уже достаточно, чтобы считать лимит систематическим (~60 мин), а не
   единичным сбоем.
2. **TC-129/TC-130 — идентичная сигнатура `TimeoutException` на одном и том же
   шаге** (ожидание replay-запроса), оба теста соседние в одном файле
   (`test_infinite_scroll.py`), оба ранее (RUN-20260803-2012) были зелёными.
   Похоже на класс-кандидат (общий барьер/фикстура файла), но НЕ тотальная
   односигнатурная смерть среды (остальные файлы вокруг зелёные) — fail-fast
   не применён по инструкции координатора. Триаж — за failure-analyst.
3. **TC-085/TC-086 — соседние тесты одного файла (`test_filter_profiles.py`),
   оба упали первыми в файле** (позиции 1-2 из 5), оба искали один и тот же
   элемент `content-desc="Rename3"` по разным xpath-якорям — возможный
   класс-кандидат (общая пред-условная фикстура/состояние), тоже не
   расследовал — не моя роль (test-runner фиксирует факт).
4. **TC-043 (AT-BUG-047) — сигнатура в этом прогоне ИНАЯ**, чем
   задокументированная в открытом `bugs/AT-BUG-047.md` (там `cannot determine
   loading status from no such window`; здесь `A new session could not be
   created ... no such execution context: loader has changed`) — возможно тот
   же класс гонки (WebView/chromedriver), возможно другой; решение о
   дедупе/новом инциденте — за failure-analyst, не беру на себя вердикт.
5. **Сравнение с последним чистым regression-baseline** (`RUN-20260803-2012`,
   160/165 passed): в ЭТОМ прогоне 154/165 — на 6 failed больше, из них 3
   известных красных замка (TC-114/115 → BUG-014, TC-139 → BUG-015, ожидаемо)
   + 8 незамкнутых новых красных (TC-043, TC-085, TC-086, TC-090, TC-129,
   TC-130, TC-134, TC-135), из которых ТОЛЬКО TC-043 имеет открытый
   test_debt-тикет (AT-BUG-047) с ДРУГОЙ сигнатурой. Сборка приложения не
   менялась между прогонами (`state/app-under-test.yaml` не трогался с
   2026-08-03). Голый факт для failure-analyst, вердикт (флейк/деградация
   среды/регресс) не выношу.

## Условия закрытия прогона (Closed)

- [ ] Каждое падение имеет вердикт и связанное действие — не выполнено, статус `NeedsTriage`, ждёт failure-analyst
- [ ] Для APP_BUG существует или создан BUG-файл — TC-114/115/139 уже покрыты (BUG-014/BUG-015), остальные 8 не триажены
- [ ] Карта покрытия (`state/coverage-map.md`) перегенерирована — не выполнялось (шаг снимка за qa-loop)
