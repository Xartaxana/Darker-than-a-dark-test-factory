---
key: "TC-173"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "«Open in background tab» из overlay Library открывает работу в фоновой вкладке, не покидая экран Library"
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

# «Open in background tab» из overlay Library открывает работу в фоновой вкладке, не покидая экран Library

_Спроецировано из `test-cases/library/TC-173.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-173 — «Open in background tab» открывает работу в фоне, экран остаётся на Library

## Предусловия
- Приложение запущено с чистыми данными.
- Засеяна работа `W.LOVED` (`ao3_id=900000001`) с рейтингом SAVE (Favorite) —
  фикстура `loved_work_seeded`, тот же приём, что TC-136.
- Открыт экран Library, активна вкладка Favorite (НЕ Files) — карточка работы
  видна.
- Открыта ровно 1 вкладка Browse (стартовая Home) — `wait_persisted_tab_count(1)`.

## Сценарий (Given-When-Then)

**Given** приложение на экране Library, вкладка Favorite активна, карточка
«A Loved Test Work» видна, открыта ровно 1 вкладка Browse (Home)

**When** пользователь долгим нажатием по карточке открывает overlay действий и
тапает первый пункт «Open in background tab»

**Then** число вкладок Browse становится 2 (`wait_persisted_tab_count(2)`,
подтверждено persisted `open_tabs_urls`)
**And** активная вкладка НЕ меняется — остаётся вкладка-0 (Home,
`assert_persisted_active_tab_index(0)`)
**And** экран остаётся Library — оверлей закрыт, никакого перехода на Browse
(в отличие от TC-136/TC-137, где тап по ТЕЛУ карточки переключает экран)
**And** новая (фоновая) вкладка несёт URL самой работы —
`assert_persisted_tab_url_at(1, "https://archiveofourown.org/works/900000001")`
**And** позиция списка Library не изменилась (та же карточка первая видимая, до
и после действия)

**Инвариант:** `openTab(url, background=true)` ниже потолка `MAX_TABS=10`
ВСЕГДА добавляет новую вкладку к существующему множеству, не заменяя и не
переключая активную, — тот же код-путь `openTab`, что и передний вход
(`background=false`, TC-136/TC-131), но с другим значением параметра и без
вызова `selectedTab =`/`navExpanded =` вовсе (MainActivity.kt:529 короче
`onOpenWork`/`onOpenFile` ровно на эти два присваивания).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | `W.LOVED`, `ao3_id=900000001`, `url=https://archiveofourown.org/works/900000001` |
| Вкладок Browse до/после | 1 / 2 |
| Активная вкладка до/после | 0 / 0 (не меняется) |
| Активный экран до/после | Library / Library (не меняется) |

## Заметки для автоматизации
- Долгое нажатие — `library_screen.long_press_work(title)` (готов,
  `framework/screens/library_screen.py:137`), тот же приём, что overlay
  Delete-пунктов.
