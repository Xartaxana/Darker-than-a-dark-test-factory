---
key: "AT-BUG-074"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "render_work_page_html не несёт #chapters/.userstuff.module ни узлов dd.fandom/dd.words — блокирует TC-256 (auto-READ при дочитывании, onWorkFinished)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-256", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T10:20:00Z"
updated: "2026-08-15T10:20:00Z"
archived: false
resolution: null
---

# render_work_page_html не несёт #chapters/.userstuff.module ни узлов dd.fandom/dd.words — блокирует TC-256 (auto-READ при дочитывании, onWorkFinished)

_Спроецировано из `bugs/AT-BUG-074.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-074 — Work-страница replay-фикстуры не несёт узлов, нужных JS auto-mark-as-read (`onWorkFinished`)

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture`). Текущая тестируемая сборка — актуальная на
момент заведения (59be96c6, коммит фикса `07805a9f`, `bugs/BUG-067.md`).
Класс СМЕЖНЫЙ с `AT-BUG-030` (тот же паттерн «`render_work_page_html` не
несёт нужную разметку тела работы») и с `AT-BUG-061` (тот же паттерн «нужны
узлы `dd.fandom`/`dd.words`, которых текущая функция не несёт»), но НЕ
дубликат ни одного — другая недостача узлов (`#chapters`/`.userstuff.module`,
конкретно под JS-слушатель скролла auto-READ) и другой блокируемый кейс.

## Суть долга

`bugs/BUG-067.md` (фикс `07805a9f`, сборка 59be96c6) требует регресс-замка
на поведение `Ao3JsBridge.onWorkFinished` (`BrowserViewModel.kt:1292-1326`):
при дочитывании скачанной работы без рейтинга рейтинг становится `READ`,
`downloadPath` и непустые локальные метаданные сохраняются (класс дефекта —
тот же, что `BUG-021`/`BUG-048`, регресс-замки которых — `TC-151`/`TC-152`).
`test-designer` спроектировал `TC-256` под этот Then — физически выполнить
его сценарий (JS-событие «дочитано») сейчас НЕЛЬЗЯ.

Триггер срабатывания — JS-слушатель `ao3_bridge.js:1164-1197`:

```js
(function () {
    var pathMatch = window.location.pathname.match(/^\/works\/(\d+)/);
    if (!pathMatch) return;
    var chaptersDiv = document.getElementById('chapters');
    if (!chaptersDiv) return;                                    // (1)
    var workId = pathMatch[1];

    function isLastPage() {
        if (!window.location.pathname.match(/\/chapters\//)) return true;
        return !Array.from(document.querySelectorAll('li a')).some(function (a) {
            return a.textContent.trim() === 'Next Chapter →';
        });
    }

    var contentDivs = chaptersDiv.querySelectorAll('.userstuff.module');
    var lastContent = contentDivs[contentDivs.length - 1] || chaptersDiv;  // (2)

    function onScroll() {
        if (lastContent.getBoundingClientRect().bottom > window.innerHeight) return;
        if (!isLastPage()) return;
        var title = (document.querySelector('h2.title.heading') || {}).textContent || '';
        var author = (document.querySelector('h3.byline a') || {}).textContent || '';
        var fandom = (document.querySelector('dd.fandom a') || {}).textContent || '';   // (3)
        var wordCount = ((document.querySelector('dd.words') || {}).textContent || '0') // (4)
            .replace(/[,\s]/g, '');
        Android.onWorkFinished(workId, title.trim(), author.trim(), fandom.trim(), wordCount);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
})();
```

`framework/data/recording_builder.py::render_work_page_html` (`:591-636`,
потребитель — `listing_basic.mitm`, ТА ЖЕ запись, что использует Given
`TC-151`/`TC-152`/`TC-256`) сегодня несёт только:
- `h2.title.heading` — есть, совместим с (не нужна правка);
- `h3.byline.heading a[rel=author]` — есть, совпадает с селектором `h3.byline
  a` (составной класс `.byline` матчит `<h3 class="byline heading">`) — не
  нужна правка;
- `h5.fandom.tags a` (preface, человекочитаемый) — **НЕ совпадает** с (3)
  `dd.fandom a`, которого функция вообще не несёт;
