---
key: "BUG-001"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "Подписи вкладок Library и меню рейтинга расходятся с PROJECT.md"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-006", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-02T04:30:00Z"
updated: "2026-07-02T04:30:00Z"
archived: false
resolution: null
---

# Подписи вкладок Library и меню рейтинга расходятся с PROJECT.md

_Спроецировано из `bugs/BUG-001.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-001 — Расхождение подписей Library vs PROJECT.md

## Окружение
Эмулятор ao3_test_api34 (API 34), сборка debug 1.10 (11).

## Шаги воспроизведения (Given-When-Then)
**Given** открыт экран Library
**When** пользователь смотрит подписи вкладок
**Then (ожидалось по PROJECT.md §Screens/Library)** «Loved · Liked · Read · Pending · Disliked · Downloads»
**Actual (факт по коду и живому UI)** «FAVORITE · KUDOSED · READ · PENDING · DISLIKED · FILES»

Аналогично меню рейтинга (ui/components/RatingOverlay.kt): «Favorite/Kudosed/…/Dislike»
вместо «Loved/Liked».

## Анализ
Кандидат в баг ДОКУМЕНТАЦИИ (PROJECT.md устарел) либо именования относительно задумки.
Источники: app/src/main/java/com/example/ao3_wrapper/ui/library/LibraryScreen.kt (enum LibTab),
ui/components/RatingOverlay.kt (ratingOptions). Требует решения человека/test-designer
(есть фоновая задача). Изменять код приложения нельзя.

## Верификация
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
