---
key: "TC-259"
project: "AO3"
issueType: "test-case"
status: "tc-review"
priority: "p1"
summary: "Ссылка «Next» под infinite scroll всегда ведёт на ещё НЕ показанную страницу и скрывается, когда страниц больше нет"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:browser", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-19T13:26:00Z"
updated: "2026-08-19T13:26:00Z"
archived: false
resolution: null
---

# Ссылка «Next» под infinite scroll всегда ведёт на ещё НЕ показанную страницу и скрывается, когда страниц больше нет

_Спроецировано из `test-cases/browser/TC-259.md` (источник правды).
Статус в нашей машине: **Review**._

# TC-259 — syncNextLinks: Next всегда указывает вперёд на непоказанное, li.previous нетронута, Next скрыт на последней странице

## Предусловия
- L2 bridge-harness (`framework/tests/bridge/`, `bridge_call` фикстура,
  device-free jsdom против `ao3_bridge.js`), маркер `@pytest.mark.bridge`.
- Фикстуры листинга — `recording_builder.render_listing_html(...,
  pagination_html=recording_builder.render_pagination_html(prev_url,
  current_page, next_url))`, три "страницы" листинга (стр.1→2, 2→3, 3→нет
  следующей), собранные литералами внутри теста (не требуют записанного
  `.mitm`).
- `window.__ao3InfiniteScroll` не задан (дефолт `!== false` → ON).

## Сценарий (Given-When-Then)

**Given** загружена страница 1 листинга с рендеренным `li.next a`, ведущим на
страницу 2 (server-rendered href, `render_pagination_html`)

**Then** сразу после инъекции бриджа `li.next a.href` совпадает с исходным
`_effectiveNextUrl` страницы 1 (страница 2) — ничего не переписано раньше
времени

**When** харнесс доводит до состояния "страница 2 подгружена" (fetch-стаб
`fetchResponses` отдаёт HTML страницы 2 с СОБСТВЕННОЙ пагинацией →
страница 3; вызов `fetchAndAppend()` достигается через существующий
fail-open путь `window.dispatchEvent(new Event('scroll'))` — см. заметки:
это НЕ проверка «скролл вызвал подгрузку», а способ довести харнесс до
пост-append состояния, которое и есть предмет Then)

**Then** `li.next a.href` ПЕРЕПИСАН на URL страницы 3 (не остался на странице
2 — тап по Next теперь ведёт на ЕЩЁ НЕ показанный контент, класс BUG-018
закрыт) **and** номерные ссылки (`li` без классов `next`/`previous`)
по-прежнему скрыты (`display:none`) **and** `li.previous` НЕ изменена ботом
(её `a.href`/текст остаются ровно теми, что отрисовал сервер для страницы 1
— бридж пишет только в `li.next`)

**When** харнесс доводит до состояния "страница 3 подгружена, и её
пагинация не несёт `next` (последняя страница)"

**Then** `li.next` полностью скрыт (`style.display==='none'`), а не просто
с пустым `href` — тап по невидимому элементу невозможен физически, не
только визуально

**Инвариант:** `_effectiveNextUrl`/`syncNextLinks` поддерживают свойство «Next
всегда указывает на первую ЕЩЁ НЕ подгруженную страницу или отсутствует,
если такой нет» независимо от того, сколько подгрузок уже произошло —
свойство проверено на ДВУХ последовательных переходах (2→3, 3→конец), не
на одном примере.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| li.next href после инициализации (стр.1) | абсолютный/host-relative URL стр.2 |
| li.next href после подгрузки стр.2 | URL стр.3 (не стр.2) |
| li.previous | не изменена бриджем на всём протяжении |
| Номерные ссылки | `display:none` на всех трёх состояниях |
| li.next на последней странице | `display:none` |

## Заметки для автоматизации
- Инфраструктура уже принята и зелёная (N5/N6 `docs/tasks/p2-pyramid-
  bridge.md`, 122 bridge-теста): `framework/tests/bridge/conftest.py`
  (`bridge_call`), `framework/bridge_harness/run_bridge.js` (`fetch`-стаб
  через `installFetchStub`, карта `url -> {status, body}`), не требует
  устройства/эмулятора. Блокера нет.
- **Пограничное решение (для F1/B10-гейта test-reviewer, ПРОЧИТАТЬ перед
  ревью).** `fetchAndAppend()` вызывается ТОЛЬКО из scroll-listener'а
  (`ao3_bridge.js:602-609`), который в jsdom fail-open (rect всегда 0 —
  `test_layout_fail_open_canary.py`, B4): ЛЮБОЙ синтетический `scroll`
  безусловно достигает `fetchAndAppend()`. Этот кейс НЕ ассертит «scroll
  вызвал подгрузку» (запрещённая по Р3 геометрическая ветка) — синтетический
  `scroll` здесь ЧИСТО техническое средство довести харнесс до состояния
  «страница N подгружена», а предметом Then является downstream-контракт
  `syncNextLinks` (строковое сравнение `href`, видимость `li.next`/номерных
  ссылок) — свойство, не зависящее от геометрии/скролл-позиции вовсе.
  Формулировка Then/действий должна явно называть это разграничение (как
  в теле кейса выше), чтобы B10-гейт не спутал этот тест с запрещённым
  классом.
- Действия харнесса — `actions: [{id:'nextHref', type:'eval', code:
  "document.querySelector('.pagination li.next a').href"}]` и т.п.,
  `{id:'nextDisplay', ..., code: "document.querySelector('.pagination
  li.next').style.display"}`, по образцу `test_badges.py`.
- Триггер подгрузки — `{"id":"scroll","type":"eval","code":
  "window.dispatchEvent(new Event('scroll')); 'dispatched'"}`, затем
  повторный `bridge_call` НЕ нужен — харнесс уже флашит микрозадачи/таймеры
  после каждого action (`flushMicrotasksAndTimers`, `run_bridge.js:216`),
  а `fetch`-промис резолвится синхронно через стаб.
- Три последовательных состояния (init → после стр.2 → после стр.3) —
  ОДИН `bridge_call` с несколькими actions подряд (харнесс держит один
  jsdom-документ на весь запрос), не три отдельных вызова — дешевле и
  соответствует «один сценарий — один кейс».
- `render_pagination_html(prev_url, current_page, next_url=None)` —
  готовый примитив для «последней страницы без Next»
  (`recording_builder.py:469-499`), не нужно городить HTML руками.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами (HTML
      литералами через `render_listing_html`/`render_pagination_html`)
- [x] Then проверяет наблюдаемое поведение (href/видимость DOM-узлов), а не
      реализацию
- [x] Заголовок сформулирован от ожидаемого поведения
- [x] Указаны приоритет (P1), область (browser) и источник требования (R-02)
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Блокер автоматизации отсутствует (harness/фикстуры уже приняты N5/N6)
- [x] Строка `Инвариант:` добавлена (свойство на ДВУХ переходах, не на одном)
- [x] Слой L2 обоснован явно (device-free, живой AO3 не нужен) и не
      конфликтует с B4/B10 fail-open запретом — граница объяснена в
      заметках для ревьюера
