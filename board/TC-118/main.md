---
key: "TC-118"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Числовая проба предпосылки guard'а: узлы вне whitelist с собственным обработчиком в теле живой work-страницы (live)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-13T15:11:55Z"
updated: "2026-08-13T15:11:55Z"
archived: false
resolution: "done"
---

# Числовая проба предпосылки guard'а: узлы вне whitelist с собственным обработчиком в теле живой work-страницы (live)

_Спроецировано из `test-cases/canary/TC-118.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-118 — Числовая проба: сколько узлов вне whitelist guard'а реально несут собственный обработчик на живой work-странице

## Предусловия
- Приложение запущено с чистыми данными, режим **live**, тестовая учётка залогинена
  в WebView (та же конвенция входа, что TC-066).
- Вкладка Browse открывает произвольную реальную work-страницу archiveofourown.org
  (`pathname` соответствует `^/works/\d`).
- Общие предусловия тап-зон (docs/01 §9, строки ~786-800): нижняя панель свёрнута,
  >=2 открытых вкладки, высота документа >= 3× `innerHeight` — включены для
  консистентности контекста области (см. заметку ниже: сам подсчёт от них не
  зависит, тапы этим кейсом не делаются).

## Сценарий (Given-When-Then)

**Given** приложение запущено live, залогинено в WebView, открыта произвольная
реальная work-страница archiveofourown.org (`pathname ^/works/\d`), страница
полностью загрузилась (`onPageFinished`, bridge инжектирован); нижняя панель
свёрнута, открыто >=2 вкладок, высота документа >= 3× `innerHeight`

**When** в JS-контексте страницы выполняется ЕДИНЫЙ подсчёт, СИММЕТРИЧНЫЙ
предикату самого guard'а (`ao3_bridge.js:1155`:
`e.target.closest('a, button, input, select, textarea, label, summary,
[role="button"]')` — guard ищет ПРЕДКА через `closest`, не сам узел, и
whitelist по role — это ИМЕННО `[role="button"]`, не любой `[role]`):
`Array.from(document.body.querySelectorAll('[onclick]')).filter(node =>
!node.closest('a, button, input, select, textarea, label, summary,
[role="button"]'))` — кандидат обязан (i) нести признак СОБСТВЕННОГО
обработчика (атрибутный `onclick` — единственный класс, измеримый статическим
DOM-запросом, см. границу валидности ниже) И (ii) не иметь ни самого узла, ни
ЛЮБОГО его предка в whitelist-наборе — через `closest`, а не через изолированный
тег/role самого узла (правка B1/B2 critic-входа 2026-07-28: прежняя версия
считала любой `[role]` вне набора тегов кандидатом независимо от наличия
обработчика — ложный положительный результат на разметке вроде
`role="main"/"navigation"/"article"`, которую реально несёт сама work-страница,
см. таблицу ниже)

**Then** — числовой: репортится ЦЕЛОЕ число N = длина отфильтрованного массива —
конкретное значение на конкретной странице, не оценка «мало/много»
**And** N == 0 ⇒ риск R-02 в части ЭТОЙ work-страницы закрывается ФАКТОМ **для
класса атрибутных onclick-обработчиков** (заметка о классе кода — «guard
теоретически уязвим, но живых узлов-кандидатов этого класса не предъявлено» —
остаётся, кейсов сверх пробы не требуется); N > 0 ⇒ предпосылка предъявлена —
узлы(-кандидаты) с их селекторами/атрибутами прикладываются как находка ДЛЯ
test-strategist (пере-оценка §5), баг по самому числу этим кейсом (test-designer)
НЕ заводится — сначала требуется воспроизвести двойное срабатывание НА
предъявленном узле (это делает TC-120 того же дизайна, либо отдельный follow-up)

