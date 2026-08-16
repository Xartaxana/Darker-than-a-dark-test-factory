---
key: "BUG-071"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p2"
summary: "Copy URL button разыменовывает navigator.clipboard БЕЗ guard'а при отсутствии API, выбрасывает синхронный TypeError"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-16T20:42:00Z"
updated: "2026-08-16T20:42:00Z"
archived: false
resolution: null
---

# Copy URL button разыменовывает navigator.clipboard БЕЗ guard'а при отсутствии API, выбрасывает синхронный TypeError

_Спроецировано из `bugs/BUG-071.md` (источник правды).
Статус в нашей машине: **Fixed**._

# BUG-071 — navigator.clipboard БЕЗ guard'а в Copy URL button вызывает синхронный TypeError

## Окружение

- Версия приложения: 1.10+ (debug button exposed in Settings > Debug > Show copy-URL button)
- Платформа: Android (embedded WebView)
- Режим: любой (дефект в JS коде, не специфичен к replay/live)

## Суть дефекта

Сиблинг-класс BUG-069 (того же Copy URL button). Коммит фикса BUG-069 (`85fbed4`) добавил обработку ошибок реджекта Promise через второй аргумент `.then()` и fallback на `document.execCommand()`, но **НЕ добавил guard против синхронного `TypeError` при разыменовании самого `navigator.clipboard.writeText`**.

На WebView-имплементациях, где `navigator.clipboard` undefined или `navigator.clipboard.writeText` недоступна, вызов:

```javascript
navigator.clipboard.writeText(location.href).then(...)
```

выбросит синхронный `TypeError: Cannot read property 'writeText' of undefined` **ДО** создания Promise, **ДО** входа в reject-handler во втором аргументе `.then()`. Это ДО TRY-CATCH промиса, что привело бы к молчаливой ошибке в консоли и молчанию кнопки — аналогично исходной проблеме BUG-069.

## Шаги воспроизведения (Given-When-Then)

**Given**
- Приложение открыто, Settings > Debug > Show copy-URL button включен
- WebView на устройстве/эмуляторе НЕ поддерживает Clipboard API в embedded контексте (например, некоторые реальные устройства или специальные конфигурации)

**When**
- Пользователь тапит кнопку "Copy URL"

**Then (ожидалось)**
- Кнопка меняет текст на "Copied!" или "Copy failed" в зависимости от успеха fallback
- Кнопка возвращается к "Copy URL" через ~1.5 сек

