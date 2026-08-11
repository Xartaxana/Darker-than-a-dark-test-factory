---
key: "TC-115"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Правка комментария уже-Favorite работы через bottom-sheet листинга не скачивает файл повторно (edge vs level, onRatingTransition:788)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-29T10:07:53Z"
updated: "2026-07-29T10:07:53Z"
archived: false
resolution: "done"
---

# Правка комментария уже-Favorite работы через bottom-sheet листинга не скачивает файл повторно (edge vs level, onRatingTransition:788)

_Спроецировано из `test-cases/downloads/TC-115.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-115 — Bottom-sheet листинга: правка заметки уже-Favorite работы не запускает повторное скачивание

## Предусловия
- Работа W уже имеет рейтинг Favorite (SAVE), файл ещё не скачан, тумблер
  Auto-download включён.
- Открыта листинговая страница с блёрбом работы W, Rate-кнопкой открыт нативный
  bottom-sheet (`RatingOverlay`), рейтинг Favorite уже показан выбранным.

## Сценарий (Given-When-Then)

**Given** работа W (уже Favorite, не скачана) открыта на листинге; тумблер
Auto-download включён; bottom-sheet рейтинга открыт Rate-кнопкой работы W, Favorite
выбран

**When** пользователь раскрывает поле комментария, вводит текст «re-save-note» и
нажимает «Save note» (правка метаданных, рейтинг НЕ меняется — остаётся Favorite)

**Then** комментарий «re-save-note» сохраняется (наблюдаемая суть операции)
**And** повторное скачивание НЕ запускается — карточка работы W по-прежнему
показывает download-иконку (не open-иконку) в Library, `downloadPath` остаётся
пустым
**And** в download-директории приложения не появляется ни одного нового файла —
`download_oracle` не фиксирует скачивание (без `@pytest.mark.produces_download`)

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | работа с rating=SAVE, downloadPath=null, присутствующая блёрбом на листинге |
| Введённый комментарий | «re-save-note» |
| Тумблер Auto-download | ON |

## Заметки для автоматизации

- Точка кода: `BrowserViewModel.kt:834-924` внутри `applyRating`, ветка `rating !=
  null` (:891-923) — зеркало TC-114, но через ВХОД С ЛИСТИНГА, а не панель работы.
  Сам предикат перехода (edge vs level) с 2026-08-10 (фикс `cc201f7`) живёт в
  единой точке `onRatingTransition` (:779-791, вызывается из :922), не в теле
  `applyRating` — см. `requirements` выше.
- **Фикстурный блокер устранён (2026-07-28, `AT-BUG-029`, `Fixed`):** чтобы
  негативный Then был содержательным (не ложно-зелёным независимо от наличия
  бага), иллегитимное повторное скачивание, если оно случится, обязано РЕАЛЬНО
  завершиться файлом — для этого фоновому OkHttp-вызову
  `DownloadRepository.downloadWork` (GET work-страницы + GET `.html`) нужна
  replay-запись, СОВПАДАЮЩАЯ по URL с работой W. `listing_basic.mitm`
  (`framework/data/recording_builder.py`) теперь несёт ВСЕ четыре нужных
  транзакции, включая GET самого `.html`-файла (`rb.download_url(work)`) —
  подробности фикса в `bugs/AT-BUG-029.md`.
- Тест **написан и подключён**: `framework/tests/test_downloads.py::
  test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload`
  (`automated_by` заполнен) — ждёт штатного F1-ревью нового автотеста
  (`state/rules.yaml`), включая независимое воспроизведение и красную пробу.
- **Тест ОЖИДАЕМО красный прямо сейчас** — это НЕ дефект фикстуры/теста.
  Продуктовый баг `bugs/BUG-014.md` (`type: app_bug`, `status: Open` в
  приложении) реально вызывает повторное скачивание при правке заметки уже
  Favorite-работы; тест — регрессионный замок на этот баг и станет зелёным
  автоматически, без правки самого теста, когда BUG-014 будет исправлен в
  `app-under-test/`. Красный прогон TC-115 не основание откатывать
  `AT-BUG-029` (см. предупреждение в самом `AT-BUG-029.md`).
- **Батарея правил-реакций:** edge vs level — вход #2 из 3 в единую точку
  `onRatingTransition` (`applyRating`/:922); прочие пункты (идемпотентность/
  propagation) — то же обоснование «н-п», что в TC-114 (тот же класс эффекта,
  другой вход).
- Сиблинг BUG-015 (авто-kudos) НЕ в скоупе — level-предикат снят тем же фиксом
  `cc201f7`, что и BUG-014 этого кейса (Verified 2026-08-11); см. актуализированную
  заметку TC-114.

## Ревью автотеста

**2026-07-29T10:07:53Z — test-reviewer (F1, вердикт: ПРОЙДЕНО, `Approved → Automated`,
`automation_status: active`).**

1. **Архитектура (C1):** `python scripts/arch_check.py` → «ошибок 0, предупреждений 0»;
   `ALLOWLIST` в `scripts/arch_check.py:80` пуст — исключения «под себя» не заводились.
   Локаторов/драйвера в теле теста нет, все действия — через `framework/steps/*`
   (`app_steps`/`saf_steps`/`settings_steps`/`library_steps`/`browser_steps`/`rating_steps`),
   `sleep` отсутствует (ожидания — `wait_until`/`is_present` слоя core/screens).
2. **Traceability:** `@allure.id("TC-115")` == id кейса; `@pytest.mark.p1` == `priority: P1`;
   `@pytest.mark.replay` соответствует режиму (`replay`-фикстура,
   `rb.LISTING_BASIC_FILENAME`); `automated_by` указывает на реально существующую и
   собираемую функцию (`collected 218 items / 1 selected` в прогоне ниже).
3. **Соответствие кейсу по смыслу:** все три Then реализованы по сути, без ослабления —
   комментарий проверяется по ТЕКСТУ в свёрнутом превью
   (`rating_steps.assert_comment_collapsed_with_text`, не «элемент существует»);
   негативный Then проверяется download-иконкой карточки (наблюдаемая проекция
   `downloadPath=null`), а не наличием карточки; третий Then — общим оракулом
   `download_oracle` БЕЗ `@pytest.mark.produces_download` (ожидание = 0 новых файлов).
   Строка `Инвариант:` (C4) кейсу не требуется: область — не комбинаторная
   (не фильтр/сортировка/видимость/backup/tabs/темы), а точечный edge-vs-level
   негативный сценарий одной точки кода (`BrowserViewModel.kt:862`).
4. **Фикстуры и данные:** порядок `(replay, loved_work_seeded, driver)` корректен —
   `clean_state()` + `seed_library([(W.LOVED, "SAVE")])` выполняются ДО создания
   Appium-сессии (контракт conftest, урок TC-008); тест владеет единственной работой,
   от порядка других тестов не зависит, чистка — `pm clear` следующего `clean_state`.
5. **Flake-риск:** явные ожидания на каждом шаге (`open_listing` ждёт блёрбы,
   `assert_rating_badge_visible` опрашивает bridge-round-trip, а не читает однократно);
   `wait_app_ready` (не `wait_ui_ready`) перед навигацией по Settings — та же гонка,
   что закрыта в TC-032; клик Rate-кнопки — через JS DOM API (обход
   `ElementNotInteractableException` на перекрывающем оверлее); живой AO3 не
   используется — все четыре транзакции покрыты `listing_basic.mitm` (AT-BUG-029).
6. **Независимое воспроизведение (ревьюером, не автором).** Среда:
   `. tasks.ps1; Get-Device` → `DEVICE: emulator-5554`. Прогон:
   `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1;
   Invoke-Pytest -k test_edit_note_on_already_saved_work_via_listing_overlay_does_not_redownload -v"`
   → `1 failed, 217 deselected, 1 warning in 63.90s`, `PYTEST_EXIT=1`.
   Падение — ДЕТЕРМИНИРОВАННОЕ и по ожидаемой причине: `tests/test_downloads.py:275`
   → `steps/library_steps.py:129`, `AssertionError: download-иконка не появилась у
   «A Loved Test Work»` (последний Then), НЕ setup/инфраструктурная ошибка — весь Given/When
   (Settings-тумблер, листинг, bottom-sheet, «Save note», свёрнутое превью с текстом)
   прошёл. Оракул зафиксировал суть: `UserWarning: download_oracle: незапрошенное
   скачивание — класс BUG-014 … ['…/ao3_downloads/ao3_A Loved Test Work_900000001.html']`.
   Rerun-политика (`--only-rerun ReadTimeoutError|MaxRetryError`) не сработала —
   класс падения продуктовый, не env. Сигнатура полностью совпала с прогоном автора
   от 2026-07-28 (`bugs/AT-BUG-029.md`) — воспроизводимость подтверждена независимо.
7. **Красная проба (п.7 F1).** Отдельная синтетическая порча не вносилась и не
   требовалась: тест ФАКТИЧЕСКИ красный на живом дефекте `bugs/BUG-014.md`
   (`app_bug`, `status: Open`) — механизм понятен, подтверждён реальным файлом в
   download-директории, текст падения указывает на суть (иконка/файл), а не таймаут-мусор.
   Обратная полярность доказана В ТОМ ЖЕ прогоне: ТОТ ЖЕ ассерт
   `library_steps.assert_download_icon_shown` ПРОШЁЛ на baseline-шаге (строка 249,
   до When) и УПАЛ после When — предикат не тавтологически ложен, тест умеет и
   зелёный, и красный. Порчи не вносилось → откатывать нечего, `git status` чист
   по `framework/` (тестовый код ревьюером не тронут — граница роли).
   Маскировки нет: assert не ослаблен ради зелёного, `@pytest.mark.produces_download`
   не добавлен (что «узаконило» бы незапрошенное скачивание) — красный содержателен
   и снимется САМ при фиксе BUG-014 в `app-under-test/`.

Замечаний, требующих доработки автотеста, нет. Наблюдения (не блокирующие, вне
границ правки этого кейса, доложены координатору по D-0043): `bugs/BUG-014.md`
несёт `test_cases: []` и `known_issue: "false"` — при `automation_status: active`
ожидаемо-красный TC-115 будет всплывать в каждом регрессионном прогоне и потребует
дедупа failure-analyst/bug-reporter вручную; связка `test_cases: ["TC-114","TC-115"]`
+ решение по `known_issue` (D14) — работа Lead/владельца, не автора теста.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Область содержит правило-реакцию — батарея адресована (edge-vs-level — предмет
      кейса; блокер автоматизации заведён test_debt-багом AT-BUG-029 в этом же ходе)