**Граница валидности пробы (B3, не решать самостоятельно — вопрос вынесен
владельцу):** проба измеряет ТОЛЬКО атрибутные `onclick`-обработчики, видимые
статическим DOM-запросом. Обработчики, зарегистрированные
`addEventListener`/jQuery `.on()`/делегированные — реальный стек живого AO3
(`jquery`/`jquery-ui`/`rails`/`application`/`bootstrap-dropdown` и т.д., см.
`bugs/AT-BUG-016.md:169-173`) — из DOM НЕ перечислимы ни одним селектором и этой
пробой НЕ видны. Следствие: `N == 0` закрывает риск R-02 фактом только для
класса атрибутных обработчиков; более широкий класс (JS-регистрация
обработчиков) этим кейсом НЕ измерен и остаётся открытым. **Доработка attempt
3 (N2):** предикат также не видит сам `<body onclick>` — запрос идёт от
`document.body.querySelectorAll(...)`, а `querySelectorAll` от узла НЕ включает
сам этот узел в результат (только потомков), поэтому обработчик, повешенный
атрибутом `onclick` НА САМ `<body>`, не будет обнаружен; и содержимое любых
`<iframe>` на странице — кросс-document, DOM-запрос из родительского контекста
их не видит вовсе (нужен отдельный `contentDocument.querySelectorAll(...)` на
каждый iframe, который эта проба не делает). Вопрос — сохраняет ли
владелец критерий «N==0 закрывает риск фактом», зная про эту границу, —
был вынесен владельцу (правило 11а CLAUDE.md); **РЕШЕНО владельцем
2026-07-28: критерий СОХРАНЁН С СУЖЕНИЕМ** до класса атрибутных
`onclick`-обработчиков (полный текст решения — `docs/01-test-strategy.md`
§9, блок `bridge-tap-zone-guard`). JS-класс остаётся named-not-covered;
триггер пересмотра — первый живой инцидент двойного срабатывания от
JS-зарегистрированного обработчика.

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Страница | произвольная реальная `archiveofourown.org/works/<id>` |
| Предикат пробы | `[onclick]`, отфильтрованный `!node.closest('a, button, input, select, textarea, label, summary, [role="button"]')` — симметрично `ao3_bridge.js:1155` |
| Ожидаемое N (текущая гипотеза) | 0 — реальный AO3-markup work-страницы (см. `PROJECT.md`/наблюдения CH-005) не содержит атрибутных `onclick`-узлов вне whitelist-цепочки предков; проба верифицирует это эмпирически, а не принимает как данность. Реальные `role`-атрибуты work-страницы (`role="main"`, `role="navigation"`, `role="article"` и т.п. — критик нагрепал role=article×20/navigation×3/link×2/tooltip/search/main/contentinfo, role=button НОЛЬ, на `sort_filter_form.mitm`) корректно НЕ учитываются предикатом: без собственного `onclick` они не кандидаты вовсе |
| Граница валидности | измеряет только атрибутные `onclick`; `addEventListener`/jQuery-обработчики не наблюдаемы из DOM (см. Then) |

## Заметки для автоматизации
- Однократный `driver.execute_script(...)`, возвращающий JSON `{"count": N,
  "details": [...]}` — `details` включает `outerHTML.slice(0, 200)` каждого
  найденного узла для приложения к находке test-strategist, если N > 0.
  Реализация внутри `execute_script`: `Array.from(document.body.
  querySelectorAll('[onclick]')).filter(n => !n.closest('a, button, input,
  select, textarea, label, summary, [role="button"]'))` — ОДИН запрос,
  отфильтрованный через `closest`, не два изолированных подсчёта тега/role
  (правка critic-входа 2026-07-28, B1/B2: прежняя версия считала любой узел с
  `[role]` не-whitelisted-тега кандидатом независимо от `closest`-предка и от
  наличия обработчика — см. Then).