**Actual (на системах БЕЗ guard'а)**
- JavaScript console ошибка: `TypeError: Cannot read property 'writeText' of undefined`
- Вторая функция `.then(...)` (reject-handler с fallback) никогда не выполняется
- Кнопка остаётся молча с текстом "Copy URL" — неясно, скопировалось или нет

## Частота

Детерминированна на всех устройствах/конфигурациях, где `navigator.clipboard` отсутствует или не имеет метода `writeText` (100% при наличии такой конфигурации; на эмуляторе ao3_test_api34 с защитой Clipboard API — всегда при каждом тапе).

## Анализ

**Почему это баг приложения, а не тестовой системы:**

1. **Воспроизводимо по коду:** Отсутствие guard `if (navigator.clipboard && navigator.clipboard.writeText)` перед вызовом — это ФАКТ кода (`app-under-test/app/src/main/assets/ao3_bridge.js:1102`).

2. **Контрастный класс с BUG-069:** BUG-069 чинил ошибку **ПОСЛЕ** создания Promise (rejectHandler); BUG-071 — ошибка **ДО** создания Promise (синхронный TypeError на разыменование). Обработка реджекта-ветки не защищает от синхронной ошибки.

3. **Рекомендация была озвучена:** В разделе "Рекомендация фикса" самого BUG-069.md предлагался именно такой guard (`if (navigator.clipboard && navigator.clipboard.writeText) { ... } else { ... }`), но он не был включен в финальный фикс `85fbed4`.

4. **Реальная проблема на системах:** На любых WebView-имплементациях или конфигурациях, где Clipboard API недоступна (реальные пользовательские устройства, браузеры/WebView-версии), пользователи получат ту же молчаливую ошибку, что и в исходной BUG-069, только на этот раз — до попытки fallback'а.

## Рекомендация фикса

Добавить guard перед вызовом `navigator.clipboard.writeText`:

```javascript
function copyUrl() {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(location.href);
    } else if (document.execCommand) {
        // Fallback на execCommand для браузеров/систем без Clipboard API
        var textarea = document.createElement('textarea');
        textarea.value = location.href;
        document.body.appendChild(textarea);
        textarea.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) {}
        document.body.removeChild(textarea);
        return ok ? Promise.resolve() : Promise.reject(new Error('execCommand failed'));
    } else {
        return Promise.reject(new Error('Copy not supported'));
    }
}

btn.addEventListener('click', function () {
    copyUrl()
        .then(function () { flash('Copied!'); })
        .catch(function (err) { flash('Copy failed'); });
});
```

Или более компактный вариант — оберните содержимое try-catch'ем:

```javascript
btn.addEventListener('click', function () {
    try {
        var promise = (navigator.clipboard && navigator.clipboard.writeText) 
            ? navigator.clipboard.writeText(location.href)
            : /* fallback via execCommand */;
        promise
            .then(function () { flash('Copied!'); })
            .catch(function () { flash('Copy failed'); });
    } catch (e) {
        flash('Copy failed');
    }
});
```

## Связанные находки

- **BUG-069** — исходная находка про обработку ошибок `writeText`; этот баг — сиблинг того же класса дефектов (неполная обработка Promise)
- **AT-BUG-068** — долг тестовой системы (Clipboard API ограничение на WebView); BUG-069 и BUG-071 — триаж этой находки на app_bug
- **D-0043 (CLAUDE.md)** — "Чини класс, а не экземпляр"; этот баг и BUG-069 относятся к классу дефектов "неполная обработка Promise" в контексте Clipboard API

## Верификация (заполняет fix-verifier)

| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**[qa @ 2026-08-16T00:28:00Z]**

Триаж критик-входа D1 BUG-069. При анализе фикса `85fbed4` и проверке всех вхождений `navigator.clipboard` в assets-файлах найден сиблинг-класс: синхронный TypeError на разыменование `navigator.clipboard.writeText` БЕЗ guard'а. Reject-handler в `.then()` не защитит от синхронной ошибки разыменования.

Severity: **minor** — DEBUG-функция, но всё же видима пользователю и влияет на UX при отсутствии Clipboard API (реальные устройства/конфигурации).

Awaiting: none

**[gitlab:dyakagreen @ 2026-08-16T10:44:36.787Z]** > **Исправлено в `aa377e0` (main).** Реализован рекомендованный guard:
> 
> - fallback на `document.execCommand('copy')` вынесен в именованную функцию `execCommandFallback()`;
> - вызов `navigator.clipboard.writeText` обёрнут в `if (navigator.clipboard && navigator.clipboard.writeText)`, ветка else идёт сразу в fallback — синхронный TypeError на разыменовании исключён;
> - reject-ветка промиса по-прежнему падает в тот же fallback, кнопка всегда даёт видимый отклик (Copied! / Copy failed).
> 
> Замечу: конфигурация «navigator.clipboard undefined» в этом приложении не экзотика — Clipboard API отсутствует на небезопасных origin, т.е. на КАЖДОЙ file://-вкладке со скачанной работой, так что guard закрывает вполне реальный путь. Верификация — за QA.

**[gitlab:dyakagreen @ 2026-08-16T10:56:14.620Z]** Метла `qa-status::QAready` выставлена на GitLab issue — переход Open→Fixed зафиксирован автоматически (второй канал, docs/06 §3а, gitlab-label).

**[qa @ 2026-08-16T20:42:00Z]**

Принято: фикс коммита `aa377e0` (main) соответствует точно рекомендации из раздела "Рекомендация фикса" (п. 83-126): добавлен guard `if (navigator.clipboard && navigator.clipboard.writeText)` перед вызовом, ветка else направлена в fallback на `document.execCommand('copy')` через функцию `execCommandFallback()`. Синхронный TypeError на разыменование исключён.

**Анализ по артефактам:**
- Разработчик подтвердил: fallback вынесен в именованную функцию (улучшение читаемости)
- Guard покрывает оба условия: наличие объекта И метода (полная защита)
- Reject-ветка по-прежнему падает в fallback — кнопка ВСЕГДА даёт видимый отклик (Copied! / Copy failed)

**Примечание:** Конфигурация `navigator.clipboard undefined` — не экзотика; на file:// origin (скачанные работы из AO3) Clipboard API отсутствует по спецификации браузера. Guard закрывает действительно распространённый путь, не теоретический.

Статус: Fixed → ожидание fix-verifier для проверки TC и device-witness'а на новой сборке (docs/06 D1).

Awaiting: none

## Чек-лист качества

- [x] Проверены дубликаты среди открытых багов (`bugs/BUG-*.md`, status != Verified/Rejected)
- [x] Точная позиция в коде: `app-under-test/app/src/main/assets/ao3_bridge.js:1102`
- [x] Severity обоснована — DEBUG-функция, но видима пользователю, плохая UX при ошибке
- [x] Сиблинг BUG-069 задокументирован; отличие от BUG-069 чётко (синхронная vs асинхронная ошибка)
- [x] Рекомендация фикса приложена
- [x] Ни одного изменения в коде приложения не внесено; только чтение
- [x] Класс дефекта идентифицирован (неполная обработка Promise, отсутствие guard на разыменование)
