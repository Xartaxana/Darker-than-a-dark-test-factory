---
key: "BUG-012"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-020", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-19T09:55:00Z"
updated: "2026-07-19T09:55:00Z"
archived: false
resolution: null
---

# Clear all ratings не отправляет broadcast открытым вкладкам браузера — бейджи на открытых работах остаются в выбранном состоянии

_Спроецировано из `bugs/BUG-012.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-012 — Clear all ratings НЕ обновляет бейджи на открытых страницах AO3

## Окружение
- Версия приложения: 1.10 (versionCode 11), build 2026-07-02T02:39:46
- Эмулятор: API 34
- Режим: replay (mitmdump)
- Класс дефекта: несоответствие между документированным поведением (PROJECT.md §9: "бейджи на открытых страницах AO3 сбрасываются") и фактической реализацией

## Шаги воспроизведения (Given-When-Then)

**Given** приложение запущено, работа W засеяна с рейтингом SAVE (Loved) в базе Room,
страница `/works/{id}` открыта в браузере с видимым бейджем «Loved» в нижней панели

**When** пользователь открывает Settings, подтверждает диалог "Clear all ratings"

**Then (ожидалось)** при возврате на вкладку с открытой страницей работы W бейдж «Loved» исчез
(панель показывает отсутствие рейтинга), БЕЗ ручной перезагрузки страницы пользователем

**Actual (фактически)** бейдж остаётся в выбранном состоянии (видимо выбранным), несмотря на то,
что все рейтинги в базе удалены

## Частота
Всегда (детерминированный дефект поведения, не зависит от сетевых условий или состояния среды)

## Артефакты
Witness находится в TC-020.md, секция "## Заблокировано" / "Находка test-automator (2026-07-18)":
- Эмулятор: emulator-5554
- Метод замера: luma-прокси (как TC-009/TC-010)
- baseline(selected)=134.2 (лума выбранного состояния «Favorite»)
- порог деселекта (unselected): 178.9
- Фактический результат после Clear all + возврата на Browse: лума НЕ поднялась выше 178.9 за 10с,
  кнопка осталась в выбранном виде
- Тест: `framework/tests/test_settings.py::test_clear_all_ratings_resets_open_work_page_badge` (`@pytest.mark.skip`)

## Анализ (кодовые доказательства)

### SettingsViewModel.confirmClearAll() не зовёт механизмы обновления открытых вкладок

`app-under-test/app/src/main/java/com/example/ao3_wrapper/ui/settings/SettingsScreen.kt:501-504`:
```kotlin
fun confirmClearAll() {
    _uiState.update { it.copy(showClearDialog = false) }
    viewModelScope.launch(Dispatchers.IO) { repo.clearAllRatings() }
}
```

Метод вызывает ТОЛЬКО `repo.clearAllRatings()`. Нет вызовов:
- `BrowserViewModel.refreshActiveTabRating` (не существует в коде)
- `BrowserViewModel.broadcastRatingChange` (существует, но не вызывается)

### Механизм обновления бейджей на открытой странице

Согласно кодовому комментарию в `BrowserViewModel.kt` и CLAUDE.md (instruction file для разработчиков):
- `applyRating` вызывает `broadcastRatingChange(workId, rating, comment, tags)` — это
  отправляет обновление в JavaScript: `window.applyRatings(ratingsJson, commentsJson)`,
  который пересчитывает цвета бейджей на странице БЕЗ reload.
- `savePanelRating` (встроенная панель на work-странице) также использует этот механизм.
- `currentPageRating` (источник визуального состояния кнопки `RatingMenu`/`WorkRatingPanel`,
  `BottomBar.kt:106-119,223-237`) перечитывается из Room ТОЛЬКО при срабатывании `onPageLoaded`
  (`BrowserViewModel.kt:463-509`, триггерится на навигацию/reload).

**Вывод:** Clear all ratings удаляет данные из Room (БД), но НЕ триггерит ни `broadcastRatingChange`,
ни перезагрузку страницы. Открытая страница с рейтингом не знает, что данные удалены, и продолжает
показывать старый рейтинг.

## Открытый вопрос (требуется триаж)

**Требуется ли broadcast к открытым вкладкам при Clear all ratings, или документация PROJECT.md §9
была неверна с самого начала?**

Два возможных исхода:
1. **APP_BUG**: Поведение должно совпадать с документацией — Clear all должен вызвать
   `broadcastRatingChange` для активной вкладки (если та содержит рейтинг, который был сброшен),
   чтобы бейджи обновились без reload.
2. **Intended** или доп. спецификация: Если это по дизайну (например, "Clear all требует reload
   открытых страниц"), то PROJECT.md §9 нужно уточнить, а TC-020.then нужно переформулировать
   для отражения реального ожидаемого поведения.

**Решение принимает:** test-runner / оператор (владелец продукта) в ходе триажа.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-18T12:00:00Z — bug-reporter (role=creator, диспатч от test-automator при автоматизации TC-020):**

Находка test-automator эмпирически подтверждена и продублирована в коде:
- `SettingsViewModel.confirmClearAll()` вызывает ТОЛЬКО `repo.clearAllRatings()`, без broadcast-механизмов
- Код приложения подтверждает отсутствие вызовов `broadcastRatingChange` из Clear all-пути
- `currentPageRating` обновляется только при `onPageLoaded` (reload/навигация)
- Ожидаемое по PROJECT.md §9 поведение ("бейджи на открытых страницах AO3 сбрасываются") не совпадает
  с фактической реализацией

Открытое требование к уточнению: является ли отсутствие broadcast-оповещения открытым вкладкам
дефектом приложения или неточностью документации. Баг заведён как `app_bug` (дефект в коде приложения),
так как PROJECT.md при первичной закладке TC-020 явно декларирует "без перезагрузки"; однако решение
о переводе в `Intended` или доп.спец остаётся за владельцем продукта.

TC-020 оставлен в статусе `Approved` (тест написан по документации, `automated_by` пуст,
триаж/переформулирование Then — задача test-designer, не test-automator; найденный класс —
уже в теле TC-020, не заводится новый AT-BUG для test-debt).

**2026-07-18T12:40:00Z — координатор (Lead, Sonnet):** переименован из `AT-BUG-018` в `BUG-012` —
`AT-BUG-` префикс зарезервирован под `type: test_debt` (schemas/agent-output и конвенция id
`AT-BUG-NNN` vs `BUG-NNN`, найдено validate_frontmatter при приёмке); это `app_bug`, правильный
префикс — `BUG-`. Добавлено отсутствовавшее поле `updated`. Содержание не менялось. Ссылка в
test-cases/settings/TC-020.md обновлена на новый id.

**2026-07-19T09:55:00Z — Lead (Fable), РЕШЕНИЕ ОПЕРАТОРА (триаж закрыт):**
оператор подтвердил исход 1 — **APP_BUG с низким приоритетом**. Поведение
обязано совпадать с PROJECT.md §9 («бейджи на открытых страницах сбрасываются
без reload»): Clear all ratings должен триггерить обновление открытых вкладок
(`broadcastRatingChange`-путь или эквивалент — выбор реализации за
разработчиком). Документация НЕ переписывается, TC-020.Then остаётся как есть
(корректно выражает требование). Следствия: `awaiting: dev` (ждёт фикса
приложения; приоритет низкий — фикс не срочный), `known_issue: true` (D14/B2 —
контроль «не ухудшился» на каждой новой сборке правилом D3 still-repro), баг
остаётся `Open` до фикса. TC-020 переведён `Approved → Blocked`
(`blocked_reason: product_decision`, матрица `*→Blocked by factory`) — правило
14 не должно холостым диспатчем гонять автоматизацию кейса, чей Then
детерминированно красный на текущей сборке; тест
`test_clear_all_ratings_resets_open_work_page_badge` остаётся в файле под
`@pytest.mark.skip` как witness. Возврат TC-020 в `Approved` — когда BUG-012
дойдёт до `Fixed` (фикс-верификация D1 включит снятие skip и прогон).