- **Граница валидности (B3, НЕ решать самостоятельно):** этот предикат видит
  только атрибутные `onclick`. `addEventListener`/делегированные обработчики
  (jquery/jquery-ui/rails/application/bootstrap-dropdown — реальный стек живого
  AO3, `bugs/AT-BUG-016.md:169-173`) из DOM НЕ перечислимы никаким селектором.
  Названная (не реализованная) возможность расширить измеримый класс:
  monkey-patch `EventTarget.prototype.addEventListener` (логирующий каждую
  регистрацию) ДО того, как страница получает шанс что-либо зарегистрировать —
  для СВОЕГО кода (`ao3_bridge.js`) это осуществимо (пропатчить перед его
  инъекцией); для стороннего JS AO3 (googleapis/jquery, грузится раньше bridge)
  патч должен встать раньше их скриптов, что не гарантировано через
  `onPageFinished`/`evaluateJavascript` без перехвата на уровне
  `WebViewClient.onPageStarted` (или раньше) — техническая осуществимость не
  проверена; владелец 2026-07-28 решил направление НЕ разведывать (критерий
  сохранён с сужением до атрибутного класса — см. `docs/01-test-strategy.md`
  §9, блок `bridge-tap-zone-guard`), пересмотр — по первому живому инциденту
  двойного срабатывания от JS-обработчика.
- Общие предусловия тап-зон (нижняя панель, >=2 вкладки, высота документа) —
  включены в Given по требованию DoD дизайна области, НО функционально на ЭТОТ
  Then не влияют: подсчёт — статический DOM-запрос, тапов не делает и не
  проверяет скролл/fullscreen. Единственное ФАКТИЧЕСКИ значимое предусловие —
  `pathname ^/works/\d` (сам guard в коде проверяет только его, `ao3_bridge.js
  :1154`). Оставлены явно per требование дизайна области — не убирать молча.
- Маркер: `@pytest.mark.p0 @pytest.mark.live`.
- Live-падение (Cloudflare interstitial, R-03) триажится по обычной live-
  конвенции (§4 docs/01), как в TC-066.
- Сиблинг: TC-119/TC-120 (replay) — поведенческий контроль самого guard'а на
  known-фикстурных узлах; эта проба и они интерпретируются ВМЕСТЕ (проба без
  поведенческого контроля неинформативна — см. §9 docs/01).
- Не путать с багом: находка N > 0 — это ВХОД для пере-оценки §5 test-strategist,
  не самостоятельный тикет от test-designer (явное non-goal этого диспатча).
- **Попытка автоматизации 2026-07-29 (test-automator, attempt 1): реализовано, не
  подтверждено прогоном — env fail-fast.** 2 прогона подряд упали ИДЕНТИЧНЫМ
  env-классом (`ReadTimeoutError`/`TimeoutError` от Appium HTTP-канала к сессии) на
  `browser_steps.open_live_listing` -> `contexts.in_webview` — диагноз деградации
  среды (docs/06 §5), `automated_by` не заполнялся.
- **Попытка автоматизации 2026-07-29 (test-automator, attempt 2): оборвана
  транзиентной 500-ошибкой API** до завершения прогона; `automated_by` был
  преждевременно проставлен без witness, координатор откатил.
- **Подтверждено 2026-07-30 (test-automator, attempt 3): 3 зелёных прогона
  подряд** (`Invoke-Pytest tests/canary/test_ao3_selectors.py -k
  test_no_non_whitelisted_onclick_candidates_on_live_work_page`, PYTEST_EXIT=0
  каждый раз, 18.4–27.0с). Числовой результат первого прогона (Allure-вложение
  `tc-118-non-whitelisted-onclick-candidates`): **N = 0** — на посещённой живой
  work-странице нет узлов вне whitelist guard'а с собственным атрибутным
  `onclick` (текущая гипотеза подтверждена эмпирически, риск R-02 закрыт фактом
  для класса атрибутных обработчиков, см. Then/B3 выше). Тест написан
  (`framework/tests/canary/test_ao3_selectors.py::
  test_no_non_whitelisted_onclick_candidates_on_live_work_page`), локатор whitelist
  вынесен в `framework/web/selectors.py::TAP_ZONE_GUARD_WHITELIST` (симметрично
  `ao3_bridge.js:1155`, единый предикат, как требует Then), assert-функция —
  `framework/steps/browser_steps.py::assert_no_non_whitelisted_onclick_candidates`.
  `automated_by` заполнен. Статус кейса не менялся (F1 — решает test-reviewer).
