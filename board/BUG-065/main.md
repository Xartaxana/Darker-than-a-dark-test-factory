---
key: "BUG-065"
project: "AO3"
issueType: "bug"
status: "bug-verified"
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
created: "2026-08-16T01:15:00Z"
updated: "2026-08-16T01:15:00Z"
archived: false
resolution: "done"
---

# PROJECT.md обещает quick rating-filter toggle icons в топ-баре Browse, но их нет в коде

_Спроецировано из `bugs/BUG-065.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-08-16 | source_commit 27d5cfd193b3e0475b872d5c5c80daadcc299a79 (fixed_in предок-цепочка: found_in cc201f789f0fb123722bbba7b29b8e0c6412dac1 подтверждён `git merge-base --is-ancestor cc201f78... 27d5cfd1...` → ANCESTOR_OK; versionName "dev-local", versionCode 12, built_at 2026-08-16T01:01:26Z — state/app-under-test.yaml) | test_cases: [] (документационный дефект, carve-out по функциональному критерию `.claude/agents/fix-verifier.md` «device-прогон не может исполнить проверяемое поведение», образец BUG-061; **не** BUG-067/ESC-033 — тот прецедент carve-out НЕ разрешает) — заменено CODE INSPECTION первоисточника на коммите 27d5cfd1 | Зелёный: PROJECT.md переписан под факт, код не изменился (фича и была в side panel — теперь верно задокументирована) | Verified |

## Обсуждение

**[qa @ 2026-08-11T13:02:00Z] Open** Баг заведён на основе перепроверки Lead от 2026-08-11 (решение владельца §10(ш) п.3: перепроверить расхождение после последних фиксов разработчиков). Фича действительно отсутствует в коде. Ожидаю решения разработчика: документировать отсутствие либо реализовать.
awaiting: dev

**[gitlab:dyakagreen @ 2026-08-15T23:08:38.703Z]** > **[dev @ 2026-08-16] Исправлено — вариант 1 (правка документации)**
> 
> Расхождение подтверждено на актуальном `main` (был `59be96c`). Топ-бар Browse (`MainActivity.kt:477`) действительно рендерит только `TabStrip`, и то лишь когда открыто больше одной вкладки.
> 
> Фича при этом не отсутствует — она находится не там, где обещала документация. Переключатели рейтингов реализованы в **боковой панели Browse** (`BrowseSidePanel.kt:113–131`): по одной иконке на рейтинг, показываются только на listing-страницах (`if (!isWorkPage)`), окрашены цветом рейтинга когда works видимы и приглушены когда скрыты. Те же переключатели продублированы в Settings как тумблеры «Hide {rating} works» (`SettingsScreen.kt:831`). Оба пути пишут в один и тот же набор `hiddenRatings`.
> 
> Добавлять дубль иконок в топ-бар не стали: бар уже занят `TabStrip`, а боковая панель — устоявшееся место для browse-level контролов.
> 
> `PROJECT.md:45` переписана под фактическое поведение (расположение, условие показа только на listing-страницах, цветовая индикация, связь с Settings, и явно сказано что в топ-баре только `TabStrip`).
> 
> Коммит: `27d5cfd` на `main`.
> 
> awaiting: qa

**[gitlab:dyakagreen @ 2026-08-15T23:08:48.091Z]** Метка `qa-status::QAready` выставлена на GitLab issue — переход Open→Fixed зафиксирован автоматически (второй канал, docs/06 §3а, gitlab-label).

**[fix-verifier @ 2026-08-16T01:15:00Z] Verified.** Carve-out применён: `type: app_bug`, `test_cases: []`, документационный класс (как BUG-001) — verification заменена CODE INSPECTION по функциональному критерию `.claude/agents/fix-verifier.md`, образец BUG-061, не device-прогон.

**[critic @ 2026-08-16T01:37Z, приёмочный вход]** Существо перепроверено независимо (собственные `git show`/`git merge-base` + сверка кода `BrowseSidePanel.kt`/`SettingsScreen.kt`/`MainActivity.kt:477` на коммите фикса) — PASS, `Verified` не откатывается. Обоснование ошибочно ссылалось на «прецедент BUG-067 D1/ESC-033» — тот прецедент carve-out ЗАПРЕЩАЕТ (см. разбор в `bugs/BUG-058.md`, тот же класс ссылки на анти-прецедент); ссылка исправлена. Тот же открытый пункт очереди Lead, что и в BUG-058: назвать документационный класс явной строкой в `.claude/agents/fix-verifier.md:17-24`.

Ancestry: `git merge-base --is-ancestor cc201f789f0fb123722bbba7b29b8e0c6412dac1 27d5cfd193b3e0475b872d5c5c80daadcc299a79` → exit 0 (`ANCESTOR_OK`); текущая сборка `state/app-under-test.yaml` — тот же коммит `27d5cfd1`, versionCode 12, versionName "dev-local", built_at 2026-08-16T01:01:26Z.

Дословно `git show 27d5cfd1:PROJECT.md` строка 45:
> Quick rating-filter toggle icons in the **Browse side panel** (`BrowseSidePanel.kt`, listing pages only — hidden on work pages): one icon per rating, tinted with its rating colour when visible and greyed when hidden; tap to hide/show Favorite/Kudosed/Read/Pending/Disliked works. The same toggles exist as "Hide {rating} works" switches in Settings; both write the one `hiddenRatings` set. The Browse top bar itself holds only the `TabStrip`, and only when more than one tab is open

Сверка кода на том же коммите:
- `BrowseSidePanel.kt` (`if (!isWorkPage) { ... ratingOptions.forEach { ... PanelIconButton(icon = opt.icon, tint = tint, onClick = { onToggleRating(opt.rating) }) } }`, `tint` = `ratingColors(opt.rating).first` когда видимо / `onSurface.copy(alpha = 0.38f)` когда скрыто) — подтверждает «one icon per rating, listing pages only, tinted/greyed».
- `SettingsScreen.kt` (`Text("Hide ${row.label} works")` + `Switch(checked = uiState.isHidden(row.rating), onCheckedChange = { viewModel.toggleHideRating(row.rating) })`) — подтверждает дубль в Settings.
- `MainActivity.kt:477` — `AppTab.BROWSE -> if (!isFullscreen && uiState.tabs.size > 1) { TabStrip(...) }` — топ-бар Browse по-прежнему держит ТОЛЬКО `TabStrip`, никаких rating-иконок — подтверждает последнюю фразу строки 45.

PROJECT.md теперь дословно соответствует коду на всех перечисленных пунктах (расположение, условие показа, цветовая индикация, связь с Settings, содержимое топ-бара). `status: Fixed → Verified`, `awaiting: none`, `lock` снят.

## Чек-лист качества (bug-reporter)
- [x] Проверены дубликаты среди открытых багов: не найдено (фича не упоминалась ни в одном открытом баге)
- [x] Репро-шаги воспроизводят проблему (архитектурное отсутствие фичи в коде)
- [x] Severity обоснована: minor (доковый дефект, вводит в заблуждение читателей PROJECT.md, но не влияет на функциональность приложения)
- [x] Приложены источники: PROJECT.md + код MainActivity.kt
- [x] Указана точная версия сборки (source_commit cc201f789, versionCode 12)
- [x] Ни одного изменения в app-under-test/
- [x] Класс совпадает с BUG-001 (PROJECT.md расходится с кодом)
