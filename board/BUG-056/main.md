---
key: "BUG-056"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p1"
summary: "Bridge-скрипт падает на document.head.appendChild — Rate-кнопки не инжектируются"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-090", "run:RUN-20260804-1624", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-04T22:29:15Z"
updated: "2026-08-04T22:29:15Z"
archived: false
resolution: null
---

# Bridge-скрипт падает на document.head.appendChild — Rate-кнопки не инжектируются

_Спроецировано из `bugs/BUG-056.md` (источник правды).
Статус в нашей машине: **Open**._

# BUG-056 — Bridge-скрипт падает при инъекции Rate-кнопок (document.head === null)

## Окружение
- Версия: 1.10 (versionCode 11), build 6455af0c, source_commit 63f6aac3
- Эмулятор: `ao3_test_api34` (emulator-5554), API 34, GPU swiftshader_indirect
- Режим: replay (listing_basic.mitm фикстура)
- Тема: не указана (системная)

## Шаги воспроизведения (Given-When-Then)

**Given**
1. Приложение запущено и готово отображать листинг работ
2. Листинг загружается с записанной страницы AO3 (replay-фикстура `listing_basic.mitm`)
3. Страница полностью отрисована с 4 блёрбами работ (видна разметка каждой карточки)

**When**
1. WebView завершает загрузку страницы
2. Инъектируется скрипт `ao3_bridge.js` через `onPageFinished` (BrowserScreen.kt:613)
3. Скрипт начинает инициализацию: устанавливает guard `window.__ao3Bridge = true` (строки 5-6)
4. Скрипт выполняет строку 20: `document.head.appendChild(noticeStyle)`

**Then (ожидалось)**
- Bridge завершает инжекцию без ошибок
- На каждом блёрбе (li[id^="work_"].work.blurb) появляется Rate-кнопка (data-ao3-rate-btn)
- Иконки рейтинга (Save/Like/Read/Dislike) отображаются рядом с работами

**Actual (фактически)**
- На строке 20 скрипт падает с ошибкой: `Uncaught TypeError: Cannot read properties of null (reading 'appendChild')`
- Guard `window.__ao3Bridge = true` уже установлен (строки 5-6 выполнены до ошибки)
- Повторная инъекция блокирована guard'ом (блокирующий `if (window.__ao3Bridge) return;` в начале скрипта)
- Страница остаётся БЕЗ Rate-кнопок и бейджей ядровой функции рейтинга на весь сеанс (до перезагрузки)

## Частота
100% на кейсе TC-090 (test_add_freeform_tag_persists), ожидалось регрессионное воспроизведение после падения (одна попытка в прогоне, сиблинг AT-BUG-047 дал переменную воспроизводимость — требуется перепрогон для уточнения частоты и стабильности).

## Артефакты
- **Скриншот листинга без Rate-кнопок**: `runs/RUN-20260804-1624/allure/04b14b07-8999-47bf-9489-606e1e3f5c56-attachment.png` — страница отрисована полностью, все 4 блёрба на месте, ни одна Rate-кнопка не видна ни у одного блёрба.
- **Logcat с дословной ошибкой**: `runs/RUN-20260804-1624/allure/d17b00ba-a449-4d1f-b61b-1def0545d157-attachment.txt`, строка 284:
  ```
  08-04 13:48:48.661 13534 13534 I chromium: [INFO:CONSOLE(20)] "Uncaught TypeError: Cannot read properties of null (reading 'appendChild')", source:  (20)
  ```
- **Page source (нативное дерево)**: `runs/RUN-20260804-1624/allure/f725140a-8700-4a35-8081-1dc0fbf91867-attachment.txt` (контекст=NATIVE_APP в момент запроса).
- **Replay-фикстура**: `framework/fixtures/ao3/listing_basic.mitm` (не повреждена, содержит корректную разметку с 10 вхождениями `class="work blurb"`).

## Анализ (баг приложения)

### Корневая причина

Скрипт `app-under-test/app/src/main/assets/ao3_bridge.js:20` безусловно обращается к `document.head`:

```javascript
var noticeStyle = document.createElement('style');
noticeStyle.textContent = 'p.muted.notice { display: none !important; }';
document.head.appendChild(noticeStyle);  // <-- строка 20, document.head === null
```

В момент инъекции скрипта (onPageFinished) `document.head` оказывается `null`, что указывает на конфликт со сроком жизни DOM-дерева: либо WebView выполняет скрипт до полного разбора заголовка страницы (race condition), либо документ загружается в состоянии, когда head не инициализирован.