- **Доработка по критик-вердикту (test-automator, 2026-07-30): добавлен
  ПОЗИТИВНЫЙ ЯКОРЬ идентичности документа.** Критик доказал: N=0 сам по себе
  не отличим от «страница — Cloudflare-интерстишл на `readyState=complete` БЕЗ
  реального контента» (интерстишл естественно не содержит атрибутных onclick
  вне whitelist — пустое множество не значит «прочитан work»). Все сиблинги
  (TC-119/120/121/122) несут позитивный якорь в Then/ассерте; TC-118 был
  единственным исключением. Фикс (вариант A критик-вердикта) — в том же
  `execute_script` (`framework/steps/browser_steps.py::
  assert_no_non_whitelisted_onclick_candidates`) ДО ассерта `count == 0`
  теперь снимаются и заассертены: (1) `location.pathname` матчит `^/works/\d`
  (симметрично `ao3_bridge.js:1154`); (2) присутствует хотя бы один узел
  реального контента work-страницы — `selectors.WORK_PAGE_CONTENT_MARKERS =
  "h2.title.heading, h3.byline, dd.fandom, dd.words"`, те же узлы, что читает
  сам `ao3_bridge.js:1139-1142` для скрапинга метаданных (список сверен
  чтением файла 2026-07-30, НЕ взят из критик-отчёта как данность —
  `#workskin`/`div.work` из черновика критика в bridge НЕ встречаются, не
  использованы). Оба поля вложены в тот же Allure-аттач
  `tc-118-non-whitelisted-onclick-candidates`, что и count, для аудита.
  **3 зелёных прогона подряд** (`Invoke-Pytest tests/canary/test_ao3_selectors.py
  -k test_no_non_whitelisted_onclick_candidates_on_live_work_page -q`,
  PYTEST_EXIT=0 каждый раз, 12.6–39.9с). Содержимое Allure-аттача первого
  прогона: `pathname='/works/87997831/chapters/233262621'
  has_content_marker=True count=0 details=[]` — позитивный якорь подтверждён
  (реальная work-страница с контентом, не интерстишл), N=0 подтверждён
  содержательно. `automated_by` не менялся (тот же тест). Статус кейса не
  менялся (F1).
