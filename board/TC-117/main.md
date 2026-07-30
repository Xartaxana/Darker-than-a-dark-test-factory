---
key: "TC-117"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p2"
summary: "Снятие рейтинга Favorite (deselect) не запускает скачивание"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-30T17:06:44Z"
updated: "2026-07-30T17:06:44Z"
archived: false
resolution: "done"
---

# Снятие рейтинга Favorite (deselect) не запускает скачивание

_Спроецировано из `test-cases/downloads/TC-117.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-117 — Снятие рейтинга Favorite повторным тапом не скачивает файл

## Предусловия
- Работа W засеяна с рейтингом SAVE (Favorite), `downloadPath=null`; тумблер
  Auto-download включён.
- Открыта страница работы W `/works/{id}`, панель показывает Favorite выбранным.

## Сценарий (Given-When-Then)

**Given** работа W имеет рейтинг Favorite; тумблер Auto-download включён; панель
показывает Favorite выбранным

**When** пользователь повторно нажимает уже выбранную кнопку «Favorite» на панели
(deselect — `rating-deselect-on-tap`)

**Then** рейтинг снят — работа W исчезает из вкладки FAVORITE экрана Library (при
отсутствии комментария/тегов/файла строка удаляется целиком, `RatingRepository.
removeRating`)
**And** скачивание НЕ запускается ни на каком этапе — в download-директории
приложения не появляется ни одного нового файла (`download_oracle`, без
`@pytest.mark.produces_download`)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | rating=SAVE → null (deselect), downloadPath=null |
| Тумблер Auto-download | ON |

## Заметки для автоматизации
- **Replay ОБЯЗАТЕЛЕН, вопреки первому впечатлению «ветка не содержит вызова —
  сети нет»** (класс найден и исправлен на TC-112/TC-113 того же файла,
  2026-07-29): сценарий сам по себе действительно не делает сетевого вызова
  (ветка `rating == null`, строки 691-737, структурно не содержит вызова
  `downloadWork`) — но негативный Then проверяет ОТСУТСТВИЕ эффекта
  ГИПОТЕТИЧЕСКОГО бага (например, деселект ошибочно попадает в ветку
  `existing != null` вместо `rating == null` из-за неверного порядка
  присваивания/чтения `existing`, и предикат `:756` срабатывает на устаревшем
  SAVE), а не отсутствие штатного поведения. Если бы такой баг существовал,
  гипотетическое нелегитимное скачивание с live-навигацией ушло бы на
  archiveofourown.org по синтетическому `ao3_id` работы W, который отдаёт
  живой HTTP 404 — `DownloadRepository` проглатывает `IOException`, и
  негативный Then остался бы истинным НЕЗАВИСИМО от того, сработал баг или
  нет: тест физически не может упасть на собственной регрессии
  (ложно-зелёный). `work_with_download.mitm` (та же запись, что
  TC-112/113/114/115) несёт РЕАЛЬНУЮ download-транзакцию — с этой записью
  гипотетическое срабатывание завершилось бы настоящим файлом, и
  `download_oracle`/UI-ассерты поймали бы его по-настоящему.
- Отличать от TC-116 (смена рейтинга на ДРУГОЙ, не null) — разные код-ветки
  (`rating != null` vs `rating == null` в `savePanelRating`), оба входа группы 4
  §9 обязаны быть покрыты по отдельности (один сценарий — один кейс).
- Шаги (исправлено 2026-07-28, critic-вход — прежняя версия ошибочно требовала ДВА
  тапа): работа W засеяна напрямую с rating=SAVE (см. Предусловия, НЕ через UI) —
  панель `RatingMenu` уже показывает Favorite выбранным при открытии страницы.
  Единственный вызов `rating_steps.rate_current_work(driver, "SAVE")` по уже
  выбранной кнопке — это и есть деселект (`rating-deselect-on-tap`, общий toggle
  `RatingOverlay.kt`/`RatingMenu`, тот же механизм, что и для group 3/панели —
  тап по УЖЕ выбранному рейтингу снимает его, а не переотправляет тот же SAVE).
  ВТОРОЙ тап здесь НЕДОПУСТИМ: он снова выбрал бы SAVE на уже удалённой строке
  (`existing == null` после деселекта) → путь `pendingPanelSave`/`:1057` → реальное
  скачивание при тумблере ON — прямо противоположно заявленному Then. Приём
  идентичен TC-008 (`framework/tests/test_rating.py:73`, фикстура
  `loved_work_seeded` — `conftest.py:75-83`: `clean_state()` +
  `seed_library([(W.LOVED, "SAVE")])`, работа УЖЕ предзаполнена SAVE ДО старта
  сессии Appium): единственный тап по уже выбранной кнопке и есть деселект;
  фикстура `loved_work_seeded` переиспользуется без изменений.
- **Батарея правил-реакций:** закрывает вторую половину группы 4 §9 («снятие
  рейтинга не скачивает»); первая половина — TC-116.

## Ревью автотеста (F1, test-reviewer, 2026-07-30) — PASS

- **Архитектура (C1):** `python scripts/arch_check.py` → «ошибок 0, предупреждений
  0»; `ALLOWLIST` в `scripts/arch_check.py` пуст (исключения «под себя» не
  заводились). В теле теста нет ни локаторов/`find_element`, ни драйверных
  вызовов напрямую — вся работа через `framework/steps/*`; `sleep` отсутствует.
- **Traceability:** `@allure.id("TC-117")` == id кейса; `@pytest.mark.p2`
  соответствует `priority: P2`; `@pytest.mark.replay` соответствует фактическому
  использованию `replay`-фикстуры. `automated_by` указывает на существующую
  функцию `test_downloads.py::test_deselecting_favorite_rating_does_not_download`.
  `features: [background-auto-download-trigger]` есть в
  `docs/feature-registry.yaml`. Ветка требования сверена по исходнику:
  `BrowserViewModel.kt:691` — `if (rating == null)`, внутри неё ветка `else ->
  repo.removeRating(workId)` (:730); вызова `downloadWork` в этом блоке (691-737)
  структурно нет, что и заявлено в `requirements`.
- **Соответствие кейсу по смыслу:** When реализован ОДНИМ вызовом
  `rating_steps.rate_current_work(driver, "SAVE")` по уже выбранной сидингом
  кнопке — ровно тот деселект, что описан в заметках; наивной версии с двумя
  тапами нет. Then проверяет суть, а не «элемент существует»:
  `assert_work_not_in_tab(driver, "SAVE", ...)` (рейтинг реально снят, строка
  ушла из FAVORITE) + `assert_work_not_in_files_tab` + autouse-оракул
  `download_oracle` без `@pytest.mark.produces_download` (любой новый файл в
  download-директории = провал). Given несёт baseline
  (`assert_auto_download_enabled(driver, True)` + download-иконка), без которого
  негативный Then был бы тавтологичен.
- **Replay-запись:** `rb.WORK_WITH_DOWNLOAD_FILENAME` подключена, как требуют
  заметки (класс ложно-зелёного, найденный на TC-112/113). Красная проба ниже
  ПОДТВЕРДИЛА это эмпирически: при срабатывании download-пути через эту запись
  файл реально появляется на устройстве и ловится оракулом.
- **Фикстуры и данные:** `loved_work_seeded` (`conftest.py:211-220`) —
  `clean_state()` + `seed_library([(W.LOVED, "SAVE")])`, переиспользуется без
  изменений. Порядок аргументов `(replay, loved_work_seeded, driver)` соблюдает
  контракт: сидинг выполняется ДО создания Appium-сессии. Тест владеет своими
  данными и не зависит от порядка (проверено отдельным одиночным `-k`-прогоном).
- **Flake-риск:** `wait_app_ready` (не `wait_ui_ready`) перед навигацией по
  Settings — та же закрытая гонка, что в TC-032/114/115/116; панель RatingMenu
  раскрывается через `BottomNav.ensure_visible()` (`AnimatedVisibility` учтён);
  явных `sleep` нет, ожидания — в `core/waits`/шагах. Живого AO3 в сценарии нет.
- **Независимое воспроизведение (п.6):** `Get-Device` → `DEVICE: emulator-5554`.
  `Invoke-Pytest tests/test_downloads.py -k
  test_deselecting_favorite_rating_does_not_download -v` → `1 passed, 13
  deselected in 63.95s`, `PYTEST_EXIT=0`. Ни одного
  `ReadTimeoutError`/`TimeoutError`; `device-liveness guard recoveries = 0/2`.
- **Красная проба (п.7):** порча — ВТОРОЙ тап `rate_current_work(driver,
  "SAVE")`, добавленный сразу за первым (ровно то, что заметки кейса объявляют
  недопустимым; временная правка шага теста). Прогон той же командой →
  `1 failed`, `PYTEST_EXIT=1`, падение на содержательном ассерте Then:
  `tests\test_downloads.py:567` → `steps\library_steps.py:49` `AssertionError:
  работа «A Loved Test Work» неожиданно присутствует во вкладке FAVORITE`; плюс
  `download_oracle` независимо зафиксировал реально скачанный файл
  `/sdcard/Android/data/com.example.ao3_wrapper/files/ao3_downloads/ao3_A Loved
  Test Work_900000001.html` (WARN, а не второй fail — тест уже упал раньше, M2
  conftest). Порча откачена в том же ходе: `git checkout --
  framework/tests/test_downloads.py`, файл отсутствует в `git status`;
  подтверждающий повторный прогон после отката → `1 passed in 60.53s`,
  `PYTEST_EXIT=0`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
