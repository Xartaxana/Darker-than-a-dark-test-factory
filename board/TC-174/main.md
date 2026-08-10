---
key: "TC-174"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "«Open in background tab» с вкладки Files открывает ЛОКАЛЬНУЮ копию, а не AO3-URL"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:library", "risk:R-08", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-10T16:10:49Z"
updated: "2026-08-10T16:10:49Z"
archived: false
resolution: "done"
---

# «Open in background tab» с вкладки Files открывает ЛОКАЛЬНУЮ копию, а не AO3-URL

_Спроецировано из `test-cases/library/TC-174.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-174 — Фоновое открытие с вкладки Files целится в локальный файл, не в AO3

## Предусловия
- Приложение запущено с чистыми данными.
- Засеяна одна работа с `downloadPath`, заполненным через
  `seed_db.seed_with_download` (тот же приём, что TC-034/035/065) —
  `downloadPath` начинается с `file://` (или обычный FS-путь, который
  `localFileUrl()` оборачивает в `file://`, см. requirements).
- Открыт экран Library, активна вкладка **Files** — карточка работы видна.
- Открыта ровно 1 вкладка Browse (Home).

## Сценарий (Given-When-Then)

**Given** приложение на экране Library, активна вкладка Files, карточка
скачанной работы видна, открыта ровно 1 вкладка Browse

**When** пользователь долгим нажатием по карточке открывает overlay и тапает
«Open in background tab»

**Then** число вкладок становится 2, активная вкладка не меняется, экран
остаётся Library (те же три инварианта, что TC-173)
**And** новая (фоновая) вкладка несёт URL ЛОКАЛЬНОГО файла
(`file://`-префикс, значение из `downloadPath` сида), а НЕ
`https://archiveofourown.org/works/<id>` — `assert_persisted_tab_url_at(1,
<file-url>)`

**Инвариант:** цель действия «Open in background tab» зависит от АКТИВНОЙ
вкладки в момент long-press (`LibraryScreen.kt:256-258`): на Files —
локальная копия, на любой из пяти рейтинговых вкладок — AO3-URL (TC-173).
Это НЕ совпадает с правилом тела карточки (`onOpenWork`, `:928`), которое на
ЛЮБОЙ вкладке, включая Files, открывает именно AO3-URL — один и тот же жест
«открыть работу» даёт РАЗНЫЙ адрес в зависимости от того, по какой части
карточки (тело vs long-press-меню) и на какой вкладке произошло действие; эта
асимметрия — задокументированный факт кода (поправка критик-гейта CH-009
2026-08-10), не предмет отдельного вердикта этого кейса.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | засеяна с `downloadPath` (`seed_with_download`), рейтинг любой |
| Вкладка Library при long-press | Files |
| URL новой (фоновой) вкладки | `file://<downloadPath>` (НЕ AO3-URL) |

## Заметки для автоматизации
- Сидинг — `seed_db.seed_with_download`, тот же приём, что TC-065/TC-034/TC-035.
- Переключение на вкладку Files — `library_steps.open_files_tab(driver)`
  (готов, `library_steps.py:14-16`).
- Долгое нажатие + пункт меню — те же примитивы, что TC-173 (routine-добавление
  тапа по «Open in background tab»).
- Ожидаемое значение URL — читается из того же `downloadPath`, что передан в
  сидинг (собрать ожидание в тесте той же функцией `localFileUrl`-эквивалентом,
  не хардкодить путь).
- Не дублирует TC-034 (открытие локального файла В ПЕРЕДНЕЙ вкладке через
  иконку `onOpenFile`, `LibraryScreen.kt:934-935`/`MainActivity.kt:522-526`) —
  тот кейс не использует overlay/фоновую дверь вовсе, другая дверь и другой
  Then (экран переключается).
- Блокера автоматизации нет — тот же класс примитивов, что TC-173.

## Ревью автотеста (F1, test-reviewer, 2026-08-10)

**Вердикт: PASS** — `Approved → Automated`, `automation_status: active`.

