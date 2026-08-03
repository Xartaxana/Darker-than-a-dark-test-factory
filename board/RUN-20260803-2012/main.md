---
key: "RUN-20260803-2012"
project: "AO3"
issueType: "run"
status: "run-triaged"
priority: "p2"
summary: "RUN-20260803-2012"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["run"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-03T20:40:00Z"
updated: "2026-08-03T20:40:00Z"
archived: false
resolution: null
---

# RUN-20260803-2012

_Спроецировано из `runs/RUN-20260803-2012.md` (источник правды).
Статус в нашей машине: **Triaged**._

# RUN-20260803-2012 — regression (full baseline) на 1.10 (11)

## Контекст запуска

Triggеr: прямой запрос оператора — regression-замер как предусловие репетиции
тёмного дня (решение владельца №2 опроса 25); `regression_status: not_run` в
`state/app-under-test.yaml` для сборки versionCode 11 / source_commit
`63f6aac3b1ea1dfad82f68b8196aa6cf56f41853`. Фреймворк на коммите `e42eb8bb`.

Эмулятор `ao3_test_api34` (emulator-5554), CA mitmproxy уже стоял (writable-system
буд предыдущей сессии), Appium 3.5.2, APK переустановлен (`Install-App`, Success)
непосредственно перед прогоном.

**suite/selection**: полный regression, `selection.mode: full` — по прямому
указанию оператора, impact-селекция (`scripts/impact_select.py`) намеренно НЕ
запускалась (это ЗАМЕР-baseline, не обычный regression-проход).

**Маркер**: канонический вид regression по `.claude/skills/run-suite/SKILL.md` —
`pytest -m "p0 or p1"`, mode replay. Уточнение по факту прогона (см. «Находка»
ниже): добавлен фильтр `and not live` — `p0 or p1` без него захватывает
canary-тесты с суффиксом `_live` (реальные хиты archiveofourown.org), что
нарушает «AO3 — сторонний сайт, не устраивай нагрузку» для ПОЛНОГО regression
(canary — отдельный минимальный набор, не regression). Итоговая команда:
`pytest -m "(p0 or p1) and not live"` → 165 тестов (313 всего в репозитории,
148 deselected как `p2`/`p3`/unit-без-приоритета, ещё 39 deselected `p0 or p1`,
но `live`-суффикс — итого 165 selected при 119 deselected на первом (широком)
collect и 148 deselected при точном фильтре, см. лог).

## Находка: фоновый прогон убит спустя ~60 минут, несмотря на активный foreground-wait

Первая попытка (`AO3_MODE` присвоение прошло мимо из-за экранирования `$` в
Bash-туле — итог см. ниже) случайно стартовала БЕЗ фильтра `not live` и успела
сделать 9 реальных запросов к archiveofourown.org (canary `_live`-тесты) прежде
чем это было замечено и прогон убит (`Stop-Process`) — задокументировано честно,
не скрыто; масштаб (9 запросов) сопоставим с штатным canary-набором, не
нагрузка. Мёртвые `mitmdump`-процессы (порт 8080) и Appium-node после `Stop-
Process` подчищены (`Stop-NodeProcesses`), протокол устройства проверен
(`Get-Device`) перед перезапуском.

Второй, корректный прогон (`pytest -m "(p0 or p1) and not live"`, `AO3_MODE=
replay`) запущен через `run_in_background`; foreground `Wait-Process -Timeout
500` вызывался повторно (канон 07-19), пока процесс был жив — 7 раундов, ~60
минут суммарно. На последнем раунде системное `task-notification` сообщило
`status: killed` для фонового job'а, а сам процесс pytest (PID 4460) оказался
завершён БЕЗ финальной строки терминальной сводки (лог обрывается на 95%,
`test_cold_start_deep_link_reuses_single_home_tab` без PASSED/FAILED) — то
есть pytest не дожил до `sessionfinish`. Appium тоже оказался мёртв после этого
события. Причина обрыва — не окружение приложения/эмулятора (`Get-Device`
после обрыва подтвердил живое устройство, эмулятор не падал) и не
device-liveness guard (recoveries=0 в обеих ЗАВЕРШИВШИХСЯ последующих сессиях,
см. ниже) — похоже на лимит времени жизни фонового job'а самого харнесса
Bash-тула (~60 мин), не пойманный явно нигде в проекте. **Дефект-собрат для
Lead/оператора (D-0043, класс «долгий фоновый прогон убит харнессом,
несмотря на канон 07-19 foreground-wait»):** канон 07-19 предполагает, что
foreground `Wait-Process` держит job живым сколь угодно долго; на практике для
this-репо полный `p0 or p1` набор (165 тестов, ~60-65 мин суммарного
исполнения) уперся именно в этот лимит. Не расследовал глубже (не моя роль —
факт для Lead/failure-analyst); при следующем regression такого масштаба
стоит закладывать явное разбиение на батчи ЗАРАНЕЕ, а не по факту обрыва.

Восстановление: `allure-results` первого (оборванного) прогона (767
json-файлов, 157 из 165 тестов с результатом) забэкаплены в scratchpad ДО
перезапуска (`--clean-alluredir` иначе стёр бы их). Недостающие 8 тестов
(`test_tabs.py::test_cold_start_deep_link_reuses_single_home_tab`,
`test_library_card_open_work_opens_new_active_browse_tab`, весь
`test_visibility.py`, 6 тестов) догнаны отдельным прогоном в
`--alluredir=allure-results-remainder`, затем результаты слиты в
`framework/allure-results` (167 → после чистки дублей 165 result-файлов, см.
ниже). Побочный эффект диагностики: промежуточный whitespace-баг в моём
собственном grep-фильтре (regex ожидал ровно один пробел перед `[NN%]`, а
pytest выравнивает разным числом пробелов) дал ложный список «9 тестов вообще
не выполнялись» — перепроверено и опровергнуто (все 9 уже были в первом
прогоне, зелёные); лишний 3-й прогон этих 9 тестов (все PASSED, согласованно с
первым прогоном) исключён из итоговых `allure-results`/`tc_results`, чтобы не
дублировать записи.

## Итог

165 уникальных тестов (полный `(p0 or p1) and not live` набор), 160 passed, 5
failed, 0 skipped. Суммарное время исполнения тестов (по timestamp'ам allure,
без учёта простоя между сегментами прогона) ≈ 65 мин (первый сегмент ~59.6
мин до обрыва + второй сегмент 4:52).

## Падения и триаж

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| test_rating_listing.py::test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos (TC-139) | `data-kudo-clicked` неожиданно = 1, ожидали стабильно 0 | **APP_BUG (известный, ожидаемый красный)** | нет — замок `red_lock` открытого бага, новый баг НЕ заводится | **BUG-015** (Open) |
| test_downloads.py::test_edit_tag_on_already_saved_work_via_panel_does_not_redownload (TC-114) | `AssertionError: download-иконка не появилась у «A Loved Test Work»` (карточка переключилась на `Open downloaded`) | **APP_BUG (известный, ожидаемый красный)** | нет — регрессионный замок открытого бага; `red_lock` в кейсе НЕ проставлен (см. собратья, п.4) | **BUG-014** (Open, `test_cases: [TC-114, TC-115]`) |
| test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload (TC-115) | `AssertionError: download-иконка не появилась у «A Loved Test Work»` (карточка переключилась на `Open downloaded`) | **APP_BUG (известный, ожидаемый красный)** | нет — то же, второе место вызова дефектного предиката (`:862`) | **BUG-014** (Open) |
| test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs (TC-043) | `WebDriverException: cannot determine loading status from no such window` (allure: broken, падение за ~3 с на `open_listing`) | **TEST_BUG** | заведён test_debt-долг (класс, 27 call sites) → B4 test-maintainer; `automation_status` оставлен `active` (см. обоснование ниже) | **AT-BUG-047** |
| test_visibility.py::test_display_mode_hide_to_dim_live_push (TC-093) | `AssertionError: секция «Display mode» не найдена прокруткой (Content Visibility)` | **TEST_BUG** | заведён test_debt-долг (класс `swipe_to_text`, 10 call sites) → B4 test-maintainer; `automation_status` оставлен `active` | **AT-BUG-048** |

Вердикты: `APP_BUG` — дефект приложения → bug-reporter; `TEST_BUG` — дефект теста →
test-maintainer; `SITE_CHANGED` — AO3 изменил DOM → test-maintainer;
`APP_CHANGED` — поведение намеренно изменено коммитом приложения;
`ENV_ISSUE` — эмулятор/proxy/сеть; `FLAKY` — нестабильность → карантин.

## Триаж (failure-analyst, 2026-08-03T20:40Z)

Общая сверка, применимая ко всем пяти падениям (evidence-элементы `build_hash`,
`commit_range`):

- Сборка приложения НЕ менялась: `state/app-under-test.yaml` →
  `source_commit 63f6aac3b1ea1dfad82f68b8196aa6cf56f41853` (2026-06-28),
  `version_code 11`, `apk_sha256 6455af0c…`. Позитивная сверка (read-only, код
  приложения не трогался): `git -C app-under-test rev-parse HEAD` →
  `63f6aac3b1ea1dfad82f68b8196aa6cf56f41853` (== `source_commit`),
  `git -C app-under-test log --oneline 63f6aac3…..HEAD` → пустой вывод. Диапазон
  коммитов приложения ПУСТ → вердикт `APP_CHANGED` невозможен ни по одному
  падению (проверено механически, а не «маловероятно»).
- Среда сверена канонической формой (CLAUDE.md, permission-hygiene п.6):
  `. D:\AO3_tests\scripts\tasks.ps1; Get-Device` → `DEVICE: emulator-5554`;
  Appium жив (`GET http://127.0.0.1:4723/status` → `200`). `recoveries: 0/2` —
  device-liveness guard за прогон не срабатывал ни разу, ENV-токена в выводе
  pytest нет. Единственный env-сигнал в stderr всех падений —
  `AT-BUG-043: порт 8080 освободился после 2 попыток bind() за 0.10s (ретрай
  справился)`, то есть штатно отработавшая защита, а не отказ.
- Пересегментация прогона (обрыв фонового job'а) на вердикты не повлияла: TC-043,
  TC-114, TC-115, TC-139 упали в ПЕРВОМ сегменте задолго до обрыва
  (21:03–21:30 по allure), TC-093 — во втором (21:56), соседние по времени тесты
  в обоих сегментах зелёные.

### TC-139 — APP_BUG, известный (BUG-015)

Замок `red_lock: "BUG-015"` в `test-cases/rating/TC-139.md`; баг `bugs/BUG-015.md`
в статусе Open. Сигнатура прогона совпадает с задокументированной в кейсе:
`data-kudo-clicked неожиданно = 1` на `browser_steps.assert_kudo_submit_click_count_holds`
(`test_rating_listing.py:480`) — все предыдущие шаги (листинг, бейдж, bottom-sheet,
добавление тега, закрытие) зелёные, падение на содержательном Then.
**Действия не требуется**: нового бага не заводим, `linked_bug` = BUG-015 стоит в
таблице (правило «Завести баг по APP_BUG» не триггерится — вердикт со ссылкой).

### TC-114 / TC-115 — APP_BUG, известные (BUG-014), ОДИН корень

Гипотеза test-runner'а об общем корне **подтверждена и уточнена**: это не «два
падения одного теста», а два РАЗНЫХ места вызова одного дефектного предиката
(`BrowserViewModel.kt:756` в `savePanelRating` — TC-114; `:862` в `applyRating` —
TC-115), заведённых как единый баг `bugs/BUG-014.md` (`type: app_bug`,
`status: Open`, `test_cases: ["TC-114","TC-115"]`).

Оба теста — **намеренные регрессионные замки**, красные ДО фикса BUG-014; это
записано в самих кейсах (`test-cases/downloads/TC-114.md`, «Регрессионный замок:
ожидаемо КРАСНЫЙ 3/3 прогона подряд»; `TC-115.md`, «Тест ОЖИДАЕМО красный прямо
сейчас — это НЕ дефект фикстуры/теста») и подтверждено ревью F1 обоих кейсов.
Ответ на вопрос диспатча: тесты задуманы КРАСНЫМИ до фикса, а не зелёными.

Доказательства, что сработал именно BUG-014, а не деградация фикстуры:
- сигнатура совпадает с зафиксированной при F1-ревью дословно —
  `steps/library_steps.py:129 AssertionError: download-иконка не появилась у
  «A Loved Test Work»`, падение на ПОСЛЕДНЕМ Then;
- весь Given/When зелёный в обоих (Settings-тумблер, Library-baseline, панель /
  bottom-sheet, сохранение тега / заметки, чип и превью комментария);
- **тот же ассерт прошёл на baseline-шаге ДО When** в обоих тестах (строки
  «Then карточка … показывает download-иконку» со статусом passed выше по
  списку шагов) — предикат не тавтологически ложен;
- page source момента падения несёт `content-desc="Open downloaded"`
  (`d1c3b6f9-…-attachment.xml` для TC-114, `87a80692-…-attachment.xml` для
  TC-115) — карточка переключилась на open-иконку, т.е. файл РЕАЛЬНО скачался
  по правке метаданных уже-Favorite работы. Это и есть наблюдаемая суть BUG-014.

**Действия не требуется**: новых багов не заводим (дедуп с BUG-014).

### TC-043 — TEST_BUG (AT-BUG-047)

`selenium.common.exceptions.WebDriverException: unknown error: cannot determine
loading status from no such window` внутри `browser_steps.open_listing` →
`core/navigate.py:96 driver.get`. Allure-статус broken (падение до первого
содержательного ассерта), длительность 3 с.

- **Артефакты:** скриншот `b650e507-…-attachment.png` — страница AO3 на середине
  загрузки (шапка есть, тело пустое); logcat `c7c45d49-…-attachment.txt`:
  `19:25:49.213 ActivityManager: Start proc …com.android.webview:sandboxed_process0`
  (WebView-процесс ещё стартует) и `19:25:49.653 OpenGLRenderer: Davey!
  duration=3229ms`; ни FATAL, ни ANR, ни crash приложения. Контекст драйвера на
  снимке — `NATIVE_APP`.
- **Причина (в тесте, не в приложении):** `test_rating_listing.py:149-153` делает
  `app_steps.wait_ui_ready(driver)` и СЛЕДУЮЩЕЙ строкой `open_listing(...)`.
  `wait_ui_ready` (`app_steps.py:96-102`) ждёт только присутствия узла
  `android.webkit.WebView`, не дожидаясь оседания стартовой загрузки Home →
  chromedriver теряет цель. **Класс уже диагностирован в этом репозитории**:
  `test-cases/browser/TC-057.md` (ревью 2026-07-17) описывает ту же сигнатуру и
  тот же механизм, фикс там — замена барьера на `wait_app_ready`
  (`BrowserScreen.wait_ao3_loaded`). Тогда починили один тест, класс не прошли —
  сейчас рецидив в другом.
- **Изолированный перезапуск — 3/3 ЗЕЛЁНЫХ** (дословно ниже): падение
  интермиттентное, проявляется под нагрузкой длинного прогона.
- **Почему не ENV_ISSUE:** эмулятор/Appium/прокси в порядке (сверка выше);
  соседние по времени тесты прогона (21:25:11 и 21:26:12) зелёные; отказ — в
  клиенте автоматизации из-за слабого барьера теста, а не в среде.
- **Почему не FLAKY:** причина УСТАНОВЛЕНА по артефактам и прецеденту (конкретные
  строки теста + известный фикс), а не «неизвестная нестабильность». Карантин не
  ставлю намеренно: детерминированной поломки нет (3/3 зелёных), а вывод P1-теста
  из сигнала до починки стоил бы дороже самой гонки. `automation_status: active`
  сохранён; переход `active → needs_maintenance` тоже не применён — его
  формулировка в `schemas/transitions.yaml` («тест сломан детерминированно») не
  описывает этот случай.
- **fix_or_debt:** заведён `bugs/AT-BUG-047.md` (`type: test_debt`,
  `debt_kind: flaky_test`, `test_cases: ["TC-043"]`, `runs: ["RUN-20260803-2012"]`)
  с критерием готовности на КЛАСС (27 call sites) — подхватит правило B4
  «Устранить test debt» (test-maintainer).

### TC-093 — TEST_BUG (AT-BUG-048)

`AssertionError: секция «Display mode» не найдена прокруткой (Content Visibility)`
(`screens/settings_screen.py:188` ← `steps/settings_steps.py:134` ←
`tests/test_visibility.py:157`).

- **Артефакты:** скриншот `9e5cc29b-…-attachment.png` показывает Settings,
  докрученный ДО САМОГО НИЗА (обрезок «Saved AO3 Filters», секции Data и Debug,
  «Clear all ratings»); page source `364d6d6e-…-attachment.xml` содержит только
  тексты нижней части списка.
- **Причина (в фреймворке, не в приложении):** `BaseScreen.swipe_to_text`
  (`base_screen.py:74-87`) делает fling (свайп 400 мс на ~55% высоты) и
  опрашивает наличие текста ОДИН раз между свайпами (`is_present(timeout=1)`);
  список продолжает ехать по инерции, строка успевает войти и выйти из вьюпорта
  между опросами. Итог — 8 свайпов израсходованы, список в конце, `False`.
- **Контроль, что элемент существует и хелпер работоспособен:** в ТОМ ЖЕ прогоне
  за 20 минут до падения TC-092 (`test_dim_mode_dims_hidden_rating_blurb`,
  21:56:02→21:56:28) прошёл ЗЕЛЁНЫМ, используя тот же `tap_display_mode`.
  По коду приложения (read-only) `Text("Display mode")` —
  `SettingsScreen.kt:771` внутри `SectionHeader("Content Visibility")` (`:716`),
  выше секции «Saved AO3 Filters» (`:809`), т.е. на скриншоте её ПРОСКОЧИЛИ.
- **Изолированный перезапуск — 3/3 ЗЕЛЁНЫХ** (дословно ниже).
- **Почему не APP_BUG/APP_CHANGED/SITE_CHANGED:** сборка не менялась (см. выше),
  контрол на месте, TC-092 зелёный на том же контроле; AO3-DOM здесь ни при чём —
  экран нативный (Compose Settings).
- **Почему не FLAKY:** причина установлена (механизм проскока доказан
  скриншотом), назван фикс. Карантин не ставлю по тем же основаниям, что у
  TC-043.
- **fix_or_debt:** заведён `bugs/AT-BUG-048.md` (`type: test_debt`,
  `debt_kind: flaky_test`, `test_cases: ["TC-093"]`) с критерием на КЛАСС
  (`swipe_to_text`/`swipe_up_to_text`, 10 call sites) → B4 test-maintainer.

### Изолированные перезапуски (дословный вывод)

Среда: `. D:\AO3_tests\scripts\tasks.ps1; Get-Device` → `DEVICE: emulator-5554`;
Appium `GET /status` → `200`. Allure-результаты перезапусков писались в
scratchpad (`--alluredir=…\scratchpad\rr093-N` / `rr043-N`), чтобы
`--clean-alluredir` не стёр артефакты прогона.

TC-093, `Invoke-Pytest tests/test_visibility.py -k test_display_mode_hide_to_dim_live_push -v`:

```
1) tests/test_visibility.py::test_display_mode_hide_to_dim_live_push[listing_basic.mitm] PASSED [100%]
   1 passed, 5 deselected in 41.59s   PYTEST_EXIT=0
2) tests/test_visibility.py::test_display_mode_hide_to_dim_live_push[listing_basic.mitm] PASSED [100%]
   1 passed, 5 deselected in 40.83s   PYTEST_EXIT=0
3) tests/test_visibility.py::test_display_mode_hide_to_dim_live_push[listing_basic.mitm] PASSED [100%]
   1 passed, 5 deselected in 39.84s   PYTEST_EXIT=0
```

TC-043, `Invoke-Pytest tests/test_rating_listing.py -k test_comment_only_visible_on_listing_and_absent_from_rating_tabs -v`:

```
1) tests/test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs[listing_basic.mitm] PASSED [100%]
   1 passed, 20 deselected in 57.90s   PYTEST_EXIT=0
2) …_absent_from_rating_tabs[listing_basic.mitm] PASSED [100%]
   1 passed, 20 deselected in 57.48s   PYTEST_EXIT=0
3) …_absent_from_rating_tabs[listing_basic.mitm] PASSED [100%]
   1 passed, 20 deselected in 57.43s   PYTEST_EXIT=0
```

В обоих случаях `recoveries this session = 0/2` — device-liveness guard не
вмешивался ни в один перезапуск.

### Пакет доказательств (C2, `schemas/evidence.yaml`)

Сверено `python scripts/evidence.py` → `вердиктов 6, ошибок 0; APP_BUG:7,
TEST_BUG:3, …`. Все файлы-вложения — в `framework/allure-results/`
(этот прогон; `allure:` в шапке).

**APP_BUG (7 элементов) — TC-139 / TC-114 / TC-115:**

| id | TC-139 | TC-114 | TC-115 |
|---|---|---|---|
| build_hash | `1.10 (11), 6455af0c`, commit `63f6aac3` (сверка выше) | то же | то же |
| test_case | TC-139 (`test_rating_listing.py::test_edit_tag_on_already_kudosed_work_via_listing_does_not_reclick_kudos`) | TC-114 (`test_downloads.py::test_edit_tag_on_already_saved_work_via_panel_does_not_redownload`) | TC-115 (`test_downloads.py::test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`) |
| steps | GWT кейса `test-cases/rating/TC-139.md` + список allure-шагов прогона (все до последнего Then — passed) | GWT `test-cases/downloads/TC-114.md` + allure-шаги | GWT `test-cases/downloads/TC-115.md` + allure-шаги |
| screenshot | `d31ec8c4-3223-4d14-ac63-5dcab009203c-attachment.png` | `6ef4d561-2d88-4dfa-b6c9-944f4c08eaf8-attachment.png` | `65b6f952-c9f2-44ef-bbb0-b7c3cc9ce972-attachment.png` |
| logcat | `7e965d7b-e061-40de-94f1-a9f683bb1498-attachment.txt` | `bb079f3f-626d-4dc2-872b-84831aa68af7-attachment.txt` | `06622f6c-8426-414c-ad54-9551f56d9553-attachment.txt` |
| page_source | `e28a4a02-9b6d-4c22-b5ad-a2d2c83fa52f-attachment.xml` | `d1c3b6f9-8f6f-47b1-92b1-2011ef4dd5b9-attachment.xml` (несёт `content-desc="Open downloaded"`) | `87a80692-500e-465b-bc71-16150c4f46b7-attachment.xml` (то же) |
| expected_actual | ожидалось `data-kudo-clicked` = 0 стабильно 3 с (правка тега не шлёт kudos повторно) — фактически 1 | ожидалось: карточка сохраняет download-иконку, файл не появляется — фактически карточка стала `Open downloaded` (файл скачан) | то же, вход через bottom-sheet листинга |

**TEST_BUG (3 элемента) — TC-043 / TC-093:**

| id | TC-043 | TC-093 |
|---|---|---|
| failing_test | `test_rating_listing.py::test_comment_only_visible_on_listing_and_absent_from_rating_tabs`, `@allure.id("TC-043")`, result `d2e400a6-…-result.json` | `test_visibility.py::test_display_mode_hide_to_dim_live_push`, `@allure.id("TC-093")`, result `868d60dc-…-result.json` |
| root_cause | барьер `app_steps.wait_ui_ready` (`app_steps.py:96-102`) слабее, чем требует следующий шаг `open_listing` → гонка стартовой загрузки Home; приложение живо (logcat без FATAL/ANR), сборка не менялась | `BaseScreen.swipe_to_text` (`base_screen.py:74-87`): fling-инерция + одиночный опрос между свайпами → секция проскочена (скриншот: список докручен до конца); контрол на месте (`SettingsScreen.kt:771`), TC-092 зелёный на нём же в этом прогоне |
| fix_or_debt | `bugs/AT-BUG-047.md` (`test_debt`/`flaky_test`, критерий на класс — 27 call sites) | `bugs/AT-BUG-048.md` (`test_debt`/`flaky_test`, критерий на класс — `swipe_to_text`/`swipe_up_to_text`, 10 call sites) |

Вердикт `FLAKY` не использован ни разу — соответственно элемент
`quarantine_decision` не требуется, карантин не оформлялся и
`automation_status` кейсов не менялся (обоснование — в разборе TC-043/TC-093).

### Наблюдения test-runner (оставлены как есть, подтверждены триажем)

**Известный ожидаемый красный (TC-139, red_lock=BUG-015):** сверено с
`test-cases/rating/TC-139.md` — единственный `red_lock` во всём
`test-cases/` (проверено grep'ом по всем файлам). Кейс намеренно НЕ исключён
из автоматизации/прогона (`automated_by` заполнен, тест реально существует и
маркирован `p1`/`replay` — коллекция и прогон его подхватывают штатно);
«исключён из F1» относится к статусу кейса (`status: Approved`,
`automation_status: ""` — НЕ `Automated`/`active`, F1-гейт test-reviewer не
пройден), а не к присутствию в pytest-наборе. Красный результат этого узла —
ожидаемый факт, зафиксированный самим кейсом, не новый дефект.

**TC-114/TC-115 — возможный класс-собрат (D-0043, не расследовано, только
замечено):** оба падения — «download-иконка не появилась» на одной и той же
работе («A Loved Test Work»), оба в области downloads, оба edge-vs-level
кейсы соседние с TC-139 по структуре (правка тега/комментария уже-Favorite/
Kudosed работы). Возможно один корневой дефект на два узла — решение о связи
за failure-analyst.
> **Подтверждено триажем:** корень действительно один (BUG-014), но это два
> РАЗНЫХ места вызова одного предиката (`:756` и `:862`), оба уже связаны с
> BUG-014 полем `test_cases`. Красные ожидаемо.

**TC-043 — иной класс (broken, не failed):** `selenium.common.exceptions.
WebDriverException` — «no such window» — по фактуре похоже на потерю
WebView-контекста/сессии, а не на assertion-несовпадение с приложением;
возможный ENV_ISSUE/инфраструктурный флейк, а не APP_BUG — решение тоже за
failure-analyst.
> **Уточнено триажем:** не ENV — гонка барьера в самом тесте
> (`wait_ui_ready` → немедленная WebView-навигация), известный класс TC-057.
> Вердикт TEST_BUG, `bugs/AT-BUG-047.md`.

## Дефекты-собратья (D-0043) — доклад

Пункты 1-3 — доклад test-runner (оставлены дословно), 4-6 добавил
failure-analyst при триаже.

1. **Долгий фоновый job убит харнессом Bash-тула ~на часовой отметке** несмотря
   на активный foreground `Wait-Process`-цикл по канону 07-19 (подробности
   выше, раздел «Находка»). Не app-дефект — дефект/ограничение процесса
   test-runner'а самого конвейера; стоит явной строкой для Lead: канон 07-19
   может нуждаться в уточнении «для прогонов длиннее ~55 мин — заранее делить
   на батчи», а не полагаться только на foreground-wait.
2. **`$env:` присвоение через Bash-тул ломается двойными кавычками** — `"..."`
   как внешняя обёртка `-Command` заставляет bash разворачивать `$env:...` до
   того, как строка попадёт в powershell (пример из этого прогона: `AO3_MODE`
   тихо не установился, привело к находке live-хитов выше). Рабочая форма —
   одинарные кавычки вокруг ВСЕГО `-Command`-аргумента. Не зафиксировано нигде
   в `CLAUDE.md`/permission-hygiene — возможный кандидат на явную строку в
   разделе «Дисциплина команд», решение за Lead.
3. **TC-114/TC-115 возможный общий корень** — см. таблицу падений выше.
4. **Конвенция `red_lock` проведена не по всем намеренно-красным замкам
   (класс, решение Lead 2026-08-03).** `red_lock` стоит ТОЛЬКО у TC-139
   (`BUG-015`), тогда как TC-114 и TC-115 — ровно такие же намеренные замки
   открытого бага (BUG-014), что записано прозой в их теле и в ревью F1, но НЕ
   машинным полем. Цена уже реализовалась в этом прогоне: два ожидаемо-красных
   узла каждый раз приходят в триаж как «неожиданные падения» и требуют ручного
   дедупа (это же предсказал test-reviewer в TC-115: «потребует дедупа
   failure-analyst/bug-reporter вручную»). Дополнительно и BUG-014, и BUG-015
   несут `known_issue: "false"` при том, что оба заведомо известны, приняты
   до фикса и уже держат намеренно-красные замки — по D14 это кандидаты на
   `known_issue: "true"` (влияет на дедуп APP_BUG и на still-repro D3);
   решение — Lead/владелец, не триаж. Кандидаты на правку — по одному полю в
   `test-cases/downloads/TC-114.md`, `TC-115.md` (+ решение по `known_issue`
   D14). Сам не правлю: `red_lock` — гейтовое поле F1 (`state/rules.yaml:107`,
   `schemas/test-case.schema.yaml:53`), владение Lead/test-maintainer, не
   failure-analyst.
5. **Класс «замок гоняется общим маркером».** Вопрос диспатча «вытаскивать ли
   TC-139 из regression-выборки» — решение Lead; фактура для него: замки
   намеренно `@pytest.mark.p1`/`replay` и подхватываются любым `p0 or p1`
   набором. Вывод замков из regression дал бы «чистый» красный/зелёный сигнал
   прогона, но потерял бы автоматическое обнаружение момента, когда баг
   починили (замок позеленел). Альтернатива без потери сигнала — отдельный
   маркер (`@pytest.mark.red_lock`) + агрегирование замков отдельной строкой
   отчёта; тогда `red_lock`-поле кейса и маркер теста становятся парой, а
   триаж перестаёт разбирать их поимённо. Механизменное решение — Lead.
6. **Класс «ожидание слабее, чем требует следующий шаг» — два независимых
   экземпляра в одном прогоне** (AT-BUG-047: барьер перед WebView-навигацией,
   27 call sites; AT-BUG-048: `swipe_to_text` под инерцией, 10 call sites).
   Общего кода нет, фиксы независимы, но класс один и он рецидивирующий
   (AT-BUG-047 — уже второй заход после TC-057, где починили экземпляр, а не
   класс). Для Lead: кандидат в правило приёмки автотестов — «барьер/ожидание
   в шаге обязан покрывать ВСЕ асинхронные эффекты, которые использует
   следующий шаг», с проверкой при F1 (test-reviewer, п.5 flake-риск).

## Условия закрытия прогона (Closed)

- [x] Каждое падение имеет вердикт и связанное действие (баг / фикс теста / карантин) — 5/5, см. таблицу и раздел «Триаж»
- [x] Для APP_BUG существует или создан BUG-файл — TC-139 → BUG-015 (Open), TC-114/TC-115 → BUG-014 (Open); новых багов приложения прогон не дал
- [ ] Карта покрытия (`state/coverage-map.md`) перегенерирована (`scripts/coverage_map.py`) — не выполнялось; триаж статусов кейсов не менял (карантин не ставился), но шаг снимка за прогон остаётся за qa-loop

**Статус:** `NeedsTriage → Triaged` (переход failure-analyst, `schemas/transitions.yaml`).
Дальнейшая работа маршрутизирована НЕ через этот прогон, а через долги
`AT-BUG-047`/`AT-BUG-048` (правило B4 «Устранить test debt»); правило «Починить
тест по TEST_BUG» на этом прогоне холостое — resolution по обоим падениям
проставлен. Переход `Triaged → Closed` — за qa-loop/bug-reporter/test-maintainer
(failure-analyst этого перехода в матрице не имеет).
