---
key: "TC-114"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Правка личного тега уже-Favorite работы через панель работы не скачивает файл повторно (edge vs level, :756)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-29T19:19:08Z"
updated: "2026-07-29T19:19:08Z"
archived: false
resolution: "done"
---

# Правка личного тега уже-Favorite работы через панель работы не скачивает файл повторно (edge vs level, :756)

_Спроецировано из `test-cases/downloads/TC-114.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-114 — Панель: правка тега уже-Favorite работы не запускает повторное скачивание

## Предусловия
- Работа W засеяна НАПРЯМУЮ в Room (не через UI, не через панель) с рейтингом SAVE
  (Favorite) и `downloadPath=null` — «работа уже была отмечена Favorite ДО этого
  визита» (`app_steps.seed_library([(W.LOVED, "SAVE")])`), полные title/author/
  fandom/wordCount заполнены сидингом.
- Тумблер «Auto-download favorite works» включён.
- Активен replay-режим `work_with_download.mitm` (`rb.WORK_WITH_DOWNLOAD_FILENAME`,
  та же запись, что TC-032/033 — несёт ОБЕ HTTP-транзакции: work-страница + `.html`
  для `W.LOVED`) — нужен, чтобы при срабатывании дефекта нелегитимное скачивание
  РЕАЛЬНО завершилось файлом (иначе `server_replay_extra=forward` уводит
  незаписанный OkHttp-запрос на живой archiveofourown.org, где синтетический
  `ao3_id` не существует — незавершённая попытка осталась бы незамеченной, и
  негативный Then был бы ложно-зелёным независимо от наличия бага).
- Открыта страница работы W `/works/{id}` (та же запись покрывает и WebView-навигацию,
  и фоновый OkHttp-вызов `DownloadRepository`, см. докстринг `test_downloads.py`),
  панель `RatingMenu` раскрыта и уже показывает Favorite выбранным (рейтинг прочитан
  из Room при загрузке страницы).

## Сценарий (Given-When-Then)

**Given** работа W уже имеет рейтинг Favorite (SAVE), файл ещё не скачан; тумблер
Auto-download включён; панель на странице работы W показывает Favorite выбранным

**When** пользователь раскрывает раздел тегов панели и добавляет личный тег
«re-save-probe» (правка метаданных, рейтинг НЕ меняется — остаётся Favorite)

**Then** тег «re-save-probe» сохраняется среди выбранных (наблюдаемая суть операции)
**And** повторное скачивание НЕ запускается — карточка работы W на вкладке FAVORITE
Library по-прежнему показывает download-иконку (не open-иконку), `downloadPath`
остаётся пустым
**And** в download-директории приложения не появляется ни одного нового файла —
`download_oracle` не фиксирует скачивание (тест без `@pytest.mark.produces_download`;
при наличии бага BUG-014 replay РЕАЛЬНО создаст файл — тест закономерно КРАСНЫЙ до
фикса, это и есть регрессионный замок класса)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | `W.LOVED`, засеяна напрямую с rating=SAVE, downloadPath=null |
| Добавляемый тег | «re-save-probe» |
| Тумблер Auto-download | ON |
| Replay | `rb.WORK_WITH_DOWNLOAD_FILENAME` (`work_with_download.mitm`) |

## Заметки для автоматизации
- Точка кода: `BrowserViewModel.kt:756-758` внутри `savePanelRating`, ветка
  `existing != null` (строка ~743) — предпосылка «строка в Room уже есть» выполнена
  сидингом, а не первым переходом (в отличие от TC-032, который идёт через
  `pendingPanelSave`/:1057, см. заметку ниже).
- Панель `RatingMenu` — ОБЩИЙ composable для встроенной панели work-page и bottom-sheet
  листинга (`app-under-test/CLAUDE.md`, `RatingOverlay.kt:70-73`); методы
  `framework/screens/rating_overlay.py` (`toggle_tags`/`enter_tag_input`/
  `confirm_tag_input`), уже используемые для листинга в TC-090, применимы к панельному
  контексту напрямую — нужна только обёртка-степ по образцу `rating_steps.
  rate_current_work` (`BottomNav(driver).ensure_visible()` перед использованием
  `RatingOverlay(driver)`), рутинная автоматизация, не блокер.
- Позитивная граница ЭТОГО ЖЕ правила-реакции (первый переход на SAVE, когда строки
  в Room ещё не было — :1057, `onRateWorkRequested`/`pendingPanelSave`) уже покрыта
  TC-032 (Automated) — отдельного нового кейса не требуется, см. правку
  docs/01-test-strategy.md §9.
- **Батарея правил-реакций:**
  - edge vs level — это и есть предмет кейса (место вызова #1 из 3, :756).
  - идемпотентность — н-п отдельным сценарием: негативный Then этого кейса УЖЕ
    доказывает, что повторное сохранение (после гипотетического легитимного
    перехода) не плодит второй файл — это и есть идемпотентность эффекта на этом
    правиле-реакции, отдельного сценария «нажать дважды» не требуется.
  - propagation — н-п: скачивание пишет файл+`downloadPath` ОДНОЙ работы, у эффекта
    нет множественных потребителей вкладок (в отличие от badge/kudos-broadcast,
    уже покрытого `bridge-badge-sync-multi`); других consumers нет.
- Известная СИБЛИНГ-находка (не в скоупе этого кейса, докладываю по D-0043): та же
  ветка `applyRating` (:862, см. TC-115) и panelSave-ветка (:1057) ТАКЖЕ авто-кликают
  AO3 kudos-кнопку при LIKE/SAVE (`BrowserViewModel.kt:859`/`1054`) — это отдельный
  открытый дефект BUG-015 (level-предикат на kudos), явно исключён из скоупа этой
  области per NON-GOALS диспатча; не путать assert'ы.
- **Тест написан и подключён** (2026-07-29, test-automator):
  `framework/tests/test_downloads.py::
  test_edit_tag_on_already_saved_work_via_panel_does_not_redownload`
  (`rating_steps.add_tag_via_panel`, новый шаг — обёртка по образцу
  `rate_current_work`, `BottomNav(driver).ensure_visible()` перед раскрытием
  раздела тегов панели). `automated_by` заполнен; ждёт штатного F1-ревью.
  **Регрессионный замок: ожидаемо КРАСНЫЙ 3/3 прогона подряд**, одна и та же
  сигнатура каждый раз — `download_oracle` (autouse, conftest.py) фиксирует
  незапрошенный файл `.../ao3_downloads/ao3_A Loved Test Work_900000001.html`
  (UserWarning «класс BUG-014»), последний Then (`library_steps.
  assert_download_icon_shown`) падает на той же строке, потому что карточка
  переключилась на open-иконку — файл реально скачался. Не setup/инфраструктурная
  ошибка: весь Given/When (Settings-тумблер, панель, добавление тега, baseline
  download-иконки) проходит каждый раз одинаково. Команда прогона:
  `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1;
  Invoke-Pytest tests/test_downloads.py -k
  test_edit_tag_on_already_saved_work_via_panel_does_not_redownload -v"` →
  `1 failed, 11 deselected` / `PYTEST_EXIT=1` все три раза. Снимется сам при
  фиксе `bugs/BUG-014.md` в `app-under-test/`, без правки теста.

