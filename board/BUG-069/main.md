---
key: "BUG-069"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "Copy URL button в DEBUG-разделе молчит при ошибке writeText, нет обратной связи пользователю"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-188", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-15T23:12:46Z"
updated: "2026-08-15T23:12:46Z"
archived: false
resolution: "done"
---

# Copy URL button в DEBUG-разделе молчит при ошибке writeText, нет обратной связи пользователю

_Спроецировано из `bugs/BUG-069.md` (источник правды).
Статус в нашей машине: **Verified**._

# BUG-069 — Copy URL кнопка (DEBUG) молчит при ошибке writeText без обратной связи

## Окружение

- Версия: 1.10+ (debug button exposed in Settings > Debug > Show copy-URL button)
- Платформа: Android (embedded WebView)
- Сценарий: Клик по кнопке "Copy URL" в DEBUG-секции нижнего левого угла при включенном режиме

## Суть дефекта

Кнопка "Copy URL" в DEBUG-разделе использует `navigator.clipboard.writeText()` БЕЗ обработки ошибок (`.catch()`). Если вызов реджектится (например, `DOMException: Write permission denied` на некоторых WebView-имплементациях), промис отклоняется молча, `.then()` никогда не вызывается, и пользователь не получает никакой обратной связи — кнопка остаётся с текстом "Copy URL", хотя копирование не удалось. Это вводит пользователя в заблуждение: неясно, скопировалось ли содержимое или нет.

## Шаги воспроизведения (Given-When-Then)

**Given**
- Приложение открыто, Settings > Debug > Show copy-URL button включен (тумблер ON)
- Пользователь на любой рабочей странице AO3 (например, любая открытая работа)
- Устройство имеет WebView с ограничением на доступ к Clipboard API в embedded контексте
  (подтверждено на эмуляторе ao3_test_api34, Chromium 113.0.5672.136; может быть на некоторых реальных устройствах)

**When**
- Пользователь тапит кнопку "Copy URL" в нижнем левом углу страницы

**Then (ожидалось)**
- URL страницы копируется в буфер обмена
- Кнопка меняет текст на "Copied!" на ~1.5 сек
- Кнопка возвращается к "Copy URL"

**Actually (фактически на затронутых устройствах)**
- Browser console содержит: `Uncaught DOMException: Write permission denied`
- Промис реджектится, но `.catch()` отсутствует
- Пользователь видит, что кнопка остаётся с текстом "Copy URL"
- Неясно, успешно ли скопировалось или нет

## Механизм (по коду)

`app-under-test/app/src/main/assets/ao3_bridge.js:1067-1087`:

```javascript
(function () {
    var btn = document.createElement('button');
    btn.textContent = 'Copy URL';
    btn.style.cssText = '...';
    btn.style.display = window.__ao3DebugCopyUrl ? '' : 'none';
    btn.addEventListener('click', function () {
        navigator.clipboard.writeText(location.href).then(function () {
            btn.textContent = 'Copied!';
            setTimeout(function () { btn.textContent = 'Copy URL'; }, 1500);
        });
        // ↑ НЕЛЬ .catch() — реджект идёт необработанным
    });
    document.body.appendChild(btn);

    window.setDebugCopyUrl = function (enabled) {
        btn.style.display = enabled ? '' : 'none';
    };
})();
```

**Класс дефекта:**
- Неполная обработка Promise: `.then()` задан, `.catch()` отсутствует
- На системах с ограничением на Clipboard API вызов реджектится молча
- Пользователь остаётся без обратной связи о причине отказа

## Частота и достижимость

**На эмуляторе ao3_test_api34 (API 34, Chromium 113):** 100% — детерминированный отказ при каждом тапе (документировано в AT-BUG-068 двумя независимыми способами — Selenium `.click()` и настоящий Android POINTER_TOUCH).

**На реальных устройствах:** Возможно на subset устройств/WebView-версий с аналогичным ограничением (не факт, что массово, но затронутые пользователи видят тот же молчаливый отказ).

## Артефакты и связанные находки

- **Код якоря:** `app-under-test/app/src/main/assets/ao3_bridge.js:1067-1087` (DEBUG Copy URL button)
- **Диагностика и подробный анализ:** `bugs/AT-BUG-068.md` (test_debt; ограничение WebView-среды)
- **Связанный TC:** `TC-188` (settings-debug-copy-url-toggle, `@pytest.mark.skip` на грани "Copied!"; заблокирован AT-BUG-068)

## Рекомендация фикса

**Минимум:** Добавить `.catch()` с UI-фидбеком:

```javascript
navigator.clipboard.writeText(location.href)
    .then(function () {
        btn.textContent = 'Copied!';
        setTimeout(function () { btn.textContent = 'Copy URL'; }, 1500);
    })
    .catch(function (err) {
        btn.textContent = 'Copy failed';
        setTimeout(function () { btn.textContent = 'Copy URL'; }, 1500);
        console.warn('Copy URL failed:', err.message);
    });
```

**Альтернатива:** Fallback на `document.execCommand('copy')` для браузеров/систем, где Clipboard API недоступна:

```javascript
function copyUrl() {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(location.href);
    } else if (document.execCommand) {
        // Fallback для старых браузеров
        var textarea = document.createElement('textarea');
        textarea.value = location.href;
        document.body.appendChild(textarea);
        textarea.select();
        var success = document.execCommand('copy');
        document.body.removeChild(textarea);
        return success ? Promise.resolve() : Promise.reject(new Error('execCommand failed'));
    } else {
        return Promise.reject(new Error('Copy not supported'));
    }
}

btn.addEventListener('click', function () {
    copyUrl()
        .then(function () {
            btn.textContent = 'Copied!';
            setTimeout(function () { btn.textContent = 'Copy URL'; }, 1500);
        })
        .catch(function (err) {
            btn.textContent = 'Copy failed';
            setTimeout(function () { btn.textContent = 'Copy URL'; }, 1500);
            console.warn('Copy URL failed:', err.message);
        });
});
```

## Анализ

### Почему это баг приложения, а не тестовой системы

1. **Воспроизводимо по коду:** Отсутствие `.catch()` — это ФАКТ кода, не проблема окружения. Даже на системах без ограничения, хорошая практика требует обработки потенциальных ошибок Promise.

2. **Контрольная точка:** AT-BUG-068 — это долг тестовой системы (broken_environment), но триаж выявил отдельный класс: приложение не готово к отказу. На реальных пользовательских устройствах с аналогичным ограничением они получат тот же молчаливый отказ БЕЗ видимой обратной связи.

3. **DEBUG vs UX:** DEBUG-функция, но видима конечному пользователю (через Settings > Debug > Show copy-URL button). Даже DEBUG-код должен давать обратную связь при сбое, иначе пользователь остаётся в неведении.

4. **Фикс независим от тестовой среды:** Добавление `.catch()` и/или fallback полезно на ЛЮБОЙ системе, не только на затронутой тестовым эмулятором.

### Отличие от AT-BUG-068

- **AT-BUG-068** (test_debt): Тестовое окружение (этот конкретный WebView/AVD) не поддерживает Clipboard API в embedded контексте — дело тестовой системы
- **BUG-069** (app_bug): Приложение не обрабатывает потенциальный отказ Clipboard API и оставляет пользователя без обратной связи — дело приложения

## Верификация (заполняет fix-verifier)

| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-15 (23:12:46Z) | source_commit `59be96c6398786d33c878dbce33cb1ecde269374` (built_at 2026-08-14T23:14:07Z, versionName `dev-local`, versionCode `12`, output-metadata.json); фикс-коммит `85fbed4` подтверждён предком (`git merge-base --is-ancestor 85fbed4 59be96c6...` → EXIT=0), файл на source_commit содержит фикс (`git show 59be96c6...:app/src/main/assets/ao3_bridge.js` — fallback-блок присутствует) | TC-188: недоступен для прогона (automated_by пуст, `@pytest.mark.skip` — флак ~20% в существующем assert через `driver.get_log('browser')`, см. AT-BUG-068 «Критерий готовности» пункт 3, откат coordinator 2026-08-16). Замена: код-факт-проверка (`git show 85fbed4` — .catch()-эквивалент, execCommand-fallback добавлен) + device-witness ЖИВЫМ прогоном временного теста `framework/tests/test_bug069_verify_tmp.py` (написан этим ходом, удалён после прогона). **Критик-вход (2026-08-15/16, независимый прогон):** цепочка коммит→сборка→устройство замкнута до конца (`adb pull` установленного `base.apk`, md5 байт-в-байт совпал со сборочным APK; `assets/ao3_bridge.js` внутри — md5 идентичен, устройство гоняло именно фиксированный код). Витнесс воркера (только чтение `b.textContent` → `['Copied!']`) структурно НЕ различал новую reject-ветку от предсуществовавшей fulfilled-ветки (обе флешат тот же текст) — критик поставил различающий изолирующий прогон (временный `test_critic_bug069_probe_tmp.py`, инструментированы `navigator.clipboard.writeText`/`document.execCommand` ДО тапа, удалён после, `git status --porcelain -- framework/tests/` пуст) | PASSED, `PYTEST_EXIT=0` (`Invoke-Pytest tests/test_bug069_verify_tmp.py -v`, 57.07s). Дословный `allure-results/017c498b-9f45-487f-9ab1-8e358780666a-attachment.txt`: `['Copied!']`. **Критик-измерение** (`scratchpad/critic-bug069/probe.txt`, `1 passed in 71.66s`, `PYTEST_EXIT=0`): `POST_TAP_POLL_0: {"exec": ["copy -> true"], "label": "Copied!", "wt": ["REJECTED:NotAllowedError:Write permission denied."]}` — `writeText` реджектится (тот же отказ, что в AT-BUG-068), reject-ветка реально исполнилась, `execCommand('copy') -> true`, подпись сменилась и вернулась по таймеру | **Verified**. Дефект устранён — подтверждено ИЗМЕРЕНИЕМ (не только сравнением подписи): при реджекте `writeText` исполняется именно новая fallback-ветка (`execCommand`), кнопка даёт «Copied!»/«Copy failed» вместо молчания. Критик-вердикт: ДОРАБОТАТЬ на слое отчёта воркера (agent_output-блок невалиден, исходная запись содержала недоказанное утверждение) — статус Verified НЕ откатывать, вывод корректен. |