- **Починка TEST_BUG (test-maintainer, 2026-08-11, `runs/RUN-20260811-0405.md`
  failure-analyst): устойчивый выбор live work-страницы + различение 404/
  Cloudflare в диагностике.** Root cause: `browser_steps.open_live_listing`
  открывает `LIVE_LISTING_URL` (`archiveofourown.org/works`, лента «Latest
  Works» — самая волатильная лента сайта), тест брал `work_ids[0]` — голову
  этой ленты — без проверки живучести и без фолбэка; работа за этим id может
  быть удалена/скрыта между скрапом листинга и навигацией на её страницу, AO3
  в этом случае штатно отдаёт **404** (не Cloudflare, как ошибочно предполагал
  прежний текст ассерта — сверено скриншотом, page source и независимым
  `curl` с хоста, дважды). Class-check (D-0043): `grep -n "open_work_page\|
  open_work("` по `framework/tests/**` — 18 call sites, ВСЕ остальные 17
  навигируют на `work.ao3_id` из детерминированных фикстур; TC-118 —
  единственный, берущий id с живой волатильной ленты, класс шире одного теста
  не идёт (тот же вывод независимо получил failure-analyst, «Дефекты-собратья
  (д)» отчёта прогона).

  Фикс (правильный слой — `framework/steps/`, не тесты):
  `browser_steps.probe_live_work_page_identity(driver)` — лёгкая (без подсчёта
  onclick-кандидатов, без исключения) проверка того же двойного якоря
  идентичности документа, что уже нёс финальный ассерт (`pathname ^/works/\d`
  + `WORK_PAGE_CONTENT_MARKERS`), плюс `document.title` для диагностики.
  `rating_steps.open_live_work_page(driver, candidate_ids, max_attempts=5)` —
  перебирает кандидатов ленты ПО ПОРЯДКУ (голова первой), открывает каждого,
  возвращает первого живого; неживые пропускаются с Allure-заметкой (title
  страницы вложен — отличает штатную AO3 404 от Cloudflare-интерстишла).
  Тест теперь: `work_ids = assert_blurb_selector_matches_headings(...)`
  → `work_id = rating_steps.open_live_work_page(driver, work_ids)` вместо
  `work_ids[0]` + голого `open_work_page`.

  Диагностика (DoD п.2): `assert_no_non_whitelisted_onclick_candidates`
  теперь снимает `document.title` в том же `execute_script` и классифицирует
  нештатную страницу через `_diagnose_non_live_page(title)` — «404» в title →
  «штатная страница ошибки AO3», «just a moment» (без учёта регистра) →
  «вероятен Cloudflare-интерстишл (R-03)», иначе — «неопознанная нештатная
  страница, title=...» — вместо прежнего безусловного «вероятен Cloudflare».
  Этот ассерт теперь работает как ЗАЩИТА В ГЛУБИНУ (defense-in-depth) ПОСЛЕ
  фолбэка, а не единственная линия проверки — сообщение об ошибке явно
  называет это (если сработал, значит фолбэк либо не применялся, либо
  страница деградировала МЕЖДУ проверкой фолбэка и этим вызовом).

  **Верификация ЗАБЛОКИРОВАНА fail-fast средой (2026-08-11, `state/
  escalations.md` ESC-025) — код-фикс НЕ подтверждён живым 3х-зелёным
  прогоном.** 3 попытки `Invoke-Pytest tests/canary/test_ao3_selectors.py -k
  test_no_non_whitelisted_onclick_candidates_on_live_work_page -q` подряд, 3
  падения, ВСЕ на `app_steps.wait_ui_ready` — шаге ДО первой строки, которую
  трогает этот фикс (`open_live_listing`/`open_live_work_page` не успевают
  выполниться ни разу за 3 попытки). Диагностический мини-прогон (`Get-Device`
  → DEVICE; Appium `:4723/status` → ready; `dumpsys window` → приложение в
  фокусе; `io.appium.settings` запущен; Event Log 15 минут → NO MATCHING
  EVENTS, qemu-процесс не перезапускался) подтвердил: устройство/Appium живы,
  но `android.webkit.WebView` стабильно не находится в дереве за бюджет —
  падение по среде, неотличимое от падения по коду; продолжать прогоны на
  этой среде запрещено правилом CLAUDE.md «Fail-fast среды» (docs/06 §5).
  Полный диагноз — `ESC-025`. `arch_check`/`validate_frontmatter` чисты
  относительно правки (репо несёт предсуществующие находки в файлах ДРУГОЙ
  параллельной сессии — не мои, не трогал). `automated_by`/`reviewed_at`/
  `red_probe` не менялись — тест тот же, только его шаги выбора work-страницы
  и диагностика внутри `framework/steps/`; статус кейса не менялся
  (F1/F-переоценка — не мандат test-maintainer). **Следующий шаг:** после
  ремонта среды (владелец — Lead/человек по диагнозу ESC-025) — просто
  повторить 3х прогон БЕЗ изменений в коде фикса.

- **Продолжение попытки (test-maintainer, attempt 2, 2026-08-11T03:22:16Z):
  рецидив ТОГО ЖЕ env-класса, теперь в изоляции.** Свежая сверка
  непосредственно перед прогоном — `Get-Device` → `DEVICE: emulator-5554`,
  Appium `:4723/status` → `ready:true` — обе здоровы; никакой параллельной
  device-работы в этом окне (в отличие от предыдущего окна с TC-009-
  воркером). Прогон `Invoke-Pytest tests/canary/test_ao3_selectors.py -k
  test_no_non_whitelisted_onclick_candidates_on_live_work_page -q` →
  `1 failed in 26.63s`, `PYTEST_EXIT=1`, падение на ТОМ ЖЕ шаге
  `app_steps.wait_ui_ready` (`TimeoutException`/`NoSuchElementError`) — ДО
  первой строки моего фикса. `dumpsys window` сразу после падения:
  `mCurrentFocus`/`mFocusedApp` = `com.example.ao3_wrapper/.MainActivity`
  (приложение в фокусе, не крашнулось). По протоколу «Fail-fast среды» —
  дальнейшие прогоны (2-я/3-я попытка этого окна) НЕ выполнялись: рецидив
  идентичного класса в изоляции подтверждает диагноз ESC-025 и исключает
  гипотезу «вклад коллизии двух device-воркеров» — root cause глубже, ещё не
  локализован. Полный разбор — `ESC-025` (продолжение записи). Код фикса
  по-прежнему НЕ верифицирован живым прогоном; `app_steps.wait_ui_ready` не
  трогал (вне scope). Лок и статус кейса не менялись.