- **НЕТ** `dd.words` (4) — статистика `dl.stats` в этой функции отсутствует
  вовсе (только текстовая заглушка `{word_count} words` внутри `<p>`, не
  отдельный узел);
- **НЕТ** `<div id="chapters">`/`.userstuff.module` (1)/(2) вовсе.

Без всех четырёх узлов:

1. **TC-256** (auto-READ при дочитывании сохраняет `downloadPath`/метаданные)
   физически невыполним — JS-слушатель выходит на `chaptersDiv`-guard, ни
   один `scroll`-листенер не регистрируется, `Android.onWorkFinished` не
   может быть вызван вовсе.

Единственный `test_cases` этого бага — `TC-256`; других кейсов, зависящих от
этого же набора узлов, на момент заведения не существует (проверено —
`grep -rl "onWorkFinished\|#chapters" test-cases/` до создания этого файла
даёт только упоминания-заметки в `TC-152.md` как ссылку на сиблинга, не
зависимость от фикстуры).

**Почему НЕ live-only (в отличие от того, как жил сам BUG-067 до фикса):**
синтетический `ao3_id 900000001` (и весь диапазон `works.py`, «намеренно из
безопасного диапазона») НЕ существует на реальном archiveofourown.org —
навигация туда на живом AO3 отдаёт 404/страницу ошибки, а не work-страницу с
`#chapters`. Класс «синтетические `ao3_id` фикстур на живом AO3 отдают 404,
эффект недостижим и негатив вакуумно-зелёный» уже кодифицирован калибровкой
Lead 2026-07-30 (`bugs/AT-BUG-029.md`) — оставлять `TC-256` live-only
означало бы либо держать её вечно `Blocked`, либо (хуже) прогонять против
РЕАЛЬНОГО стороннего произведения на archiveofourown.org, что не
согласовано ни с одним существующим приёмом фреймворка (все текущие
`@pytest.mark.live` тесты — `TC-007`/`TC-008` — не зависят от содержимого
DOM работы, только от факта, что панель `RatingMenu` рендерится независимо
от контента страницы; `TC-256` зависит от РЕАЛЬНОГО скрейпа DOM). Путь
replay-фикстуры — единственный практичный.

## Критерий готовности (Fixed)

`render_work_page_html` (или отдельная функция, если разработчик решит не
трогать общую — по образцу `render_work_metadata_page_html`, AT-BUG-061,
уже отдельной от `render_work_page_html` по той же причине несовместимых
узлов) несёт, в дополнение к существующему телу (не ломая порядок
`_download_list_html`/узлов AT-BUG-030 — тот же регресс-инвариант):

1. **`dd.fandom a`/`dd.words`** — реальная разметка `dl.work.meta.group`/
   `dl.stats`, ПО ОБРАЗЦУ уже существующей `render_work_metadata_page_html`
   (`recording_builder.py:754-770`): `<dl class="work meta group"><dt
   class="fandom tags">Fandom:</dt><dd class="fandom tags"><ul
   class="commas"><li><a class="tag" href="...">{fandom}</a></li></ul></dd>
   </dl>` и `<dl class="stats">...<dt class="words">Words:</dt><dd
   class="words">{word_count}</dd>...</dl>` — переиспользовать буквально тот
   же HTML-фрагмент, не изобретать заново.
2. **`<div id="chapters"><div class="userstuff module">...</div></div>`** —
   ОДНА глава (никакой ссылки `li a` с текстом «Next Chapter →» на странице
   — `isLastPage()` и так вернёт `true` тривиально, т.к. `pathname` не
   матчит `/chapters/`), содержимое достаточно короткое/расположенное так,
   чтобы `.userstuff.module` последнего блока помещался в вьюпорт ПОСЛЕ
   скролла документа до конца (`getBoundingClientRect().bottom <=
   innerHeight`) — то есть `#chapters` физически должен быть у КОНЦА
   документа, а суммарная высота документа НЕ должна намного превышать
   `innerHeight` (регрессия с узлом 3 `AT-BUG-030`/`render_reading_ux_filler_
   html`, который специально делает документ ВЫСОКИМ — тот узел и `#chapters`
   концептуально противоречат друг другу на одной странице; если оба нужны
   одному потребителю — разместить `#chapters` строго ПОСЛЕДНИМ узлом
   документа и подобрать геометрию так, чтобы скролл до самого низа страницы
   ГАРАНТИРОВАННО заводил низ `.userstuff.module` в вьюпорт — например
   `#chapters` без собственной большой высоты, сразу после фillera).