### Класс дефекта: необёрнутые обращения к DOM

Скрипт содержит **6 необёрнутых обращений** к `document.head`/`document.body`:
- Строка 20: `document.head.appendChild(noticeStyle)` — падает на этой
- Строка 199: `document.head.appendChild(...)`
- Строка 1024: `document.body.appendChild(...)`
- Строка 1040: `document.body.appendChild(...)`
- Строка 1069: `document.body.appendChild(...)`
- Строка 900: чтение `document.body.scrollHeight`

Любое из этих обращений может поймать `null` при недостаточно разобранном документе, блокируя весь механизм инжекции Rate-кнопок.

### Техническое наблюдение: дегустация ресурсов перед ошибкой

Перед ошибкой в логкате видны фреймы с пропусками рендеринга:
```
08-04 13:48:47.610 13534 13534 I Choreographer: Skipped 61 frames!
08-04 13:48:47.623 13534 13549 I OpenGLRenderer: Davey! duration=1053ms
```

Нагрузка на устройство была высокой (~60% используемого времени), что может сдвинуть timing инъекции, но это триггер окна гонки, а не причина падения кода.

### Почему это баг приложения

1. **Скрипт выполняется нормативно** — инджектируется через `onPageFinished` (BrowserScreen.kt:613), метод стандартный.
2. **Replay-фикстура валидна** — `listing_basic.mitm` содержит корректный HTML с `<head>` и полной разметкой `<li class="work blurb">` элементов.
3. **Guard блокирует повторную инъекцию** — `window.__ao3Bridge` установлен ДО work-with-DOM, поэтому при повторной загрузке одного документа инъекция пропускается, и страница остаётся без Rate-кнопок.
4. **Дефект в защите кода** — ожидается, что `document.head` и `document.body` существуют при выполнении скрипта в onPageFinished; реальность может быть иной в углах нагрузки, и скрипт должен иметь защиту (проверку null или try-catch).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-04T22:29:15Z | 1.10 (versionCode 11), build 6455af0c (та же, что found_in) | TC-090 (test_add_freeform_tag_persists) — witness из прогона RUN-20260804-1624.md (regression replay), запущен 2026-08-04T15:09:40–16:09:19, archival результатов в runs/RUN-20260804-1624/allure/ | TC-090: `failed` (broken по Allure; Allure-статус в таблице «Падения» прогона: "broken"); дословное сообщение: `TimeoutException: не найден DOM-элемент: li#work_900000002.work.blurb [data-ao3-rate-btn]`. Логкат фиксирует причину падения: `[INFO:CONSOLE(20)] "Uncaught TypeError: Cannot read properties of null (reading 'appendChild')"` (строка 284 logcat-артефакта). Скриншот отрисовки листинга (04b14b07…png) показывает 4 полные карточки работ, ни одна Rate-кнопка не видна ни у одного блёрба — дефект подтверждён поведением (Rate-кнопка не инжектирована). Triaged by failure-analyst как APP_BUG, вердикт обоснован: баг лежит в коде app-under-test, инъекция повреждена падением скрипта, страница невосстановима без перезагрузки | APP_BUG подтверждён |

## Обсуждение

## Чек-лист качества
- [x] Проверены дубликаты среди открытых багов (bugs/BUG-001..055, AT-BUG-002..055) — нет совпадений; класс bridge/null-обращений не совпадает с BUG-014 (авто-скачивание) или BUG-015 (авто-клик kudos)
- [x] Репро-шаги воспроизводят проблему: Given (листинг отрисован), When (инджекция bridge), Then (Rate-кнопки есть) vs Actual (нет кнопок из-за TypeError)
- [x] Severity: major — потеря ядровой функции (Rate-кнопки) на затронутой странице; функциональность доступна только после перезагрузки
- [x] Приложены логкат (дословная цитата TypeError в строке 284), скриншот листинга без Rate-кнопок, logcat в полном виде
- [x] Точная версия указана (1.10 versionCode 11, build 6455af0c, commit 63f6aac3) из state/app-under-test.yaml на момент RUN-20260804-1624
- [x] Ни одно изменение не внесено в app-under-test/ (read-only источник анализа)
- [x] Класс дефекта явно назван: необёрнутые обращения к DOM (6 мест в ao3_bridge.js: :20, :199, :1024, :1040, :1069, :900)
- [x] Источник находки: TC-090 на регрессионном прогоне RUN-20260804-1624 (вердикт failure-analyst: APP_BUG); прилинкована тест-кейс и прогон в frontmatter