- **Архитектура (C1):** `arch_check.py` — 0 ошибок, файл теста чист; локатор
  пункта overlay — в `screens/library_screen.py`, шаги — в `steps/`; `sleep` нет.
- **Traceability:** `@allure.id("TC-174")`, `@pytest.mark.p1` == `priority: P1`,
  `automated_by` резолвится в существующую функцию.
- **Соответствие GWT:** ключевой Then («цель — ЛОКАЛЬНАЯ копия, а не AO3-URL»)
  реализован адресной сверкой `assert_persisted_tab_url_at(1, f"file://{device_path}")`,
  причём ожидание собрано из ФАКТИЧЕСКОГО возврата сидинга той же формулой, что
  `localFileUrl()` (не хардкод пути) — как и требовали заметки кейса. Инвариант
  «цель зависит от активной вкладки» закрыт парой TC-174 (Files → `file://`) +
  TC-173 (рейтинговая вкладка → AO3-URL), т.е. проверяется ОТНОШЕНИЕ, не пример.
- **Фикстуры:** локальная `downloaded_work_seeded_with_path` стоит ПЕРЕД `driver`
  — сидинг до Appium-сессии; `clean_state()` в setup, данные свои.
- **Flake-риск:** только persisted-prefs оракулы, без WEBVIEW-контекста и
  снекбаров; ожидания явные.

**Зелёное воспроизведение (независимое, 1x):** тот же прогон, что TC-173 —
`2 passed, 2 deselected in 96.31s`, `PYTEST_EXIT=0`.

**Красная проба (мутационная):** порча — ожидание подменено на AO3-URL
(`expected_url = work.url`, `framework/tests/test_library_background_open.py:94`),
т.е. симуляция регрессии «overlay на Files целится в archiveofourown.org».
Прогон: `Invoke-Pytest tests/test_library_background_open.py -k 'targets_local_file' -q --no-header --tb=line`
→ `1 failed`, `PYTEST_EXIT=1`, падение по сути порчи:
`AssertionError: URL вкладки на позиции 1:
'file:///data/user/0/com.example.ao3_wrapper/files/ao3_test_downloads/900000001.html',
ожидали 'https://archiveofourown.org/works/900000001'` (`app_steps.py:534`) —
ассерт реально различает локальную цель и AO3-URL, не тавтологичен.
Откат — по байтовой копии (CLAUDE.md п.8): до порчи `git status --porcelain -- <файл>`
ПУСТ, blob `5229e0fa00bb06b4b6a9b1e9799d30e978bdeee3`; после отката дословно:
`git status --porcelain -- framework/tests/test_library_background_open.py` →
пустой вывод, `git hash-object` → `5229e0fa00bb06b4b6a9b1e9799d30e978bdeee3`.

**Замечания (не блокирующие):**
1. Then кейса называет ТРИ инварианта «те же, что TC-173» (счёт, активная
   вкладка, ЭКРАН остаётся Library), тест реализует два: проверки «экран не
   переключился» (`browser_steps.assert_tab_strip_not_visible`) нет. Риск низкий
   — обработчик `onOpenInBackground` (MainActivity.kt:527-529) один и тот же для
   любой вкладки Library и уже доказан TC-173, — но клауза кейса не реализована:
   либо добавить одну строку ассерта, либо снять клаузу из Then.
2. Фикстура `downloaded_work_seeded_with_path` (тест-файл) почти дословно
   повторяет `downloaded_work_seeded` из `conftest.py` (вместе с константой
   `_DOWNLOADED_WORK_FIXTURE`); отличие — только возврат `device_path`. Чище
   вернуть путь из conftest-фикстуры и переиспользовать её (D-0043: класс
   «копия фикстуры вместо расширения»).

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
      (`seed_with_download`)
- [x] Then проверяет наблюдаемое поведение (URL новой вкладки), а не реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет (P1), область (library) и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует
- [x] Не C4-семьи формально; строка `Инвариант:` дана для полноты семейства
      (асимметрия цели действия) — квалифицирующий факт кода, не пример
