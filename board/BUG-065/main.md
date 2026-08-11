---
key: "BUG-065"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "PROJECT.md обещает quick rating-filter toggle icons в топ-баре Browse, но их нет в коде"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-11T13:02:00Z"
updated: "2026-08-11T13:02:00Z"
archived: false
resolution: null
---

# PROJECT.md обещает quick rating-filter toggle icons в топ-баре Browse, но их нет в коде

_Спроецировано из `bugs/BUG-065.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-065 — Несуществующие rating-filter toggle icons в топ-баре Browse

Класс бага (как BUG-001): PROJECT.md описывает функциональность, которой нет в коде приложения.

## Окружение
- Эмулятор / dev-local сборка
- versionCode 12, versionName "dev-local"
- source_commit cc201f789f0fb123722bbba7b29b8e0c6412dac1

## Шаги воспроизведения (Given-When-Then)

**Given** Browse tab открыт, пользователь находится на listing-странице AO3 (browse/search/tag page)
**When** пользователь смотрит на top bar экрана
**Then (ожидалось по PROJECT.md §Screens/Browser, строка 45)** «Quick rating-filter toggle icons in the top bar (Browse tab, listing pages only): tap to hide/show Favorite/Kudosed/Read/Pending/Disliked works» — в топ-баре должны быть иконки для быстрого переключения видимости рейтингов
**Actual (факт по коду MainActivity.kt)** топ-бар содержит ТОЛЬКО TabStrip (когда > 1 вкладки), никаких rating-filter иконок. На listing-страницах нет специальных иконок переключения рейтингов в топ-баре.

## Код, подтверждающий отсутствие фичи

**MainActivity.kt:408–416** (topBar для AppTab.BROWSE):
```kotlin
AppTab.BROWSE   -> if (!isFullscreen && uiState.tabs.size > 1) {
    TabStrip(
        tabs = uiState.tabs,
        activeTabIndex = uiState.activeTabIndex,
        onSelectTab = { browserViewModel.switchTab(it) },
        onCloseTab = onCloseTab,
        onNewTab = { browserViewModel.openTab(BrowserViewModel.HOME_URL, background = false) },
    )
}
```

Переключение рейтингов существует, но ТОЛЬКО в Settings и в side panel (MainActivity.kt:603, `onToggleRating = { settingsViewModel.toggleHideRating(it) }`), не в топ-баре Browse.

## Частота
Фича отсутствует всегда (архитектурное решение, не флаки).

## Артефакты
- Код: `app-under-test/app/src/main/java/com/example/ao3_wrapper/MainActivity.kt:408-416` (topBar для Browse)
- Документация: `app-under-test/PROJECT.md:45`

## Анализ
Кандидат в баг ДОКУМЕНТАЦИИ (как BUG-001). PROJECT.md описывает функциональность быстрого переключения рейтингов в топ-баре Browse, но коде приложения эта фича не реализована. Переключение рейтингов работает в Settings (per-rating тумблеры «Hide {rating} works») и в side panel Browse tab, но не в топ-баре.

Расхождение живо на актуальной сборке cc201f78 со всеми 7 фиксами разработчиков от 2026-08-11 (source_commit state/app-under-test.yaml совпадает).

Развилка для разработчиков: (1) убрать описание фичи из PROJECT.md (как BUG-001); либо (2) реализовать фичу в коде (тогда QA заведёт needs-design область для тест-дизайна).

## Верификация
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[qa @ 2026-08-11T13:02:00Z] Open** Баг заведён на основе перепроверки Lead от 2026-08-11 (решение владельца §10(ш) п.3: перепроверить расхождение после последних фиксов разработчиков). Фича действительно отсутствует в коде. Ожидаю решения разработчика: документировать отсутствие либо реализовать.
awaiting: dev

## Чек-лист качества (bug-reporter)
- [x] Проверены дубликаты среди открытых багов: не найдено (фича не упоминалась ни в одном открытом баге)
- [x] Репро-шаги воспроизводят проблему (архитектурное отсутствие фичи в коде)
- [x] Severity обоснована: minor (доковый дефект, вводит в заблуждение читателей PROJECT.md, но не влияет на функциональность приложения)
- [x] Приложены источники: PROJECT.md + код MainActivity.kt
- [x] Указана точная версия сборки (source_commit cc201f789, versionCode 12)
- [x] Ни одного изменения в app-under-test/
- [x] Класс совпадает с BUG-001 (PROJECT.md расходится с кодом)
