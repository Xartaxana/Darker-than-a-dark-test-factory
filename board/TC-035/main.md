---
key: "TC-035"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Delete downloaded file удаляет только файл, сохраняя строку рейтинга"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:downloads", "risk:R-05", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-09T11:15:00Z"
updated: "2026-07-09T11:15:00Z"
archived: false
resolution: "done"
---

# Delete downloaded file удаляет только файл, сохраняя строку рейтинга

_Спроецировано из `test-cases/downloads/TC-035.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-035 — Delete downloaded file сохраняет WorkRating

## Предусловия
- Приложение запущено, в Room засеяна работа с рейтингом Loved и связанным локальным
  файлом (`downloadPath` заполнен, файл существует).
- Открыт экран Library, вкладка FAVORITE содержит эту работу с open-иконкой.

## Сценарий (Given-When-Then)

**Given** работа W имеет рейтинг Loved и скачанный файл

**When** пользователь делает long-press по карточке работы W и в открывшемся overlay
выбирает "Delete downloaded file"

**Then** файл удаляется с диска, `downloadPath` работы W становится пустым
**And** работа W остаётся во вкладке FAVORITE с прежним рейтингом Loved (строка
`WorkRating` не удалена)
**And** карточка работы W снова показывает download-иконку вместо open-иконки

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа W | засеяна с rating=SAVE и заполненным downloadPath на существующий файл |

## Заметки для автоматизации
- Отличать явно от TC-036 (Delete work — полное удаление строки и файла) — оба
  действия доступны в одном overlay, легко перепутать локаторы; выбрать точный текст
  кнопки "Delete downloaded file" (не "Delete work").
- В overlay опция "Delete downloaded file" задизейблена, когда у работы нет файла —
  не относится к этому кейсу, но полезно для граничного P2/P3-кейса позже (не
  заводить сейчас, не запрошено в §9).
- Требует такой же фикстуры файла на диске, как в TC-034 (adb push), плюс запись в
  Room с соответствующим `downloadPath`.

## Ревью автотеста (test-reviewer, 2026-07-09)

Вердикт: **Пройдено** — `Approved → Automated`, `automation_status: active`.

1. **Архитектура (C1):** `python scripts/arch_check.py` — ошибок 0, предупреждений 0.
   Файл теста не в ALLOWLIST; локаторы в `framework/screens/library_screen.py`,
   бизнес-шаги в `framework/steps/`, ожидания через `core/waits`, `sleep` нет.
2. **Traceability:** `@allure.id("TC-035")` == id кейса; `@pytest.mark.p1` == priority P1;
   `automated_by` указывает на реально существующую и проходящую функцию.
3. **Соответствие по смыслу (R-05, главный риск кейса):** шаг
   `delete_via_overlay(..., "Delete downloaded file")` кликает по локатору
   `by_text("Delete downloaded file")` (library_screen.py:66-68) — БУКВАЛЬНО текст
   «Delete downloaded file», НЕ «Delete work». Сверено с исходником приложения
   `LibraryScreen.kt:354` (`label = "Delete work"`) и `:360`
   (`label = "Delete downloaded file"`) — два разных `DeleteMenuItem` в одном overlay,
   локатор точный (exact `.text()`, не contains), путаницы TC-035/TC-036 нет.
   Assert'ы проверяют суть ожидаемого результата, а не «элемент существует»:
   строка `WorkRating` сохранена (работа осталась во вкладке FAVORITE=SAVE),
   `downloadPath` очищен (карточка снова показывает download-иконку,
   `by_desc("Download")`), файл ушёл из вкладки FILES.
4. **Фикстуры/данные:** `downloaded_work_seeded` (conftest.py:90-99) сидит работу LOVED
   с rating=SAVE и реальным файлом на диске ДО создания Appium-сессии (порядок
   параметров `(downloaded_work_seeded, driver)` — сидинг раньше сессии, как требует
   HANDOFF); `clean_state()` (pm clear) изолирует от других тестов и порядка прогона.
5. **Flake-риск:** ожидания явные (`element_to_be_clickable`/`presence_of_element_located`),
   гонок с AO3 нет (тест офлайн, без сети/replay). Compose-нюанс «клик на родителе
   текстового узла» (clickable на `Row`, `Text` — дочерний, LibraryScreen.kt:379-408)
   отрабатывает: координата тапа по `Text` попадает в границы `Row` — подтверждено
   зелёным независимым прогоном.
6. **Независимое воспроизведение:** `Get-Device` → `DEVICE: emulator-5554`;
   `Invoke-Pytest -k test_delete_downloaded_file_keeps_rating_row` → `1 passed`, PYTEST_EXIT=0.

## Красная проба (red_probe, ретрофит — test-reviewer, 2026-07-22T00:58:17Z)

Режим red-probe-only (только пп.6-7 F1, статус кейса не менялся).
- **Зелёный (п.6):** `Invoke-Pytest tests/test_downloads.py -k '<5 downloads-тестов>'` →
  `5 passed in 220.66s`, `PYTEST_EXIT=0`, emulator-5554.
- **Красная проба (п.7):** порча проверяемого условия (сам риск R-05 — различие двух
  destructive-действий overlay) — действие overlay в тесте подменено с «Delete downloaded
  file» на «Delete work» (строка WorkRating удаляется целиком, а не только файл). Прогон
  `-k test_delete_downloaded_file_keeps_rating_row --reruns 0` → `FAILED`:
  `AssertionError: работа «A Loved Test Work» не найдена во вкладке FAVORITE`
  (`library_steps.py:41`) — падение указывает на суть (строка рейтинга НЕ сохранена).
- **Откат:** `git checkout -- framework/tests/test_downloads.py`; дифф теста чист.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
