---
id: AT-BUG-042
title: "WorkRatingPanel dispose-save воскрешал запись после Clear all — блокер автоматизации TC-020 снят обходом порядка reload (дефект приложения — BUG-022)"
type: test_debt
debt_kind: flaky_test
severity: major
status: Fixed
found_in: "1.10 (versionCode 11), build 6455af0cfc2c937e81975f59a250476c77aecb73, emulator-5554 — discovered by test-maintainer while reworking TC-020 for BUG-012 (Intended), 2026-08-02"
fixed_in: "test-only (B4, no app rebuild needed): TC-020 automation blocker resolved by test design workaround (R8) + @pytest.mark.live -> @pytest.mark.replay conversion, test-maintainer 2026-08-03"
last_seen_in: "1.10 (versionCode 11), build 6455af0cfc2c937e81975f59a250476c77aecb73"
test_cases: ["TC-020"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-03T01:20:00Z"
updated: "2026-08-03T02:10:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: "fix-verifier:2026-08-03T09:23:51Z"
gitlab_issue: ""
---

# AT-BUG-042 — блокер автоматизации TC-020: dispose-save панели воскрешал запись после Clear all (дефект приложения — `BUG-022`)

> **Навигация (аннотация 2026-08-03T02:10:00Z, финализация D5):** этот файл —
> ИНЖЕНЕРНЫЙ СЛЕД блокера автоматизации и его обхода. Сам дефект приложения
> заведён отдельно: **`bugs/BUG-022.md`** (`type: app_bug`, `Open`) — туда же
> уходит регрессионный замок пользовательского порядка «возврат на Browse →
> reload» при фиксе. `TC-020` этот порядок не заявляет и не проверяет (см.
> блок «Границы проверяемого» в `test-cases/settings/TC-020.md`).
> История разбора ниже (attempt 1/2/3, гипотезы, опровержения) СОХРАНЕНА как
> есть и аннотирована — не переписана.

## Окружение
Долг тестовой системы (`type: test_debt`), обнаружен **test-maintainer** в ходе
переработки `TC-020` под решение владельца `Intended` по `bugs/BUG-012.md`
(бейджи открытых вкладок обновляются только перезагрузкой страницы). Автоматизация
`Then (б)` кейса («после перезагрузки бейдж отражает очищенное состояние») стабильно
НЕ проходит — не из-за неверного оракула/локатора, а из-за отдельного,
независимого от BUG-012 поведения приложения, которое реально СТИРАЕТ эффект
`Clear all ratings` для конкретной работы ещё до того, как reload успевает
что-либо показать.

## Механизм — ПОДТВЕРЖДЕНО эмпирически различающим замером (attempt 3, 2026-08-03T01:20:00Z)

**ИТОГ (attempt 3):** гипотеза критика (шаги 1-6 ниже) ПОДТВЕРЖДЕНА живым
различающим замером после перевода `TC-020` на replay (координатор,
устранение `ESC-015`/сетевого блокера — см. Обсуждение). Инструментированный
`test_clear_all_ratings_badge_resets_after_reload` (`replay=works_multi.mitm`)
дал ДОСЛОВНО:
```
CHECKPOINT 1 (after open_work_page): '900000001|SAVE|1785710320972'
CHECKPOINT 2 (after capture_baseline, luma=134.2098245614035): '900000001|SAVE|1785710320972'
CHECKPOINT 3 (after open_tab Settings, BEFORE clear): '900000001|SAVE|1785710320972'
CHECKPOINT 4 (after clear_all_ratings confirm, still on Settings): ''
CHECKPOINT 5 (immediately after open_tab Browse, BEFORE ensure_visible/luma read): '900000001|SAVE|1785710358931'
CHECKPOINT 6 (after assert_panel_rating_still_selected / ensure_visible+luma): '900000001|SAVE|1785710358931'
CHECKPOINT 7 (immediately after reload_active_webview_page): '900000001|SAVE|1785710358931'
CHECKPOINT 8 (after final deselect attempt): '900000001|SAVE|1785710358931'
```
(`ao3Id|rating|timestamp`, `settings_steps.read_rating_rows()`.)

Прочтение:
- Checkpoint 1→3: строка НЕ меняется (тот же timestamp `...320972`) при уходе
  Browse→Settings — ранний dispose (шаг 2 гипотезы) НЕ производит наблюдаемой
  записи в этом прогоне (детали синхронизации timing вне важности — критично
  то, что он НЕ является источником resurrection, что и утверждала гипотеза).
- Checkpoint 4: `Clear all ratings` корректно очищает таблицу (`''`, 0 строк).
- Checkpoint 5: строка ВОЗВРАЩАЕТСЯ немедленно по возврату на Browse, ДО
  какого-либо `ensure_visible`/чтения luma/reload — НОВЫЙ timestamp
  (`...358931` ≠ `...320972`) — НОВАЯ запись, не остаток старой. `rating=SAVE`
  — ОДНОЗНАЧНО НЕ `onWorkFinished` auto-READ (структурно исключён:
  `works_multi.mitm` не несёт `<div id="chapters">`, см. ниже) — это
  ПОДТВЕРЖДАЕТ шаг 4 гипотезы (транзитный mount+dispose на возврате).
- Checkpoints 6-8: строка стабильна (`SAVE`, тот же timestamp) — reload
  (checkpoint 7) НЕ меняет её (ожидаемо: `onPageLoaded` только ЧИТАЕТ Room в
  `currentPageRating`, не пишет), badge остаётся selected — Then (б) FAILED
  без обхода, как и предсказывала гипотеза.

**Конкурирующая гипотеза (`onWorkFinished` auto-READ, B3) — ИСКЛЮЧЕНА и
структурно, И эмпирически:** `works_multi.mitm`
(`recording_builder.render_work_page_html`) НЕ содержит `<div id="chapters">`
— JS-слушатель `ao3_bridge.js:1117-1147` (`var chaptersDiv =
document.getElementById('chapters'); if (!chaptersDiv) return;`) НЕ МОЖЕТ
присоединиться на этой странице, поэтому `Android.onWorkFinished` физически
не может быть вызван. Воскресшая строка (checkpoint 5) — ОДНОЗНАЧНО
`WorkRatingPanel`-dispose путь (`rating=SAVE`, не `READ`).

**Граница этого исключения (критик, обязательная оговорка):** структурное
исключение auto-READ — свойство REPLAY-ФИКСТУРЫ (`works_multi.mitm` без
`<div id="chapters">`), НЕ свойство приложения: на живой странице AO3
слушатель существует и может сработать. Поэтому структурного аргумента
одного мало — он подпёрт ЭМПИРИКОЙ, независимой от фикстуры: воскресшая
строка несёт `rating=SAVE`, а auto-READ пишет `READ` (различающий замер,
чекпоинты 5-8 выше). Именно значение `rating`, а не отсутствие `#chapters`,
закрывает конкурирующего писателя.

Секции ниже (шаги 1-6 гипотезы, критерий Fixed, история attempt 1/2)
сохранены как есть — они теперь ПОДТВЕРЖДЁННЫЙ механизм, не гипотеза.

### Что ТОЧНО неверно в attempt 1 (исправлено критиком)

Attempt 1 утверждал: dispose при уходе Browse→Settings (ДО `Clear all
ratings`) ставит отложенный re-save, который долетает ПОСЛЕ. Это
противоречит коду: в момент этого dispose строка `work_ratings` ЕЩЁ
существует (`Clear all ratings` ещё не нажат) — `savePanelRating` идёт
веткой `existing != null` (`BrowserViewModel.kt:742-758`) —
**немедленный** `upsertWorkRating` (тот же `rating=SAVE`, что уже в базе,
редундантно, timestamp обновляется) — БЕЗ `pendingPanelSave`/`evalJs`. Эта
ранняя запись НЕ может быть источником resurrection ПОСЛЕ `Clear all`,
потому что она уже завершилась (быстрый прямой `upsertWorkRating`, не
scrape-round-trip) задолго до нажатия «Clear all».

### Уточнённая гипотеза триггера (критик, код-анализ)

1. Пользователь на Browse, панель `RatingMenu` раскрыта и смотрит на
   `rating=SAVE` (`WorkRatingPanel`, `BottomBar.kt:134-167`,
   `DisposableEffect(currentWorkId) { onDispose { if (savedWorkId != null &&
   latestRating != null) onSave(savedWorkId, latestRating, ...) } }`,
   `latestRating` = `rememberUpdatedState(currentPageRating)`).
2. Уход на Settings: `onSelect = { tab -> selectedTab = tab; navExpanded =
   false }` (`MainActivity.kt:426-429`). `AnimatedVisibility(visible =
   selectedTab != AppTab.BROWSE || navExpanded, ...)` (`BottomBar.kt:99-100`)
   — условие СРАЗУ `true` (`selectedTab=SETTINGS != BROWSE`), БЕЗ
   exit-анимации; внутренний `if (selectedTab == BROWSE && isWorkPage)`
   (`BottomBar.kt:105`) сразу `false` — `WorkRatingPanel` размонтируется
   синхронно (не через анимацию), `onDispose` срабатывает с
   `latestRating=SAVE`, строка ЕЩЁ есть → немедленный upsert (см. выше,
   безобидно).
3. Пользователь подтверждает `Clear all ratings` — `work_ratings.deleteAll()`
   — таблица пуста.
4. Возврат на Browse: тот же `onSelect` — `selectedTab=BROWSE; navExpanded =
   false` ОДНИМ обновлением состояния. `AnimatedVisibility`'s `visible`
   переходит `true → false` (`selectedTab==BROWSE` теперь true, `navExpanded`
   false) — НАЧИНАЕТСЯ EXIT-анимация. Во время exit `AnimatedVisibility`
   держит контент composed, и он пересчитывается с ТЕКУЩИМИ (не
   замороженными) значениями внешних переменных: `if (selectedTab==BROWSE &&
   isWorkPage)` теперь `true` (`selectedTab` уже флипнулся на `BROWSE`) —
   `WorkRatingPanel` МОНТИРУЕТСЯ ЗАНОВО на время exit-анимации, читая
   ТЕКУЩИЙ `currentPageRating` (`SAVE` — `onPageLoaded` ещё не вызывался,
   reload не делался). Когда exit-анимация завершается, `AnimatedVisibility`
   диспозит контент целиком — `WorkRatingPanel`, только что смонтированная,
   диспозится СНОВА, `onDispose` срабатывает с `latestRating=SAVE`. Теперь
   строка УЖЕ удалена (`Clear all` шага 3) — `existing == null` →
   `BrowserViewModel.kt:759-761`: `updateTab { pendingPanelSave =
   Triple(rating, comment, tags) }` + `evalJs(tab.id, workInfoJs(workId))`.
5. Отложенная запись из шага 4 **не планируется до возврата на Browse** (не
   «зависает, пока WebView не foreground» — это утверждение attempt 1
   ПРОТИВОРЕЧИТ коду: `BrowserScreen` всегда композится
   (`MainActivity.kt:471-472`, «Browser is always rendered to keep WebViews
   alive»), `workInfoJs` — синхронный JS, `evalJs` = `webView.post` на уже
   присоединённый View, ничего структурно не блокирует его до foreground).
   Корректная формулировка: САМ ТРИГГЕР (транзитный mount+dispose шага 4) НЕ
   СУЩЕСТВУЕТ до момента возврата на Browse — раньше просто нечему было
   ставить `pendingPanelSave`, потому что панель не диспозилась с
   `existing==null` ни разу до этого момента.
6. Callback `onRateWorkRequested` (`BrowserViewModel.kt:1008-1054`)
   БЕЗУСЛОВНО создаёт новую строку `repo.upsertWorkRating(WorkRating(...,
   rating=rating, ...))` (1027-1040) и НАПРЯМУЮ выставляет `currentPageRating
   = rating` в состоянии таба (1044) — не проверяя, не изменилось ли
   состояние базы за это время.

### Конкурирующий писатель — ЗАКРЫТО различающим замером (была гипотеза B3)

> **Аннотация 2026-08-03 (текст ниже сохранён в исходном виде — как он был
> написан, когда замера ещё не было):** конкурирующий писатель `onWorkFinished`
> auto-READ ИСКЛЮЧЁН — различающий замер (чекпоинты 1-8 в разделе «Механизм»
> выше) показал `rating=SAVE` на КАЖДОЙ наблюдавшейся воскресшей строке,
> никогда `READ`. Требование ниже («живой различающий замер обязателен ПЕРЕД
> тем, как формулировать критерий Fixed окончательно») — ВЫПОЛНЕНО
> 2026-08-03T01:20:00Z, до перевода записи в `Fixed`; порядок соблюдён, а не
> обойдён.

`onWorkFinished` (`BrowserViewModel.kt:1198-1224`) + auto-mark-as-read
JS-слушатель (`ao3_bridge.js:1114-1147`, `window.addEventListener('scroll',
onScroll)`, срабатывает когда низ `#chapters` виден в вьюпорте — В Т.Ч. НА
scroll-restore при загрузке страницы, без явного пользовательского скролла)
пишет `rating=READ` (НЕ `SAVE`) для работы БЕЗ существующего рейтинга
(`if (existing?.rating != null) return@launch` — guard на «есть рейтинг»,
пропускает запись, если рейтинг уже есть; ПОСЛЕ `Clear all` рейтинга нет —
guard НЕ блокирует). Если тестовая работа (`word_count=4200`, короткая)
после reload оказывается достаточно короткой/проскроллена так, что низ
контента виден — эта функция МОЖЕТ быть источником resurrection, а не
dispose re-save из шага 4-6 выше. **Различить эти два механизма может ТОЛЬКО
значение `rating` воскресшей строки** (`SAVE` → dispose re-save гипотеза;
`READ` → auto-mark-as-read, отдельный, возможно ПРЕДНАМЕРЕННЫЙ механизм) —
не `COUNT`. Это ключевая причина, почему живой различающий замер (заблокирован
ESC-015) обязателен ПЕРЕД тем, как формулировать критерий Fixed окончательно.

### Связь с BUG-012

`BUG-012` (Intended) — про отсутствие broadcast к УЖЕ ОТКРЫТОЙ вкладке
(виджет не узнаёт об очистке без reload) — это ИСТОЧНИК стухшего значения:
именно ПОТОМУ, что `currentPageRating` не обновляется без `onPageLoaded`
(решение владельца — Intended, не баг), шаг 4 выше читает СТАРЫЙ `SAVE` в
момент транзитного mount, а не актуальный `null`. Не будь `BUG-012`
Intended-решения (т.е. будь broadcast к открытым вкладкам реализован),
`currentPageRating` обнулился бы сразу при `Clear all`, и dispose шага 4
captured бы `latestRating=null` — `onSave`/`savePanelRating` не вызвался бы
вовсе (`if (savedWorkId != null && latestRating != null)` — guard на
`onDispose`). Т.е. `AT-BUG-042` (если гипотеза dispose re-save подтвердится)
— ПРОИЗВОДНЫЙ эффект решения `BUG-012` Intended, не независимый от него
дефект, как ошибочно утверждал attempt 1 — хотя технически это ДРУГОЙ
код-путь (`WorkRatingPanel`/`savePanelRating`, не
`SettingsViewModel.confirmClearAll`).

### Обход (R8) — ПОДТВЕРЖДЁН эмпирически (attempt 3)

Триггер — транзитный mount+dispose ИМЕННО на возврате на Browse (шаг 4).
Если к этому моменту `currentPageRating` уже `null` (обновлён `onPageLoaded`
РАНЬШЕ этого возврата), `onDispose`'s guard `latestRating != null`
(`BottomBar.kt:159-167`) пропускает `onSave` — resurrection не происходит.

`BrowserScreen` (и его WebView) композится БЕЗУСЛОВНО независимо от
`selectedTab` (`MainActivity.kt:471-472`, «Browser is always rendered to keep
WebViews alive») — `window.location.reload()` можно выполнить, ПОКА тест ещё
на Settings, ДО возврата на Browse. Реализовано в
`test_clear_all_ratings_badge_resets_after_reload`: `settings_steps.
reload_active_webview_page(driver)` вызывается СРАЗУ после `clear_all_ratings`,
ДО `app_steps.open_tab(driver, "Browse")`.

Witness (дословно, различающий замер подтверждает НУЛЕВУЮ resurrection на
каждом чекпоинте после этой перестановки):
```
CHECKPOINT 4 (after clear_all_ratings confirm, still on Settings): ''
CHECKPOINT 4b (immediately after reload, STILL on Settings): ''
CHECKPOINT 5 (immediately after open_tab Browse, BEFORE ensure_visible/luma read): ''
CHECKPOINT 8 (after final deselect attempt): ''
PASSED
```
Тест зелёный 3 раза подряд (см. Обсуждение/Верификация ниже).

## Наблюдаемый эффект — эмпирика attempt 1 (ПРОМЕЖУТОЧНАЯ, не переизмерена в attempt 2)

**Пометка координатора/test-maintainer (B4, attempt 2): цитата ниже — из
attempt 1, использует `COUNT` (не различающий замер) и ссылается на функцию
`test_clear_all_ratings_badge_persists_until_reload`, которой БОЛЬШЕ НЕ
СУЩЕСТВУЕТ в кодовой базе (переименована/разделена на
`test_clear_all_ratings_badge_persists_without_reload` +
`test_clear_all_ratings_badge_resets_after_reload` при том же rework). Цитата
сохранена как исторический артефакт находки, НЕ как подтверждённый факт
точного шага — attempt 1 ТАКЖЕ противоречиво утверждал в разных прогонах то
«COUNT=1 сразу после возврата на Browse», то «COUNT=0 сразу после возврата,
1 только на следующем шаге» — какое из двух верно (и с каким `rating`),
живым различающим замером НЕ переизмерено (ESC-015 заблокировал попытку
attempt 2).**

```
tests/test_settings.py::test_clear_all_ratings_badge_persists_until_reload FAILED
...
AssertionError: ожидали 0 рейтингов, в БД: 1
steps\settings_steps.py:255: AssertionError
```

Сценарий-описание attempt 1 (тоже промежуточное, требует переизмерения):
работа W с рейтингом Loved открыта → уход в Settings → `Clear all ratings`
подтверждён (`COUNT=0` сразу после подтверждения) → возврат на Browse —
`COUNT` снова `1` в ОДНОМ ИЗ последующих шагов (точный шаг противоречив
между прогонами attempt 1, см. выше) — РАНЬШЕ, чем какой-либо явный reload.

## Критерий готовности (Fixed) для ЭТОГО test_debt — ДОСТИГНУТ вариантом (c)

Данный test_debt закрывает БЛОКЕР автоматизации, не обязательно правит сам
механизм приложения (правка `app-under-test/` вне мандата
test-maintainer/test-automator, если корень — в приложении). Fixed для ЭТОЙ
записи означал один из:
- (a) живой различающий замер подтвердил гипотезу dispose re-save И
  разработчик исправил механизм в приложении — НЕ ВЫБРАН (правка
  `app-under-test/` вне мандата этого прохода);
- (b) конкурирующий механизм — ИСКЛЮЧЁН (см. «Механизм» выше: структурно и
  эмпирически, `rating` воскресшей строки = `SAVE`, никогда `READ`);
- **(c) ДОСТИГНУТ 2026-08-03T01:20:00Z:** test-maintainer нашёл ОБХОД
  тестовым дизайном — reload ДО возврата на Browse (см. «Обход (R8)» выше),
  эмпирически подтверждённый различающим замером (0 resurrection на каждом
  чекпоинте) и 3×зелёным прогоном `test_clear_all_ratings_badge_resets_after_reload`.
  `TC-020` выведен из `Blocked` в `Review` легальным переходом
  (`test-cases/settings/TC-020.md`).

  **ЧТО ИМЕННО СНЯЛ ОБХОД (честная формулировка, финализация
  2026-08-03T02:10:00Z по вердикту критика раунда 2 и решению Lead BL-1):**
  обход снял ТРЕБОВАНИЕ ПРОВЕРЯТЬ ПОЛЬЗОВАТЕЛЬСКИЙ ПОРЯДОК («возврат на
  Browse → reload») В РАМКАХ `TC-020` — кейс переформулирован под реально
  проверяемое (перезагрузка перечитывает рейтинг из Room), и в его границах
  автоматизация больше ничем не блокирована. Обход НЕ означает, что дефект
  исчез или что порядок работает: **носитель пользовательского порядка —
  `bugs/BUG-022.md`** (`app_bug`, `Open`); регрессионный замок этого порядка
  ставится при фиксе `BUG-022` и принадлежит ему, не `TC-020`. `test_debt`
  закрыт `Fixed` ровно в этом смысле: блокер АВТОМАТИЗАЦИИ снят, механизм
  приложения НЕ тронут (ни строки в `app-under-test/`) и остаётся открытым
  под своим номером.

### Связи

- **`bugs/BUG-022.md`** (`app_bug`, `Open`, major) — САМ дефект приложения,
  выделенный из этой записи 2026-08-02: dispose-save `WorkRatingPanel`
  воскрешает удалённую `Clear all ratings` запись при возврате на Browse.
  Заведение app_bug — carve-out триажа (bug-reporter/координатор), не
  test-maintainer; здесь остаётся инженерный след и witness. Регрессионный
  замок пользовательского порядка — за `BUG-022`.
- **`test-cases/settings/TC-020.md`** — кейс, чью автоматизацию блокировал
  этот долг; блок «Границы проверяемого» кейса ссылается обратно на
  `BUG-022`.
- **`bugs/BUG-012.md`** (`Intended`) — источник стухшего значения на панели,
  см. раздел «Связь с BUG-012» ниже.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-03 (test-maintainer, self-run — не fix-verifier, для fix-verifier см. B4 "не ждёт сборку приложения") | 1.10 (versionCode 11), replay `works_multi.mitm` | `TC-020` обе функции: `test_clear_all_ratings_badge_persists_without_reload` (3× PASSED, ~55-59с каждый), `test_clear_all_ratings_badge_resets_after_reload` (3× PASSED, ~55-72с каждый, включая 1 инструментированный прогон с различающим замером) | Все 6 прогонов PASSED, `PYTEST_EXIT=0` каждый | Fixed-критерий (c) достигнут — блокер автоматизации снят обходом; ждёт официальной верификации fix-verifier/test-reviewer (F1) |
| 2026-08-03T02:10:00Z (test-maintainer Opus, финализация D5 — перепрогон ПОСЛЕ правок оракулов) | 1.10 (versionCode 11), replay `works_multi.mitm` | `TC-020` обе функции одним прогоном, 3 раза подряд | `2 passed, 6 deselected` в 103.92s / 101.98s / 108.77s, `PYTEST_EXIT=0` каждый | Правки оракулов (бюджет 10с, опрашивающий якорь Given, якорь состояния БД) не поколебали зелёный; каждая изменённая проверка предварительно доказана красной пробой (см. Обсуждение) |

## Обсуждение

**2026-08-02T15:20:00Z — test-maintainer (Sonnet), заведение блокера при
переработке TC-020 под BUG-012 (Intended):**

Обнаружено при попытке автоматизировать `Then (б)` («после перезагрузки бейдж
отражает очищенное состояние») переработанного `TC-020`. Первая гипотеза (Chromium
не триггерит `onPageFinished` на навигацию к тому же URL) подтвердилась и решена
в рамках рework (новый шаг `settings_steps.reload_active_webview_page` —
`window.location.reload()` вместо повторной навигации, подтверждено через
`browser_steps.mark_no_reload_baseline`/`assert_no_reload_since`: маркер
теряется, реальный reload происходит). Но даже с настоящим reload `Then (б)`
не проходит — раскопки (adb sqlite `SELECT COUNT(*) FROM work_ratings`,
серия прогонов с точечными diagnostic-чекпоинтами) показали ПОЛНОСТЬЮ ДРУГУЮ
причину: сама база откатывается НАЗАД к состоянию до `Clear all ratings`,
раньше, чем reload успевает что-либо прочитать. Причина — механизм, описанный
выше, подтверждённый прямым чтением `BottomBar.kt`/`BrowserViewModel.kt`
(`app-under-test/`, только ЧТЕНИЕ — правок туда НЕ вносилось).

Это НЕ то же самое, что `BUG-012` — независимый дефект в том же
рейтинг-панельном коде. Правка `app-under-test/` вне мандата (не
test-automator/test-maintainer scope) — оставляю продуктовое решение
bug-reporter/владельцу; эта запись фиксирует БЛОКЕР автоматизации `TC-020`, не
формулирует app_bug сама (carve-out по инструкции test-maintainer, не
расширяю scope, D-0037).

`TC-020` переведён в `Blocked`/`dev_answer` до триажа этого блокера — см.
`test-cases/settings/TC-020.md`. Автоматизирована и подтверждена зелёной
только `Then (а)` часть Given-When-Then кейса (не зависит от этого дефекта —
наблюдаемый результат совпадает с ожидаемым независимо от того, воскрес ли
рейтинг в фоне или нет; badge остаётся selected ЛИБО из-за отсутствия
broadcast [BUG-012], ЛИБО из-за resurrection [этот баг] — оба случая дают
одинаковую наблюдаемую картинку, но `Then (а)` не заявляет ПРИЧИНУ, только
наблюдаемый факт).

**История ревизий (для навигации по документу):** секция «Механизм» выше —
attempt 2 (2026-08-03), заменяет ПЕРВОНАЧАЛЬНУЮ версию attempt 1 целиком
(хронология «dispose до Clear all» была ФАКТИЧЕСКИ НЕВЕРНОЙ — исправлено
критик-вердиктом приёмки, см. запись attempt 2 ниже). Секция «Наблюдаемый
эффект» ниже неё — НЕПЕРЕИЗМЕРЕННАЯ эмпирика attempt 1, помечена как
промежуточная.

**2026-08-03T00:20:00Z — test-maintainer (Sonnet), attempt 2 по
критик-вердикту приёмки (6 блокеров, D5-сдача):**

Критик вернул attempt 1 с вердиктом «доработать» — шесть блокеров/рекомендаций
(B1-B6, R1-R2, R8). Разобрано:

- **B1+B3 (различающий замер + хронология)**: критик указал ДВЕ проблемы —
  (1) COUNT не различает dispose re-save (`SAVE`) от конкурирующего
  `onWorkFinished` auto-READ (`BrowserViewModel.kt:1198-1224` +
  `ao3_bridge.js:1114-1147`, auto-mark при видимом низе работы, В Т.Ч. на
  scroll-restore); (2) хронология attempt 1 («dispose до Clear all →
  pendingPanelSave») ПРОТИВОРЕЧИТ коду: в момент раннего dispose (уход
  Browse→Settings) строка ЕЩЁ существует → ветка `existing != null`
  (`BrowserViewModel.kt:742-758`, немедленный upsert), НЕ `pendingPanelSave`.
  Уточнённая (критиком) гипотеза триггера — транзитный mount+dispose
  `WorkRatingPanel` ВО ВРЕМЯ exit-анимации `AnimatedVisibility` при ВОЗВРАТЕ
  на Browse (`onSelect` ставит `navExpanded=false` ОДНОВРЕМЕННО с
  `selectedTab=BROWSE`, что переворачивает `visible` true→false, но контент
  внутри exit-анимации пересчитывается с уже новым `selectedTab=BROWSE` —
  панель монтируется и тут же диспозится снова). Разобрал код построчно
  (`MainActivity.kt:426-429`, `BottomBar.kt:99-105`) — гипотеза
  МЕХАНИСТИЧЕСКИ состоятельна, подробности в секции «Механизм» выше.
  **НЕ ПОДТВЕРЖДЕНА эмпирически** — живой прогон с различающим замером
  (`SELECT ao3Id, rating, timestamp`, инструментирован в тесте, checkpoints
  1-8) заблокирован деградацией среды раньше, чем удалось получить хоть
  одну строку живых данных (см. ESC-015 ниже). Промежуточная цитата witness
  attempt 1 помечена как таковая (ссылается на несуществующую после
  переименования функцию, использует COUNT, шаг resurrection противоречив
  между собственными прогонами attempt 1 — см. секцию «Наблюдаемый эффект»).
- **B2 (формулировка)**: убрано ложное утверждение «зависает пока WebView не
  foreground» (противоречит `MainActivity.kt:471-472` — Browser всегда
  композится; `evalJs` — `webView.post` на присоединённый View, ничего не
  блокирует структурно). Заменено на корректную формулировку критика:
  отложенная запись НЕ ПЛАНИРУЕТСЯ до возврата на Browse (триггер — сам факт
  транзитного dispose на возврате, не «зависшая до foreground» очередь).
- **Критерий Fixed переписан**: убран нерабочий пример «отменять
  pendingPanelSave при clearAllRatings()» (pending СОЗДАЁТСЯ уже ПОСЛЕ
  очистки — отменять на момент очистки нечего, там pending ещё не существует).
  Добавлен вариант (c) — обход тестовым дизайном (R8 координатора), связка с
  `BUG-012` явно прописана (Intended-решение — источник стухшего значения,
  которое читает транзитный mount).
- **B5/B6/R1/R2 (code-level, НЕ требуют живого замера)** — применены сразу:
  `settings_steps.py:194` falsy-zero (`timeout or ...` →
  `timeout if timeout is not None else ...`); `assert_panel_rating_still_selected`
  переписан на `waits.assert_holds_for` (бюджет 4с) вместо одноразового
  снимка; добавлен `assert_baseline_indicates_selected` (R1, якорь Given —
  baseline обязан быть ниже порога деселекта 178.9); `Then (а)` в
  `test_settings.py`/`TC-020.md` избавлен от причинных claim'ов (R2) —
  утверждается только наблюдаемый факт.
- **B4 (противоречие)**: разрешено явной пометкой — цитата attempt 1
  остаётся ПРОМЕЖУТОЧНОЙ, живая переверка НЕ проведена (не «одна из двух
  верна», а «ни одна не подтверждена повторно»).

**Fail-fast (ESC-015, `state/escalations.md`):** попытка живого прогона
инструментированного `test_clear_all_ratings_badge_resets_after_reload`
(снят skip для эксперимента) упёрлась в `ReadTimeoutError` (read
timeout=120с) на САМОМ ПЕРВОМ driver-вызове (`wait_app_ready`/`current_url`)
— ПОДТВЕРЖДЕНО 3 РАЗА подряд идентично (включая после чистого рестарта
Appium `Stop-NodeProcesses`+`Start-Appium`, И на уже стабильно зелёном
`test_clear_all_ratings_badge_persists_without_reload`, чей код НЕ менялся
между зелёными и красными прогонами). Позитивный контроль: non-live тест
(та же driver-сессия, без реальной AO3-навигации) прошёл чисто за 35с —
Appium/UiAutomator2-сессия САМА ПО СЕБЕ здорова; первоначальная гипотеза
«automation-сервер не виден в `ps -A`» (первый замер) была ПРЕЖДЕВРЕМЕННОЙ
без этого контроля. Единственная переменная между здоровым и больным
прогонами — реальная загрузка AO3 в WebView: похоже на ПОВТОР `ESC-009`
(upstream AO3/сетевой транзит хоста), не Appium/UiAutomator2-процесс — вне
мандата test-maintainer (системная сеть хоста, не test-maintainer чинит
CLAUDE.md «Fail-fast среды»; полный разбор с позитивным контролем —
`state/escalations.md` `ESC-015`). Skip восстановлен на
`test_clear_all_ratings_badge_resets_after_reload`, причина обновлена
(ссылается на ESC-015 + этот файл). Живая верификация гипотезы
dispose-re-save vs auto-READ, красная проба нового `assert_holds_for`-оракула
и 3×зелёный прогон — ОТЛОЖЕНЫ до починки сети хоста (не мой мандат).

**R3/R4 (прозаическая пометка, схемы НЕ трогаю — очередь координатора):**
`debt_kind: flaky_test` — не идеальное совпадение (это не флаки в смысле
«тест иногда падает без причины», а детерминированная — по гипотезе —
консеквенция реального поведения приложения; ближайший из существующих
enum-значений `schemas/bug.schema.yaml`, ничего точнее вроде
`app_behavior_blocker`/`env_race` в перечне нет). Аналогично
`blocked_reason: dev_answer` у `TC-020` (`schemas/test-case.schema.yaml`) —
кейс ждёт не буквально «ответа разработчика», а разбора связки
test_debt+возможный app_bug; ближайшее из существующих значений. Оба
зазора — не мой мандат менять enum (D-0037, гейт 4-вопросов CLAUDE.md п.10
на изменение схемы), оставляю координатору как потенциальный «новая ось
словаря» пункт.

**2026-08-03T01:20:00Z — test-maintainer (Sonnet), attempt 3 (координаторский
план: перевод TC-020 с live на replay устраняет ESC-015/R-03):**

Координатор диагностировал `ESC-015` как повтор `ESC-009`-класса: гостевой
Chromium (qemu slirp) предпочитает IPv6 независимо от хостовой
prefix-policy, IPv6-транзит хоста мёртв — live-класс заблокирован до починки
сети, replay-класс здоров (не зависит от хостового транзита, идёт через
`mitmdump` на хосте с уже починенным IPv4-first `getaddrinfo`). Поручение:
оценить перевод `TC-020` на replay.

Оценка: сценарий `TC-020` НЕ проверяет реальное содержимое AO3-страницы —
бейдж/панель управляются Room, не DOM; единственные сетевые точки —
начальная навигация (`open_work_page`) и `reload()`. `works_multi.mitm`
(`ALL_WORKS[0]=W.LOVED`, тот же `ao3_id`/`url`, что использует
`loved_work_seeded`) уже несёт нужную work-страницу,
`server_replay_reuse=true` отдаёт тот же ответ на повторные запросы (нужно
для reload). Перевод сделан на ОБЕИХ функциях
(`@pytest.mark.live` → `@pytest.mark.replay`,
`@pytest.mark.parametrize("replay", [rb.WORKS_MULTI_FILENAME], indirect=True)`,
`app_steps.wait_app_ready` → `wait_ui_ready` — домашняя страница не
записана, ждать её означало бы уйти в live).

Witness (дословно): `test_clear_all_ratings_badge_persists_without_reload`
прошёл ЧИСТО с первого прогона (`1 passed in 58.93s`, `PYTEST_EXIT=0`) —
БЕЗ каких-либо изменений сети/Appium/эмулятора, только смена маркера. Это
эмпирически подтвердило координаторский диагноз (изоляция «non-live 35с
зелёный, live висит» точно предсказала «replay зелёный»).

С сетью решённой (замер на replay), выполнен весь остаток плана attempt 2:

1. **Различающий эксперимент**: инструментированный `test_clear_all_ratings_
   badge_resets_after_reload` (checkpoints 1-8, `settings_steps.
   read_rating_rows`) дал дословный результат, приведённый в разделе
   «Механизм» выше — гипотеза критика (транзитный dispose на возврате на
   Browse) ПОДТВЕРЖДЕНА, конкурирующая гипотеза (`onWorkFinished` auto-READ)
   ИСКЛЮЧЕНА и структурно (`works_multi.mitm` без `#chapters`), и
   эмпирически (`rating=SAVE`, не `READ`, на воскресшей строке).
2. **R8-обход**: reload ДО возврата на Browse (пока `BrowserScreen`
   композится безусловно, `MainActivity.kt:471-472`) — различающий замер
   подтвердил 0 resurrection на каждом чекпоинте после перестановки (раздел
   «Обход (R8)» выше). Реализовано как финальная версия теста (без
   diagnostic-print'ов — они сделали свою работу, оставлен чистый
   Given-When-Then).
3. **Красная проба нового `assert_holds_for`-оракула** (`assert_panel_
   rating_still_selected`): байтовая копия `test_settings.py` снята ДО
   пробы (правило отката п.8 CLAUDE.md,
   `scratchpad/test_settings.py.before_redprobe`); временный вызов с
   `selected_luma * 0.01` дал `AssertionError` (`luma=134.2`,
   `threshold=1.8`) — оракул способен падать; откат подтверждён побайтовым
   `diff` (пусто) с байтовой копией.
4. **3×зелёный**: обе функции `TC-020` прогнаны по 3 раза подряд, все 6
   прогонов PASSED (`PYTEST_EXIT=0` каждый; полные цифры — таблица
   «Верификация» выше).

`TC-020` выведен из `Blocked` в `Review` (`test-cases/settings/TC-020.md`,
`*→Review by [test-maintainer]`). `AT-BUG-042` переведён `Open → Fixed`
(guard-переход B4, `schemas/transitions.yaml` — `test_debt`, сборка
приложения не нужна): блокер автоматизации снят обходом; запись ОСТАЁТСЯ
открытым свидетельством реального дефекта приложения (см. критерий Fixed
выше) — решение о заведении `BUG-0xx`/диспатче bug-reporter за
координатором. Правок в `app-under-test/` НЕ вносилось (только чтение).
`state/escalations.md` `ESC-015` дополнена диагнозом координатора и
подтверждающей запиской (статус `open` — сама сеть не починена, кейс
`TC-020` больше от нее не зависит). Изменённые файлы: `bugs/AT-BUG-042.md`
(этот), `bugs/BUG-012.md` (Обсуждение), `test-cases/settings/TC-020.md`,
`framework/tests/test_settings.py`, `state/escalations.md`. Эмулятор/Appium
оставлены живыми.

**2026-08-03T02:10:00Z — test-maintainer (Opus, эскалация правила 6), финализация
D5 по вердикту критика раунда 2 и решению Lead (BL-1/BL-2):**

Критик показал расхождение НОСИТЕЛЕЙ: тест Then (б) делал reload ДО возврата на
Browse (обход), а кейс описывал пользовательский порядок «возврат → reload», в
котором ожидание на текущей сборке ЛОЖНО. Развязка проведена по решению Lead:

1. **`test-cases/settings/TC-020.md`**: Then (б) переформулирован под реально
   проверяемое («перезагрузка перечитывает рейтинг из Room; в тесте reload — ДО
   возврата на Browse»); добавлен блок «Границы проверяемого» с явным
   утверждением, что в пользовательской последовательности ожидание НЕ
   выполняется (`BUG-022`) и что регрессионный замок этого порядка —
   за `BUG-022`, не за TC-020. Заголовок кейса сверен: сформулирован от
   ОЖИДАЕМОГО ПОВЕДЕНИЯ («…сохраняют состояние до перезагрузки; после reload —
   сброшены»), не от дефекта — оставлен без изменений.
2. **`framework/tests/test_settings.py`**: докстринг Then (б) называет причину
   порядка шагов честно — ОБХОД подтверждённого дефекта приложения `BUG-022`, с
   явной оговоркой «этот тест не проверяет пользовательский порядок и не должен
   трактоваться как его замок».
3. **Эта запись**: `title`, раздел конкурирующего писателя, критерий Fixed (c) и
   новый раздел «Связи» приведены в соответствие (история НЕ стёрта —
   аннотирована).

Мелочи критика (замечания 1-3) — решения и красные пробы (дословно):

- **(1) `settings_steps.read_rating_rows()` был мёртвым кодом — ЗАДЕЙСТВОВАН**
  (не удалён): поверх него добавлен шаг `assert_rating_rows_empty()`, который
  тест Then (б) вызывает ПЕРЕД reload как якорь состояния БД. Мотив выбора:
  сырые строки различают писателей (`SAVE` vs `READ`), поэтому провал Then (б)
  остаётся отличим от «в Room по-прежнему лежит рейтинг» (BUG-022-класс) —
  `COUNT` этого не даёт; заодно helper остаётся живым для верификации `BUG-022`.
  Красная проба (вызов ДО `Clear all ratings`, дословно):
  ```
  E  AssertionError: ожидали пустую work_ratings после Clear all ratings,
     в БД строки: '900000001|SAVE|1785713779763'
  ```
- **(2) Бюджет `assert_panel_rating_still_selected` поднят 4.0с → 10.0с**
  (вариант «поднять», не «обосновать 4с»): 10с = таймаут парной ПОЗИТИВНОЙ
  `rating_steps.assert_panel_rating_deselected`; асимметрия делала негатив
  слабее позитива. Красная проба СЕМАНТИКИ бюджета (host-side, нарушение
  приходит на 6-й секунде; `waits.py` не менялся — проверялось именно значение):
  ```
  budget_s=4.0: PASSED (нарушение НЕ замечено) [прошло 4.0с]
  budget_s=10.0: AssertionError: состояние не удержано весь бюджет [прошло 6.0с]
  ```
  Плюс красная проба самого оракула на устройстве (искажённый baseline,
  новый бюджет по умолчанию):
  ```
  E  AssertionError: кнопка рейтинга SAVE неожиданно посветлела до 134.2
     (порог деселекта 1.8, baseline выбранного=1.3) после Clear all ratings БЕЗ reload
  ```
- **(3) `assert_baseline_indicates_selected` переведён с жёсткого снимка на
  ОПРОС с бюджетом** (образец — опрашивающий сиблинг
  `rating_steps.assert_rating_button_selected`): `onPageLoaded` читает Room
  асинхронно, `animateColorAsState` доигрывает 180мс — ранний снимок давал бы
  ложно-красный на верном Given. Шаг ВОЗВРАЩАЕТ осевшее значение, и baseline
  берётся именно оно (ранний светлый снимок завысил бы порог деселекта и
  ослабил бы обе парные проверки). Красная проба (порог 1.0, дословно):
  ```
  E  AssertionError: baseline luma=134.2 (первичный замер 134.2, опрос 10с,
     наблюдения: [134.2, 134.2, 134.2, 134.2, 134.2, 134.2, 134.2, 134.2,
     134.2, 134.2, 134.2, 134.2]) НЕ ниже порога деселекта 1.0 — похоже,
     Given кейса не установил кнопку рейтинга в выбранное состояние
  ```
  (12 наблюдений за 10с — доказано, что шаг реально опрашивает весь бюджет и
  падает, а не возвращается молча.)

Временная порча файла под красные пробы — по правилу п.8 CLAUDE.md: `git status
--porcelain` снят ДО (файл был `M` — незакоммиченный дифф в дереве, `git
checkout` был бы нелегален), байтовая копия
`scratchpad/test_settings.py.before_redprobe_opus`; откат — восстановлением
копии, сверка дословно: `hash-object` = `2c6773dfe2994e3d2152a5b9d272f6a0766aaf7a`
(совпал с зафиксированным до порчи), `diff` с копией пуст, `grep -c RED-PROBE` = 0.

Перепрогон после правок: `2 passed, 6 deselected` три раза подряд
(103.92s/101.98s/108.77s, `PYTEST_EXIT=0` каждый) — строка таблицы Верификации
выше. `validate_frontmatter` и `arch_check` — по 0 ошибок / 0 предупреждений.
Правок в `app-under-test/` не вносилось; `bugs/BUG-022.md`, `bugs/BUG-012.md`,
`scripts/`, `state/` не трогались.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [x] Проверены дубликаты среди открытых test_debt: не пересекается с
  AT-BUG-038/040/041 (те — EOL/partial-writer класс в `scripts/`, эта запись —
  про `app-under-test/` рейтинг-панель, другая ось)
- [x] Severity обоснована влиянием: major — блокирует полную автоматизацию
  `TC-020` (Then б недостижим), и является потенциальной потерей данных
  («Clear all ratings» не гарантированно очищает БД для недавно просматриваемых
  работ) — не minor-косметика
- [x] Приложены материалы: цитаты кода (`BottomBar.kt`, `BrowserViewModel.kt`),
  дословный вывод failing pytest witness, описание воспроизведения через adb sqlite
- [x] Нет изменений кода приложения (только чтение при диагностике)