3. **Регрессия называет ВСЕХ потребителей `render_work_page_html`** (тот же
   список, что критерий готовности `AT-BUG-030`: `listing_basic.mitm`,
   `work_with_download.mitm`, `works_multi.mitm`, `listing_paginated.mitm`)
   — пересобрать все четыре, явно сверить TC-026/TC-032/TC-033 (уже
   существующий регресс-список AT-BUG-030) на отсутствие регрессии ПОСЛЕ
   добавления узлов этого бага.
4. **`TC-256` реализован и зелёный** (3 прогона подряд) на пересобранной
   `listing_basic.mitm` — сценарий: `open_work_page` → скролл документа до
   конца → `read_work_ratings_full()` подтверждает `rating=READ`,
   `downloadPath` неизменен, `comment`/`tags` неизменны, `title`/`fandom`/
   `wordCount` остаются ЛОКАЛЬНЫМИ (не заменены значениями фикстуры).
5. **Красная проба**: временный monkey-patch/удаление `#chapters` (или
   guard `if (existing?.rating != null)`, инвертированный для контроля) на
   живом прогоне `TC-256` реально меняет Then — доказательство, что
   негативный/позитивный Then содержателен, не тривиален из-за отсутствия
   узла.
6. `python -m pytest scripts/tests -q` без регресса.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-08-15T10:20:00Z — test-designer, заведение (правило 4 воркфлоу
test-designer).** Блокер обнаружен при проектировании `TC-256` — регресс-
замка `bugs/BUG-067.md` (эскалация координатора, разбор очереди, НЕ
needs-design §9 — `bugs/BUG-067.md` пришёл с `test_cases: []` после того,
как фикс `07805a9f` уже приехал в сборке 59be96c6, и правило D1 «Верифи-
цировать исправленный баг» на следующем проходе `/qa-loop` осталось бы без
предмета прогона). Дизайн кейса завершён и полон (`status: Review`) —
ограничена ТОЛЬКО автоматизация; сам кейс НЕ переведён в `Blocked` (тот же
паттерн, что `AT-BUG-029`/`AT-BUG-030`/`AT-BUG-067` — `schemas/
transitions.yaml`, test-case `initial: [Draft, Review]`; здесь нет спорного
ТРЕБОВАНИЯ, только инфраструктурный пробел).

Существовавшие покрывающие баги проверены ДО заведения (правило 4
воркфлоу): `AT-BUG-030` (тот же паттерн, другие узлы/другие кейсы, не
дубликат), `AT-BUG-061` (тот же паттерн, `dd.fandom`/`dd.words` УЖЕ решены
там для ДРУГОГО потребителя/URL-паттерна — образец переиспользования, не
готовая фикстура для ЭТОГО потребителя). Ни один существующий test_debt не
называет `#chapters`/`onWorkFinished`/`.userstuff.module` как предмет
критерия готовности (`grep -l "chapters\|onWorkFinished" bugs/AT-BUG-*.md`
до создания этого файла → 0 совпадений вне этого файла).

**Дефекты-собратья (D-0043):** не искал за пределами узкой поверхности
`render_work_page_html`/JS-слушателя `onScroll` — вне мандата этого
диспатча (регресс-замок одного конкретного бага, не полный аудит фикстур).

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов: `AT-BUG-030`
      (тот же паттерн «`render_work_page_html` не несёт нужную разметку»,
      другие узлы/кейсы — не дубликат), `AT-BUG-061` (тот же паттерн «нужны
      `dd.fandom`/`dd.words`», но для ДРУГОГО потребителя/URL — образец, не
      дубликат)
- [x] Суть долга ясна и воспроизводима по коду (`ao3_bridge.js:1164-1197`,
      `recording_builder.py:591-636`/`754-770`)
- [x] Severity: minor — блокирует автоматизацию ОДНОГО P1-кейса (`TC-256`),
      дизайн кейса полон, продуктовый баг (`BUG-067`) уже `Fixed` независимо
      от этого долга
- [x] Ни одно изменение не внесено в `app-under-test/`
- [x] `test_cases: ["TC-256"]` — единственный кейс, заблокированный этим
      фикстурным пробелом на момент заведения