## Ревью автотеста

**2026-07-29T19:19:08Z — test-reviewer, F1 ПРОЙДЕН (ветка «регрессионный замок»,
решение Lead 2026-07-29; прецедент того же класса — TC-115 на тот же BUG-014).**
Статус `Approved → Automated`, `automation_status: active`: красный active-тест в
прогонах и есть смысл замка — снимется сам фиксом `bugs/BUG-014.md`, без правки
теста.

- **п.1 архитектура (C1):** `python scripts/arch_check.py` → «ошибок 0,
  предупреждений 0»; ALLOWLIST в `scripts/arch_check.py:80` пуст (исключение «под
  себя» не заводилось). Локаторы — в `framework/screens/rating_overlay.py`,
  шаги — в `framework/steps/` (новый `rating_steps.add_tag_via_panel:36`),
  `time.sleep` в задействованных модулях нет.
- **п.2 traceability:** `@allure.id("TC-114")` == id кейса; `@pytest.mark.p1` ==
  `priority: P1`; `@pytest.mark.replay` соответствует заявленному replay-режиму;
  `automated_by` резолвится (тест собран и исполнен: `1 selected`).
- **п.3 соответствие GWT:** Then кейса покрыт по сути, а не «элемент существует»:
  сохранение тега — `rating_steps.assert_chip_visible`; отсутствие повторного
  скачивания — `library_steps.assert_download_icon_shown` (карточка не должна
  переключиться на open-иконку) + независимый autouse `download_oracle` без
  `@pytest.mark.produces_download` (ожидание 0 новых файлов). Ассерт НЕ ослаблен
  под «стать зелёным» — маскировки открытого бага нет; ссылка на `bugs/BUG-014.md`
  стоит в `requirements` и в теле кейса.