- **Верификация подтверждена (test-maintainer, 2026-08-13, `ESC-025`
  закрыт).** После холодного рестарта эмулятора (`Start-Emulator
  -WritableSystem`, унаследованный процесс НЕ переиспользован — на момент
  старта `Get-Device` уже отдавал `NO DEVICE`, лишнего
  `qemu-system-x86_64.exe`-процесса не было) — **3 зелёных прогона подряд**
  (`Invoke-Pytest tests/canary/test_ao3_selectors.py -k
  test_no_non_whitelisted_onclick_candidates_on_live_work_page -q`,
  `PYTEST_EXIT=0` каждый раз, 31.08s / 14.30s / 14.49s). Allure-трасса
  первого прогона подтверждает, что фикс реально исполнился (не был обойдён
  средой): шаг «открыта первая ЖИВАЯ (не 404/интерстишл) work-страница из
  кандидатов [...]» с полным списком из 20 id ленты живой ленты — новый код
  `rating_steps.open_live_work_page` реально в работе (не голый
  `open_work_page`); вложение `tc-118-non-whitelisted-onclick-candidates`:
  `pathname='/works/89686901' title='I Loved You First - jenniferskywalker
  - Multifandom [Archive of Our Own]' has_content_marker=True count=0
  details=[]` — содержательный якорь и N=0 подтверждены. Падение на
  `app_steps.wait_ui_ready` (env-класс ESC-025) не повторилось ни разу за
  3 попытки в этом окне — консистентно с диагнозом «остаточная деградация
  эмулятора после qemu-краха», снятым холодным рестартом. `automated_by`/
  `reviewed_at`/`red_probe`/статус кейса не менялись — верификация
  подтверждала уже закоммиченный код-фикс живым прогоном, ничего в
  `framework/` не правила.

## Ревью автотеста (F1, test-reviewer, 2026-07-30)

**Вердикт: ПРОЙДЕНО** — `Approved -> Automated`, `automation_status: active`.

Чек-лист F1 (все пункты):
1. **Архитектура (C1):** `python scripts/arch_check.py` → «ошибок 0,
   предупреждений 0»; `ALLOWLIST` в `scripts/arch_check.py:80` пуст (исключение
   «под себя» не добавлялось). Тест-модуль импортирует только `steps` +
   `allure`/`pytest`, локаторы/JS-предикат живут в `framework/web/selectors.py`
   и `framework/steps/browser_steps.py`, `sleep` в пути теста нет — ожидания
   через `core/waits` (`wait_until` на `readyState`, bounded `navigate`).
2. **Traceability:** `@allure.id("TC-118")` == id кейса; маркеры
   `@pytest.mark.p0` (frontmatter `priority: P0`) + `@pytest.mark.live`
   соответствуют «Заметкам для автоматизации»; `automated_by` указывает на
   существующую функцию `test_ao3_selectors.py:502`.
3. **Соответствие по смыслу:** предикат теста
   (`browser_steps.py:503-514`) — единый `document.body.querySelectorAll(
   '[onclick]')` + `!n.closest(selectors.TAP_ZONE_GUARD_WHITELIST)`; whitelist
   СЛОВО В СЛОВО совпал со сверенной строкой самого guard'а
   (`ao3_bridge.js:1155`, прочитана при ревью). Ассерт — свойство ВСЕГО
   множества узлов тела (N == 0), не единичный пример; при N > 0 узлы
   (`outerHTML[:200]`) уходят в Allure как находка для test-strategist, баг не
   заводится (совпадает с Then/non-goal). Позитивный якорь идентичности
   документа присутствует и НЕ декоративен: `pathname ~ ^/works/\d`
   (`browser_steps.py:524`, симметрично `ao3_bridge.js:1154`) и
   `WORK_PAGE_CONTENT_MARKERS` (`browser_steps.py:529`, узлы из
   `ao3_bridge.js:1139-1142`) — оба заассерчены ДО `count == 0`
   (`browser_steps.py:536`), фальсифицируемость доказана красной пробой 2 ниже.
