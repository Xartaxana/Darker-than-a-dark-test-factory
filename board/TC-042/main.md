---
key: "TC-042"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p1"
summary: "Удаление фильтр-профиля из Settings убирает его из списка и панели"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:filter-profiles", "risk:R-09", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-17T22:39:06Z"
updated: "2026-07-17T22:39:06Z"
archived: false
resolution: "done"
---

# Удаление фильтр-профиля из Settings убирает его из списка и панели

_Спроецировано из `test-cases/filter-profiles/TC-042.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-042 — Удаление фильтр-профиля

## Предусловия
- Приложение запущено, в Room засеяны 2 фильтр-профиля с разными именами ("Profile A",
  "Profile B") через расширение сидинг-скрипта (см. заметку TC-041).
- Открыт экран Settings, секция "Filters" показывает оба профиля.

## Сценарий (Given-When-Then)

**Given** в Settings в секции "Filters" отображаются 2 сохранённых профиля: "Profile
A" и "Profile B"

**When** пользователь нажимает кнопку удаления рядом с "Profile A"

**Then** "Profile A" исчезает из списка в Settings, "Profile B" остаётся
**And** при переходе на листинговую страницу и раскрытии фильтр-панели "Profile A"
больше не предлагается в списке выбора

## Проверяемые данные
| Параметр | Значение |
|---|---|
| FilterProfile A | произвольное имя/queryString, удаляемый |
| FilterProfile B | произвольное имя/queryString, контрольный (должен остаться) |

## Заметки для автоматизации
- Требует того же расширения сидинга, что и TC-041 (таблица `filter_profiles`).
- Наличие второго профиля (Profile B) в Given — намеренно, чтобы отличить "удалён
  именно нужный элемент" от "весь список случайно очищен".
- **Автоматизирован (AT-BUG-006, инкремент 2):** листинговая часть "And" использует
  СУЩЕСТВУЮЩУЮ synthetic-фикстуру `listing_basic.mitm` (не реальную запись формы
  Sort & Filter из TC-040) — нативная `FilterPanel` (`BottomBar.kt`) видна на любой
  странице, чей URL проходит `BrowserViewModel.FILTERABLE_PAGE`, независимо от
  реальности разметки формы; сама AO3-форма Sort & Filter в этой проверке не
  участвует. Кейс выбран вместо TC-041 именно по этой причине — TC-041 требует
  навигации с параметрами (`work_search[...]`), которая не матчится ни с одним
  offline-recorded flow и уходит в live-сеть при server-replay.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов

## Ревью автотеста

**Вердикт: ПРОЙДЕНО (F1).** test-reviewer, 2026-07-17. Approved → Automated,
automation_status: active.

Чек-лист:
1. **Архитектура (C1):** `python scripts/arch_check.py` → «ошибок 0, предупреждений
   0». Тест не в ALLOWLIST, локаторов/driver в `tests/` нет (только steps),
   `sleep` отсутствует — ожидания через `core/waits`.
2. **Traceability:** `@allure.id("TC-042")` == id кейса; `@pytest.mark.p1`
   соответствует `priority: P1`; `@pytest.mark.replay` (offline, не живой AO3);
   `automated_by` указывает на существующую `test_delete_filter_profile`.
3. **Соответствие кейсу:** GWT реализован полностью. Свойство удаления проверено с
   контролем: `assert_filter_profile_not_listed(A)` + `assert_filter_profile_listed(B)`
   в Settings и `assert_filter_not_offered(A)` + `assert_filter_offered(B)` в
   фильтр-панели — отличает «удалён именно нужный» от «список случайно очищен», не
   единичный пример. CRUD-удаление с контрольным элементом (не комбинаторная
   матрица фильтр/сорт/видимость) — отдельная строка `Инвариант:` не требуется,
   свойство (множество: A убран, B сохранён) проверяется обоими surface'ами.
4. **Фикстуры/данные:** `two_filter_profiles_seeded` сидит ДО создания
   Appium-сессии (порядок аргументов `replay, two_filter_profiles_seeded, driver` —
   сидинг раньше `driver`), `clean_state()` перед сидом, тест владеет своими
   данными и независим от порядка.
5. **Flake-риск:** replay (`listing_basic.mitm`), без живого AO3; ожидания явные
   (`assert_filter_not_offered` timeout, `open_listing` ждёт блёрбы,
   `open_filter_dropdown` → `ensure_visible`); гонок с Compose-анимацией не найдено.
6. **Независимый зелёный прогон:** `Invoke-Pytest -k test_delete_filter_profile`
   → `test_delete_filter_profile[listing_basic.mitm] PASSED` (в связке с TC-057,
   114.19s суммарно; эмулятор `emulator-5554`, writable-system + mitm-CA).
7. **Красная проба (red_probe 2026-07-17T22:39:06Z):** порча — нейтрализован
   `SettingsScreen.delete_filter_profile` (закомментирован `self.tap(...)`,
   `framework/screens/settings_screen.py:89`), временно, откачено `git checkout`
   тем же ходом (дифф `framework/` чист). Прогон на порче →
   `test_delete_filter_profile[listing_basic.mitm] FAILED` на осмысленном assert'е
   `assert_filter_profile_not_listed(name_a)` (`steps/settings_steps.py:97`):
   «фильтр-профиль «Profile A» всё ещё виден в списке Settings — ожидали удалённым»
   — падение указывает на суть порчи (удаление не выполнено), не таймаут-мусор.
   Тест умеет падать.