- Тап по пункту «Open in background tab» — helper ОТСУТСТВУЕТ (`library_screen.py`
  знает только `tap_delete_work`/`tap_delete_downloaded_file`, CH-009
  test-automator note #1), но это РУТИННОЕ добавление по точному образцу
  соседних методов (`self.tap(self.by_text("Open in background tab"))`), не
  блокер: тот же класс, что `tap_delete_work`/`tap_delete_downloaded_file`
  (`library_screen.py:146-152`), просто третий пункт того же меню.
- Оракулы — persisted-prefs примитивы (`app_steps.py`), НЕ WEBVIEW-контекст:
  `wait_persisted_tab_count`, `assert_persisted_tab_url_at`,
  `assert_persisted_active_tab_index` — тот же приём и то же обоснование
  sticky-context (AT-BUG-018/AT-BUG-022), что TC-131/132/136.
- Позиция списка — `library_steps.capture_topmost_card_y` до/после, тот же
  приём, что TC-030 (не проверяет сам факт «не сдвинулся», доп. Then можно
  дёшево слить в тот же тест — не отдельный сценарий).
- Не проверяет текст/счётчик снекбара — отдельный кейс TC-176 (та же грань
  §9, но фокус на `browse-background-open-snackbar`, красный замок BUG-059).
- Блокера автоматизации нет — все примитивы существуют и уже используются
  (TC-131/132/136), новый метод оверлея тривиален.

## Ревью автотеста (F1, test-reviewer, 2026-08-10)

**Вердикт: PASS** — `Approved → Automated`, `automation_status: active`.

- **Архитектура (C1):** `python scripts/arch_check.py` — ошибок 0; файл теста в
  выводе не фигурирует (2 WARN — чужой `test_swipe_to_text_settle_unit.py`,
  известное ALLOWLIST-исключение). В тесте нет `sleep` (проверено; позитивный
  контроль поиска — 82 вхождения в 18 других файлах `framework/`), локаторы —
  в `screens/` (`library_screen.tap_open_in_background`), шаги — в `steps/`.
- **Traceability:** `@allure.id("TC-173")` == id кейса, `@pytest.mark.p1` ==
  `priority: P1`, `automated_by` указывает на существующую функцию.
- **Соответствие GWT:** ассерты реализуют Then кейса СВОЙСТВОМ, не примером:
  счёт вкладок дельтой (позитивный якорь `wait_persisted_tab_count(1)` ДО When),
  `assert_persisted_active_tab_index(0)` (активная не переключилась),
  `assert_tab_strip_not_visible` (экран не ушёл на Browse — TabStrip рендерится
  только при `selectedTab == BROWSE`), адресный URL на позиции 1.
- **Фикстуры:** `loved_work_seeded` стоит ПЕРЕД `driver` в сигнатуре — сидинг до
  создания Appium-сессии (порядок соблюдён); фикстура владеет данными
  (`clean_state()` в setup).
- **Flake-риск:** ожидания явные (persisted-prefs поллинг, `wait_*`), снекбар в
  этом кейсе не читается (ловушка CH-009 ~3.5 с не задействована), WEBVIEW-
  контекст не используется.

**Зелёное воспроизведение (независимое, 1x):**
`Invoke-Pytest tests/test_library_background_open.py -k 'stays_on_library or targets_local_file' -q`
→ `2 passed, 2 deselected in 96.31s`, `PYTEST_EXIT=0`.

**Красная проба (мутационная):** порча — подмена When на ПЕРЕДНЕЕ открытие
(`library_steps.open_work_in_browser` вместо `open_in_background_via_overlay`,
`framework/tests/test_library_background_open.py:64`), т.е. симуляция регрессии
«фоновая дверь ведёт себя как передняя». Прогон:
`Invoke-Pytest tests/test_library_background_open.py -k 'stays_on_library or targets_local_file' -q --no-header -x --tb=line`
→ `1 failed`, `PYTEST_EXIT=1`, падение содержательное и по сути порчи:
`AssertionError: active_tab_index в prefs: 1, ожидали 0` (`app_steps.py:559`).
Откат — восстановлением байтовой копии (CLAUDE.md «Дисциплина команд» п.8; до
порчи `git status --porcelain -- framework/tests/test_library_background_open.py`
был ПУСТ, blob-хэш `5229e0fa00bb06b4b6a9b1e9799d30e978bdeee3`). Сверка после
отката — дословно: `git status --porcelain -- framework/tests/test_library_background_open.py`
→ пустой вывод; `git hash-object framework/tests/test_library_background_open.py`
→ `5229e0fa00bb06b4b6a9b1e9799d30e978bdeee3` (совпадает с зафиксированным до
порчи).

**Замечания (не блокирующие, к следующему касанию теста):**
1. Предусловия кейса называют «replay-режим (`listing_basic.mitm`)», но тест не
   берёт фикстуру `replay` и не несёт `@pytest.mark.replay`. Измерено:
   `adb shell settings get global http_proxy` → `:0` (прокси не выставлен) —
   прогон шёл без replay. Для ЭТОГО теста несущей зависимости от AO3 нет (ни
   один ассерт не читает страницу), поэтому не блокер; расхождение кейс↔тест
   надо снять в одну сторону: либо убрать строку про replay из Предусловий,
   либо добавить фикстуру. Ср. блокер того же класса в TC-175 (там зависимость
   несущая).
2. `topmost_before/after` при одной засеянной карточке проверяет позицию списка,
   который заведомо не скроллится, — ассерт почти тавтологичен (сам кейс называет
   его дешёвым довеском). Не требует правки, но и сигнала не несёт.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами (`loved_work_seeded`)
- [x] Then проверяет наблюдаемое поведение (счёт/активность вкладок, экран,
      URL, позиция списка), а не внутренние поля `BrowserViewModel`
- [x] Заголовок сформулирован от ожидаемого/спецификационного поведения
- [x] Указаны приоритет (P1), область (library) и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует — рутинный метод по существующему шаблону
- [x] Область не C4-семьи (единичный сценарий открытия, не сортировка/фильтр/
      backup) — строка `Инвариант:` дана для полноты семейства TC-131/136/137,
      не потому что область формально входит в банк C4
