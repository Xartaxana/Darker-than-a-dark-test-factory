---
key: "BUG-001"
project: "AO3"
issueType: "bug"
status: "bug-rejected"
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
created: "2026-08-04T16:43:21Z"
updated: "2026-08-04T16:43:21Z"
archived: false
resolution: null
---

# PROJECT.md расходится с кодом: подписи вкладок Library/меню рейтинга; несуществующий глобальный «Enable filtering»

_Спроецировано из `bugs/BUG-001.md` (источник правды).
Статус в нашей машине: **Rejected**._

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

## Обсуждение

**Решение владельца (2026-07-17, слово оператора в Lead-сессии): эталон =
фактический UI/код.** Оба примера — баг ДОКУМЕНТАЦИИ (PROJECT.md устарел),
не приложения:
- Пример 1 (вкладки): TC-006 фиксирует фактические подписи
  (FAVORITE · KUDOSED · READ · PENDING · DISLIKED · FILES) как
  регрессионный якорь — доводка test-designer, затем Review → Approved.
- Пример 2 (Enable filtering): TC-015 переформулируется под реальный UI —
  per-rating тумблер «Hide Disliked works»; вариант «считать отсутствие
  глобального тумблера дефектом приложения и ждать реализации» ОТКЛОНЁН.
  Фантом «Enable-тумблер», унаследованный реестром фич, исправлен тем же
  днём (defect_found ref=part4-strategy-review).

Баг остаётся Open как коллекция класса: правка самого PROJECT.md — зона
разработчика приложения (наш репо код приложения не трогает).

**fix-verifier, mode=recheck-rejected (2026-08-04, проход /qa-loop 3, правило D4).**
Перепроверка ЧЕСТНАЯ, на актуальной сборке (1.10, versionCode 11, HEAD
`app-under-test` = commit `63f6aac`, сам коммит датирован 2026-06-28 —
файл-таргеты бага в нём не менялись, их последние правки:
`LibraryScreen.kt`/`SettingsScreen.kt` — commit `e7acfad`/`0ec6102` от
2026-06-28, `RatingOverlay.kt` — `0ec6102` от 2026-06-28; `git log` по всем
трём файлам подтверждает: НИ ОДНОГО коммита после 2026-07-17, когда владелец
принял решение по этому багу).

Расхождение живо буквально:
- `LibraryScreen.kt:71-78` — `enum class LibTab`: `SUPER_LIKE("Favorite", ...)`,
  `LIKE("Kudosed", ...)`, `READ("Read", ...)`, `PENDING("Pending", ...)`,
  `DISLIKE("Disliked", ...)`, `DOWNLOADED("Files", null)` — фактические подписи
  вкладок те же, что зафиксированы в TC-006 (FAVORITE·KUDOSED·READ·PENDING·
  DISLIKED·FILES), не «Loved·Liked·Read·Pending·Disliked·Downloads».
- `RatingOverlay.kt:52-54` — `val ratingOptions = listOf(RatingOption(Rating.SAVE,
  ..., "Favorite"), RatingOption(Rating.LIKE, ..., "Kudosed"), ...)` — те же
  подписи в меню рейтинга.
- `SettingsScreen.kt:66-67` — `SettingsUiState`: `val hiddenRatings: Set<Rating> =
  setOf(Rating.DISLIKE)`, `val filterDisplayMode: String = "hide"` — глобального
  master-флага `enableFiltering`/аналога нет; негативный grep (case-insensitive,
  позитивным контролем на `filterDisplayMode` в том же файле подтверждена рабочая
  форма вызова) `grep -rni "enable filtering" app/src/main/` по всему исходнику
  приложения — 0 совпадений.
- Само `PROJECT.md` приложения (не трогали, только прочли) на текущей сборке
  ВСЁ ЕЩЁ содержит расходящиеся утверждения: строка 49 `Tabbed layout: **Loved**
  · **Liked** · **Read** · **Pending** · **Disliked** · **Downloads**`, строка 61
  `**Filtering**: enable/disable globally; ...`, строка 115 `When "Enable
  filtering" is off, all works are shown regardless of rating`.

**Оспаривание репетиционного `Rejected` (2026-08-04T12:32:15Z).** Статус
поставлен БЕЗ новой строки «## Обсуждение» и без ссылки на изменение кода/
PROJECT.md — прямо противоречит записанному решению владельца от 2026-07-17
выше («баг ДОКУМЕНТАЦИИ... баг остаётся Open как коллекция класса») без
видимого нового обоснования в теле бага. Факты на актуальной сборке
подтверждают исходное репро один-в-один — расхождение никуда не делось.
Не меняю статус сам (это ход человека, `Rejected` — зарезервированный статус);
фиксирую спор доказательствами и передаю на `awaiting: dev`.

**Дефекты-собратья (D-0043):** не найдено новых экземпляров сверх уже
перечисленных двух в этом баге (сверка ограничена заявленными в манифесте
файлами — расширять scope не стал).

## Верификация
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-04 | 1.10 (versionCode 11), commit 63f6aac | TC-006, TC-015: девайс не нужен (класс — статичные строки/отсутствие фичи в коде), заменено код-инспекцией (сверка исходников + git-история файлов) | Расхождение подтверждено на актуальной сборке; репетиционный Rejected НЕ подтверждён — обе части исходного репро живы без изменений с 2026-07-17 | recheck-rejected: воспроизвелось, спор |