## Обсуждение

**[qa @ 2026-08-14T02:15:00Z]**

Триаж находки из AT-BUG-068. AT-BUG-068 классифицирован как `test_debt` (broken_environment: Clipboard API на тестовом WebView отвергает writeText), но раздел "Non-goal" указывает на отдельный продуктовый триаж: молчаливый отказ БЕЗ обработки ошибок в коде приложения затронет и реальных пользователей на устройствах с аналогичным ограничением.

Решение: Отдельный APP_BUG на отсутствие `.catch()` и обратной связи пользователю.

Severity: **minor** — DEBUG-функция (не часть основного потока), но всё же видима пользователю и влияет на UX даже при редких ошибках.

Awaiting: none

**[gitlab:dyakagreen @ 2026-08-14T20:16:18.829Z]** Метка `qa-status::QAready` выставлена на GitLab issue — переход Open→Fixed зафиксирован автоматически (второй канал, docs/06 §3а, gitlab-label).

**[fix-verifier @ 2026-08-15T23:12:46Z]** Fixed → Verified.

Фикс-коммит `85fbed4` (`git merge-base --is-ancestor 85fbed4 59be96c6...` → EXIT=0, предок текущей сборки; `git show 59be96c6...:app/src/main/assets/ao3_bridge.js` — фактическое содержимое собранного дерева несёт фикс) добавляет обработчик реджекта `writeText` (второй аргумент `.then()`, эквивалент `.catch()`): при реджекте — fallback на `document.execCommand('copy')` через скрытую `<textarea>`, и в ЛЮБОМ случае (успех/неуспех fallback) кнопка получает `flash('Copied!' | 'Copy failed')` — молчания больше нет ни при каком исходе.

TC-188 недоступен для прогона (`automated_by` пуст, `@pytest.mark.skip` — флак ~20% через `driver.get_log('browser')`, откат coordinator 2026-08-16, см. AT-BUG-068 п.3 «Критерий готовности»). Замена — временный device-witness тест (`framework/tests/test_bug069_verify_tmp.py`, написан и удалён этим ходом, не примешан к сьюту), переиспользующий существующие степы `browser_steps.assert_copy_url_button_visible`/`tap_copy_url_button`, но с прямым чтением `b.textContent` через `execute_script` — НЕ через флакующий browser-log путь, которым падал automation-attempt. Живой прогон на канонической сборке (`Install-App`, source_commit `59be96c6...`, versionCode 12/`dev-local`): `PYTEST_EXIT=0`, дословный attachment «observed labels» = `['Copied!']` — подпись сменилась с «Copy URL» на «Copied!» уже на первом опросе после тапа, вместо того чтобы навсегда остаться «Copy URL» (pre-fix поведение, задокументировано AT-BUG-068 тремя независимыми прогонами ДО фикса). Red→green переход между pre-fix диагностикой AT-BUG-068 и этим прогоном на ОДНОМ коде-пути — различающая сила есть, это не совпадение.

Дефекты-собратья: точечная сверка `grep -n "\.then(function" ao3_bridge.js` (не полный аудит файла — за пределы scope верификации намеренно не выходил) нашла ещё одну `.then()`-цепочку — `fetchAndAppend()` (`ao3_bridge.js:595-649`, infinite-scroll `fetch(url).then(r => r.text()).then(html => ...)`) — но у неё ЕСТЬ `.catch(function () { _loadBusy = false; })` (`:649`), просто без user-facing фидбека (не тот же класс дефекта: сбрасывает internal busy-flag, не оставляет UI молча зависшим для пользователя явным образом, как было с Copy URL). Класс «Promise без `.catch()` вовсе» в этой окрестности файла больше не встречается — сиблингов не найдено.

`lock` снят.

## Чек-лист качества

- [x] Проверены дубликаты: поиск по "Clipboard", "Copy", "writeText" в существующих `bugs/BUG-*.md` — не найдено; это новая находка
- [x] Суть дефекта ясна: отсутствие `.catch()` и обратной связи при реджекте Promise
- [x] Severity обоснована: minor — DEBUG-функция, не критична, но плохая UX для затронутых устройств
- [x] Репро-шаги пользовательские (Given-When-Then)
- [x] Точная версия кода приложения и якоря (ao3_bridge.js:1067-1087)
- [x] Связь с AT-BUG-068 и TC-188 задокументирована; отличие от AT-BUG-068 чётко
- [x] Рекомендация фикса приложена (минимум — `.catch()` + UI, альтернатива — fallback на execCommand)
- [x] Ни одного изменения в коде приложения не внесено; чтение только
- [x] Класс дефекта идентифицирован (неполная обработка Promise)
