---
key: "BUG-001"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-006", "test_case:TC-015", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-10T16:56:00Z"
updated: "2026-07-10T16:56:00Z"
archived: false
resolution: null
---

# PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»

_Спроецировано из `bugs/BUG-001.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-001 — Расхождения PROJECT.md с кодом (коллекция примеров)

Класс бага: PROJECT.md описывает функциональность/тексты, которых в коде
приложения нет или они другие. Один баг — все примеры класса (решение
оператора 2026-07-10 при добавлении примера 2).

## Окружение
Эмулятор ao3_test_api34 (API 34), сборка debug 1.10 (11).

## Шаги воспроизведения (Given-When-Then)
**Given** открыт экран Library
**When** пользователь смотрит подписи вкладок
**Then (ожидалось по PROJECT.md §Screens/Library)** «Loved · Liked · Read · Pending · Disliked · Downloads»
**Actual (факт по коду и живому UI)** «FAVORITE · KUDOSED · READ · PENDING · DISLIKED · FILES»

Аналогично меню рейтинга (ui/components/RatingOverlay.kt): «Favorite/Kudosed/…/Dislike»
вместо «Loved/Liked».

## Пример 2 (2026-07-10): глобальный «Enable filtering» не существует

**Ожидалось по PROJECT.md §Priority rules п.3:** «when Enable filtering is
off, all works are shown regardless of rating» — глобальный тумблер
фильтрации в Settings, отдельный от per-rating переключателей.

**Факт по коду** (разбор test-automator 2026-07-08, блокер №2 в
`test-cases/visibility/TC-015.md`, секция «Заблокировано»):
`SettingsScreen.kt` (~715–800, секция Content Visibility),
`SettingsUiState`/`SettingsViewModel`, `MainActivity.kt`
(`setHiddenRatings`), `ao3_bridge.js` — глобального master-флага НЕТ.
Есть только per-rating тумблеры «Hide {rating} works»
(`hiddenRatings: Set<Rating>`) и `filterDisplayMode` (Hide/Dim).

**Следствие:** TC-015 (P0, visibility) не автоматизируем как написан —
его Given/When ссылается на несуществующий элемент UI. Развилка
переформулировки кейса (per-rating тумблер vs дублирование TC-013) —
решение человека/test-designer при ревью Review→Approved; добавлен в
`test_cases` этого бага.

## Анализ
Кандидат в баг ДОКУМЕНТАЦИИ (PROJECT.md устарел) либо именования относительно задумки.
Источники: app/src/main/java/com/example/ao3_wrapper/ui/library/LibraryScreen.kt (enum LibTab),
ui/components/RatingOverlay.kt (ratingOptions). Требует решения человека/test-designer
(есть фоновая задача). Изменять код приложения нельзя.
Память проекта подтверждает класс: PROJECT.md ненадёжен, истина = код
app-under-test (зафиксировано фидбеком оператора ранее).

## Верификация
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