4. **Фикстуры и данные:** тест не сеет и не пишет данные (статический
   DOM-подсчёт, тапов нет), от порядка других тестов не зависит; отсутствие
   `clean_app` безопасно и дополнительно проверено: в `ao3_bridge.js` нет НИ
   ОДНОГО атрибутного `onclick` (grep case-insensitive, 0 совпадений при
   позитивном контроле `addEventListener` = 16) — инжекции приложения не могут
   исказить N ни при каком состоянии БД.
5. **Flake-риск:** живой AO3 заявлен явно (кейс live, не replay);
   Cloudflare-риск R-03 закрыт с двух сторон — `open_live_listing`
   (повторная навигация по бюджету) и содержательный якорь контента, который
   превращает интерстишл в ОСМЫСЛЕННОЕ падение, а не в ложный зелёный.
   Гонок с Compose-анимациями нет (нативный UI не драйвится).
6. **Независимое воспроизведение (ревьюером, эмулятор `emulator-5554`,
   `Get-Device` → `DEVICE: emulator-5554`):**
   `Invoke-Pytest tests/canary/test_ao3_selectors.py -k
   test_no_non_whitelisted_onclick_candidates_on_live_work_page -v` →
   `1 passed ... in 21.84s`, `PYTEST_EXIT=0`. Контрольный повтор после отката
   порчи — `1 passed in 12.46s`, `PYTEST_EXIT=0`.
7. **Красная проба (мутационная), 2026-07-30 — две одиночные порчи, каждая
   откачена в том же ходе:**
   - Порча A (существо Then): в `framework/steps/browser_steps.py:505`
     `querySelectorAll('[onclick]')` → `querySelectorAll('[role]')` (класс
     ложноположительных кандидатов, который и чинила правка B1/B2). Прогон:
     `1 failed in 14.03s`, `PYTEST_EXIT=1`, падение на `browser_steps.py:536`
     (`assert count == 0`) с осмысленным текстом: «найдено 5 узл(ов) вне
     whitelist guard'а… [form#search role=search, span.tip role=tooltip,
     div#main role=main, div#chapters role=article, div#footer
     role=contentinfo]» — не таймаут-мусор. Откат: `git checkout --
     framework/steps/browser_steps.py`, `git status --short framework/` пуст.
   - Порча B (позитивный якорь): в `framework/web/selectors.py:143`
     `WORK_PAGE_CONTENT_MARKERS` → `"h2.tc118-red-probe-absent-marker"`.
     Прогон: `1 failed in 14.27s`, `PYTEST_EXIT=1`, падение на
     `browser_steps.py:529` (`assert has_content_marker`) с текстом «на
     странице pathname='/works/89534311' не найдено ни одного узла реального
     контента work-страницы… N=0 НЕ является доказательством отсутствия
     кандидатов». Якорь ДЕЙСТВИТЕЛЬНО стоит на пути ассерта и фальсифицируем —
     требование критик-входа выполнено не декларативно. Откат: `git checkout --
     framework/web/selectors.py`, дерево `framework/` чисто.

Замечаний, требующих доработки, нет. Наблюдение без блокирующего статуса
(не меняет вердикт): `WORK_PAGE_CONTENT_MARKERS` берёт `h3.byline`/`dd.fandom`,
тогда как bridge читает `h3.byline a`/`dd.fandom a` — якорь чуть шире
bridge-контракта, но `h2.title.heading`/`dd.words` совпадают точно, и роль
списка — именно OR-присутствие реального контента, поэтому ослабления сути нет.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