- **п.4 фикстуры/данные:** порядок в сигнатуре `(replay, loved_work_seeded,
  driver)` — сидинг (`clean_state` + `seed_library([(W.LOVED,"SAVE")])`) строго ДО
  создания Appium-сессии; тест владеет своими данными и не зависит от порядка;
  teardown `replay` возвращает прокси и глушит mitmdump независимо от исхода.
- **п.5 flake-риск:** ожидания явные (`is_present/find` с таймаутами, без sleep);
  гонка `AnimatedVisibility` нижней навигации снята `BottomNav.ensure_visible()`
  внутри `add_tag_via_panel`; живой AO3 не используется — весь трафик идёт через
  `work_with_download.mitm` (обе транзакции: work-страница + `.html`).
- **п.6 (замена — воспроизведение ФАКТИЧЕСКОГО поведения):** собственный прогон
  ревьюера, `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1;
  Invoke-Pytest tests/test_downloads.py -k
  test_edit_tag_on_already_saved_work_via_panel_does_not_redownload -v"` →
  `1 failed, 11 deselected, 1 warning in 60.95s`, `PYTEST_EXIT=1`, устройство
  `emulator-5554` (`Get-Device` → `DEVICE: emulator-5554`). Падение — на
  СОДЕРЖАТЕЛЬНОМ ассерте Then, не в setup: `tests/test_downloads.py:386` →
  `steps/library_steps.py:129 AssertionError: download-иконка не появилась у «A Loved
  Test Work»`, плюс `UserWarning download_oracle: незапрошенное скачивание — класс
  BUG-014 ... ao3_downloads/ao3_A Loved Test Work_900000001.html`. Механизм совпадает
  с заявленным `BUG-014`: строка в Room засеяна, значит `savePanelRating` идёт веткой
  `existing != null` (`BrowserViewModel.kt:743-758`) и упирается в level-предикат
  `:756` — путь `pendingPanelSave`/`:1057` при существующей строке недостижим (сверено
  по коду read-only).
- **п.7 (замена — обратная полярность):** (а) БЕЗ порчи, в том же красном прогоне
  ТОТ ЖЕ ассерт `library_steps.assert_download_icon_shown(driver, work.title)`
  прошёл на baseline-шаге ДО When (`test_downloads.py:364`) — предикат не
  тавтологически ложен. (б) Дополнительная проба ДИСКРИМИНИРУЮЩЕЙ силы (сильнее
  baseline: baseline снимается до открытия work-страницы и сам по себе не отделяет
  «скачало по правке тега» от «скачало по заходу на страницу»): временно заменён
  шаг `settings_steps.enable_auto_download(driver)` на
  `settings_steps.assert_auto_download_enabled(driver, False)`
  (`test_downloads.py:361`) — то есть изменено только состояние приложения
  (тумблер Auto-download OFF), сценарий не тронут. Той же командой прогон →
  `1 passed, 11 deselected in 49.21s`, `PYTEST_EXIT=0`, оракул не зафиксировал ни
  одного нового файла. Полярность перевернулась на изменении ровно того конъюнкта
  `autoDownloadSaved`, который входит в дефектный предикат `:756`: RED порождается
  реакцией авто-скачивания на сохранение метаданных, а не инфраструктурой, replay,
  сидингом или навигацией на work-страницу. Порча откачена тем же ходом:
  `git checkout -- framework/tests/test_downloads.py`, `git status --porcelain` по
  `framework/` чист.
- **Собратья (D-0043), в скоуп ревью не берутся:** экземпляр уже
  зарегистрированного класса «When идемпотентного сеттера ничем не подтверждён»
  (`docs/HANDOFF.md` §5а) присутствует и здесь — `test_downloads.py:361`
  (`enable_auto_download` без парного `assert_auto_download_enabled(driver, True)`)
  и в Given не подтверждён явным ассертом факт «панель уже показывает Favorite
  выбранным». Сегодня живой проблемы нет (RED доказывает оба условия
  транзитивно — скачивание невозможно ни при выключенном тумблере, ни при
  `rating == null`), но ПОСЛЕ фикса BUG-014 тест станет зелёным и оба
  подтверждения понадобятся, иначе регрессия в предзагрузке рейтинга панели даст
  вакуумно-зелёный. Не блокер F1: класс уже в очереди Lead с TC-114 в списке
  экземпляров, и TC-115 принят в тот же статус с тем же гэпом — чинить его здесь
  значило бы править тестовый код ревьюером.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область содержит правило-реакцию — батарея адресована по каждому пункту
      (edge-vs-level — предмет кейса; идемпотентность/propagation — «н-п» с
      обоснованием выше)
