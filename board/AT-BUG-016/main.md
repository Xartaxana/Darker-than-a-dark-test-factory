---
key: "AT-BUG-016"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "TC-040 (Save filter dialog) детерминированно крашит qemu-эмулятор (0xc0000005) при переходе в Settings — реальный live-рендер тяжёлой страницы + недождённая пост-save навигация"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-040", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-19T01:52:53Z"
updated: "2026-07-19T01:52:53Z"
archived: false
resolution: null
---

# TC-040 (Save filter dialog) детерминированно крашит qemu-эмулятор (0xc0000005) при переходе в Settings — реальный live-рендер тяжёлой страницы + недождённая пост-save навигация

_Спроецировано из `bugs/AT-BUG-016.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-016 — TC-040 детерминированно крашит qemu при live-рендере + Settings-переходе

## Окружение
- Хост WHPX-гипервизор (см. environment-setup.md), эмулированный GPU.
- Live-forward сеть: `framework/core/mitm.py` (`server_replay_extra=forward`) —
  суб-ресурсы страницы, не попавшие в `.mitm`-запись, реально уходят в сеть.

## Суть долга

`test_save_filter_profile` (TC-040) грузит `sort_filter_form.mitm` —
запись РЕАЛЬНОЙ тяжёлой страницы `archiveofourown.org/tags/Fluff/works`
(`recording_builder.py:84-85`, `SORT_FILTER_FORM_URL`), чьи внешние
CSS/JS/шрифты/картинки тянутся ЖИВЬЁМ через forward (не самодостаточная
синтетическая фикстура, в отличие от стабильного `listing_basic.mitm`
у сиблинга TC-042). После `confirmSaveFilter` (`BrowserViewModel`)
приложение уходит в ФОНОВУЮ навигацию на live-URL с `work_search[...]`
параметрами (тоже не в `.mitm` → forward → ВТОРАЯ реальная тяжёлая
страница) — тест эту навигацию НЕ дожидается и сразу вызывает
`app_steps.open_tab(driver, "Settings")`, где `_find_pill` дампит ВСЁ
accessibility-дерево (`//*[@clickable]`) поверх WebView, ещё активно
рендерящего live-контент.

Пиковая конкуренция (UiAutomator2 tree-dump + GPU-компоновка живой
страницы) крашит `qemu-system-x86_64.exe` (код исключения `0xc0000005`,
faulting-модуль `unknown` — характерно для падения в
динамически-сгенерированном коде TCG/GPU-эмуляции).

## Эмпирика (critic, 2026-07-18)

- Воспроизведено САМ с ПЕРВОЙ попытки на подтверждённо здоровом свежем
  окружении (`Start-Emulator -WritableSystem` → `Get-Device: DEVICE` →
  `Install-App: Success` → `Start-Appium: ready`).
  `Invoke-Pytest tests/test_filter_profiles.py::test_save_filter_profile -v`
  → `1 failed` за 67.87s, точка падения буквально совпадает с отчётом
  воркера (`navigation.py::_find_pill`, `open_tab("Settings")`,
  `test_filter_profiles.py:130`). Teardown: `adb.exe: no devices/emulators
  found`. Повторный `Get-Device` → `NO DEVICE`.
- Независимая улика: Windows Application Event Log — краш
  `qemu-system-x86_64.exe` в 07:41:57 (код `0xc0000005`), ~35с внутри
  прогона критика — момент, совпадающий с рендером live-страницы при
  навигации в Settings.
- Историческая корреляция (6 крашей `0xc0000005` за 4 дня): оба кластера
  (07-18 сессия test-automator; 07-15 запись `sort_filter_form.mitm`
  через live-WebView при AT-BUG-006 инкремент 2) привязаны к ОДНОЙ и той
  же тяжёлой странице `archiveofourown.org/tags/Fluff/works`.
- Контрольная группа: `test_delete_filter_profile` (TC-042) зелёный 3×
  (07-15/07-17/07-18) на ТОЙ ЖЕ Appium/replay-инфраструктуре, но на
  самодостаточной синтетической `listing_basic.mitm` (без forward,
  без недождённой навигации) — единственная переменная, отличающая
  крашащийся TC-040 от стабильного TC-042, это дизайн самого TC-040
  (реальный live-рендер), не среда как таковая.
- Отклонённая гипотеза: JS DOM-инъекция (`sort_filter_form_page.py`,
  `execute_script` на CSS-hidden форму вместо Selenium `.click()`) —
  НЕ виновник; операции тривиальны, выполняются успешно ДО точки краша
  (`set_word_count_min`/`tap_save_filter_button` проходят, падение
  позже, на открытии Settings).

## Критерий готовности (Fixed)

Один из вариантов (выбор — за координатором/test-designer, D0043 роль
critic ограничена диагнозом):
1. Сделать `sort_filter_form.mitm` самодостаточной (записать/встроить
   суб-ресурсы, чтобы forward не уходил в live), как у стабильных
   синтетических фикстур; и/или записать post-save filtered-URL в
   `.mitm`, чтобы `confirmSaveFilter` не форвардил живьём.
2. Дождаться завершения фоновой навигации ДО `open_tab("Settings")`,
   чтобы tree-dump не совпадал с mid-render живой страницы.
3. Env-митигация (гипотеза, не проверена): `-gpu swiftshader_indirect`
   (софт-рендер) — проверить, переживает ли реальные страницы.

Плюс: `test_save_filter_profile` даёт 3 зелёных прогона подряд на
эмуляторе, TC-041 регрессия зелёная, `automated_by` TC-040 заполнен,
СНЯТ временный `@pytest.mark.skip(reason="AT-BUG-016")` (добавлен
координатором 2026-07-18 как guard против подхвата тестом
regression/p1-прогонами до фикса — находка critic-входа TC-041).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-07-19 (test-maintainer, попытка B4, заход 1) | без изменений app-under-test | TC-040 (3 прогона), TC-041 (1 прогон) | TC-040: PASS/FAIL/FAIL (не 3 подряд зелёных); TC-041: PASS | Open — фикс не найден, эскалировано |
| 2026-07-19 (test-maintainer, попытка B4, заход 3, critic-directed) | без изменений app-under-test | TC-040 (3 прогона подряд, `Get-Device: DEVICE` перед каждым), TC-041 (1 прогон регрессии) | TC-040: `PYTEST_EXIT=0` ×3 (`41.00s`/`40.31s`/`40.23s`, все `1 passed`, ни одного краша qemu — `Get-Device: DEVICE` устойчиво между прогонами); TC-041: `PYTEST_EXIT=0` (`1 passed in 45.86s`) | **Fixed** — 3 зелёных подряд достигнуты, DoD выполнен |

(Это заполнение — test-maintainer, не fix-verifier, т.к. B4/test_debt — фикс
тестовой системы, сборка приложения не участвует; следующий формальный
верификатор при необходимости — fix-verifier по обычному потоку приёмки.)

## Обсуждение

**2026-07-18T05:35:00Z — координатор (Lead, Sonnet, критик-вход диагностики
PASS):** заведено по вердикту critic-диагностики (правило 3б CLAUDE.md —
непонятный баг получил critic-вход ДО того, как Lead начал отлаживать сам).
Классификация воркера ("env fail-fast, случайная нестабильность, test_debt
не заводить") отклонена — краш детерминирован, воспроизведён с первой
попытки на здоровом окружении, коррелирует с конкретной живой страницей.
Не смешивается с AT-BUG-006 (сетевой ReadTimeoutError, не краш эмулятора)
и AT-BUG-012/014 (краш НА BOOT снапшота, не mid-test). Гипотеза
JS-инъекции как причины — отклонена по коду и по факту (падение позже
точки JS-вызовов). TC-040 остаётся `Approved`, `automated_by` не
заполнен — правило 14 пропустит его при следующих проходах, пока этот
test_debt открыт (guard правила 14: не покрытые Open test_debt-багом).
TC-041 НЕ затронут (другая фикстура, уже проходил чисто) — доводится
отдельным диспатчем этого же прохода.

Найденная ось для SIBLING_MAP/докладки (не расширено, не подтверждено
дефектом — только названо): поверхность «рендер РЕАЛЬНЫХ live AO3-страниц
в эмуляторном WebView» — кандидаты `browser_steps.py::open_stable_tall_page`
(`/tos`, TC-047/048/049 через AT-BUG-015) и `browser_screen.py` живая
work-страница. Эти сиблинги ЛЕГЧЕ (дожидаются `readyState complete`, нет
конкурентного tree-dump поверх mid-render) — witness их краша нет, ось
называется для будущей точечной проверки координатором, не сканом.

**2026-07-19T01:19:51Z — test-maintainer (B4, попытка ремедиации, ЭСКАЛИРУЕТСЯ):**
lock снят, `status` остаётся `Open` — фикс не найден за 2 захода на этом
ярусе (правило 6 CLAUDE.md), нужен critic/Lead-вход.

Начал с варианта 2 (самый дешёвый, рекомендован координатором): в
`framework/steps/browser_steps.py::save_filter_profile_as` добавлено
ожидание `document.readyState == 'complete'` НОВОЙ страницы (URL сменился
относительно того, что было открыто до Save) перед возвратом управления —
закрывает ИМЕННО ту гонку, что диагностировал critic (tree-dump поверх
mid-render). Первый прогон TC-040 подтвердил: `PYTEST_EXIT=0`, `1 passed
in 46.65s` (лог: `tests/test_filter_profiles.py::test_save_filter_profile[sort_filter_form.mitm]
PASSED`).

Повторный прогон (2-й подряд, та же правка) упал НЕ на Settings, а
раньше — на самой ПЕРВОЙ загрузке формы (`open_sort_filter_form` →
`open_listing` ожидание якорь-текста), `TimeoutException`, затем
`adb.exe: no devices/emulators found` при попытке вернуться в нативный
контекст (`PYTEST_EXIT=1`, `1 failed in 90.85s`). Windows Event Log
(`Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000}`)
подтвердил независимую улику: краш `qemu-system-x86_64.exe` в 03:04:32
(локальное время), код `0xc0000005` — тот же класс, что в исходном
диагнозе critic, но на ДРУГОМ шаге (первая живая страница, не
пост-save навигация). Это показало, что вариант 2 закрывает только ОДНУ
из как минимум ДВУХ точек риска: сама фикстура `sort_filter_form.mitm`
живьём форвардит суб-ресурсы (CSS/JS/шрифты/картинки) уже на ПЕРВОЙ
загрузке, независимо от Settings-гонки.

Перешёл к варианту 1 (частично): `sort_filter_form.mitm` пересобран
самодостаточным ДЛЯ ПЕРВОЙ живой страницы (`/tags/Fluff/works`) —
скриптом (не входит в `recording_builder.py`/`build_replay_recordings.py`,
т.к. `SORT_FILTER_FORM_FILENAME` намеренно НЕ перегенерируется этим
пайплайном, см. модульный докстринг `recording_builder.py`) из тела
записанного flow вырезаны ВСЕ `<link>` (5 stylesheet + sandbox.css),
ВСЕ `<script>` (src= внешние: `livevalidation`, googleapis
jquery/jquery-ui, `jquery.scrollTo`/`livequery`/`rails`/`application`/
`bootstrap-dropdown`/`jquery-shuffle`/`jquery.tokeninput`/`jquery.trap`/
`ao3modal`/`js.cookie`/`filters`, плюс инлайновые блоки, зависящие от
`jQuery`/`$j`, включая fallback `document.write` на случай блокировки
googleapis) и `src` у единственного `<img>` (логотип, не записан в
`.mitm`). Проверено (`framework/web/sort_filter_form_page.py`,
`ao3_bridge.js::injectSaveFilterButton`): форма/кнопка ищутся чистым
`document.querySelector`/`form.elements`, БЕЗ jQuery/site-JS зависимости
(сам DOM формы генерируется сервером, не JS; видимость через
`narrow-hidden` тест и так обходит через JS DOM API, не полагаясь на
`displayed=True`) — усечение безопасно для семантики теста.
`work_search_words_from`/`work-filters`/`name="commit"` подтверждены
присутствующими в очищенном теле (проверочный скрипт, вывод приложен
к диффу в scratchpad сессии). Остальные 7 flows `.mitm` (главная `/`,
`token_dispenser.json` x2, autofill-протобаф x2, `imageset.png`) не
тронуты.

Прогон с обоими фиксами упал СНОВА, на этот раз внутри
`save_filter_profile_as` (переход в WebView-контекст сразу после тапа
"Save") — `WebDriverException: Device emulator-5554 is not online`
(`PYTEST_EXIT=1`, `1 failed in 56.03s`). Event Log: краш
`qemu-system-x86_64.exe` в 03:14:33 (локальное время), код `0xc0000005`
— СОВПАДАЕТ по месту с исходным диагнозом critic (пост-save навигация),
но теперь это ВТОРАЯ, всё ещё живая навигация: она не покрыта фиксом 2
(тело сама фикстура для НЕЁ не подготовлена — `work_search[...]`-URL
динамический, не записан в `.mitm`), поэтому её собственный
`<link>/<script src>` (та же реальная разметка archiveofourown.org)
по-прежнему форвардится вживую целиком.

**Итог: 1 PASS / 2 FAIL из 3 прогонов TC-040 сегодня** (после Get-Device
здорового окружения перед каждым — env-негатив не сработал: устройство
было `DEVICE` перед обоими упавшими прогонами, `NO DEVICE` только
ПОСЛЕ краша, что подтверждает crash mid-test, не отсутствие
устройства с самого начала). TC-041 регрессия зелёная (`PYTEST_EXIT=0`,
`1 passed in 46.06s`, фикстура/шаги не пересекаются с TC-040). Оба
ремедиационных фикса ОСТАВЛЕНЫ в дереве (`browser_steps.py`
ожидание readyState — устраняет диагностированную critic'ом гонку;
`sort_filter_form.mitm` — устраняет форвард на ПЕРВОЙ загрузке) как
реальные, не маскирующие улучшения, но НЕДОСТАТОЧНЫЕ для DoD (3 зелёных
подряд): `@pytest.mark.skip(reason="AT-BUG-016...")` возвращён на
`test_save_filter_profile` (обновлённая причина в самом тесте),
`automated_by` TC-040.md не заполнен, `status` остаётся `Open`.

Разброс места краша между попытками (первая загрузка / вторая
навигация) плюс исторический паттерн (test-automator тоже видел
краш дважды идентично на Settings-шаге, critic — с первой попытки, я —
1 pass из 3) говорит о том, что нестабильность НЕ строго детерминирована
по шагу — вероятно, общая хрупкость GPU-эмуляции (WHPX) под нагрузкой
рендера ЛЮБОЙ тяжёлой live-страницы archiveofourown.org, а не только
конкретная гонка tree-dump. Это НЕ квалифицируется как fail-fast триггер
docs/06 §5 (тот про 2 ИДЕНТИЧНЫХ `ReadTimeoutError`/`TimeoutError` на
ОДНОМ И ТОМ ЖЕ шаге — здесь разные шаги и разный класс ошибки, реальный
краш процесса qemu, не таймаут), поэтому не стал звать диагностику
Get-Device/health-check как blocked-по-среде — но называю тот же
класс явно для критика: возможно, обе оставшиеся точки (первая
навигация ДОКОНЦА не изолирована, если не 100% суб-ресурсов ушли из
`<head>`/`<body>` — не проверял глубже второго уровня; вторая
навигация ВООБЩЕ не изолирована) нужно закрывать вместе, ЛИБО нужен
вариант 3 (env: `-gpu swiftshader_indirect`) как системная мера —
не пробовал (правки `tasks.ps1`/параметров эмулятора — инфраструктурный
мехнизм с более широким blast radius, вне узкого скоупа test-maintainer
по framework/test-cases, D-0043/правило 9: чинить класс, но правки
общей среды — решение выше этого яруса).

Рекомендация для critic/Lead: (а) либо завершить вариант 1 —
записать/подготовить И post-save filtered-URL (детерминирован:
`ao3_bridge.js` строит `qs` из `form.elements`/`work_search[...]`
чистым JS, без jQuery — можно точно вычислить итоговый query string
статическим разбором дефолтных значений формы + `"1000"` из теста —
и добавить как ВТОРОЙ `.mitm`-flow с тем же усечением `<link>/<script>`,
что сделано для первой страницы); (б) и/или попробовать вариант 3
(`-gpu swiftshader_indirect`) как отдельный диагностический прогон,
если (а) снова не даст 3/3.

**2026-07-19T01:52:53Z — test-maintainer (B4, попытка 3, critic-directed, ЗАКРЫЛА
долг):** выполнена критик-директива буквально — довёл вариант 1 до конца.

1. **Вычислен и записан ВТОРОЙ self-contained flow.** Написал скрипт
   (scratchpad сессии, не в репо), который парсит РЕАЛЬНУЮ разметку
   `#work-filters` из уже записанного тела `sort_filter_form.mitm` (HTML
   `<form>`) и детерминированно повторяет логику
   `ao3_bridge.js::injectSaveFilterButton` (тот же порядок `form.elements`,
   тот же фильтр по имени/типу/`checked`/`value`, тот же `encodeURIComponent`)
   с ОДНИМ отличием — `work_search[words_from]` переопределён на `"1000"`
   (как делает сам тест через `set_word_count_min`). Результат: РОВНО 2
   параметра непусты в реальной форме — `work_search[sort_column]=revised_at`
   (единственный `<select>` с `selected`) и переопределённый `words_from`;
   все чекбоксы/радио на дефолтной форме либо не checked, либо checked со
   значением `""` (`crossover`/`complete` — оба отфильтровываются JS'ом как
   falsy). Итоговый URL:
   `https://archiveofourown.org/tags/Fluff/works?work_search%5Bsort_column%5D=revised_at&work_search%5Bwords_from%5D=1000`.
   Записан как 9-й flow в `.mitm` (тем же телом, что и первая страница —
   тест не проверяет контент второй страницы, только сам факт последующего
   успешного перехода в Settings) через `recording_builder.make_html_get_flow`
   + `write_flows` (полная перезапись списка flows, т.к. `FlowWriter`
   поддерживает только `"wb"`). Подтверждено ДИАГНОСТИЧЕСКИМ mitm-addon'ом
   (временный `-s` скрипт в `mitm.py::start_replay`, ОТКАЧЕН сразу после
   диагностики через `git checkout` — не часть фикса): реальный запрос
   `GET .../tags/Fluff/works?work_search%5Bsort_column%5D=revised_at&work_search%5Bwords_from%5D=1000`
   дал `is_replay=response` — байт-в-байт совпадение, live-forward не
   произошёл. Краш qemu ни разу не воспроизвёлся ни в одном из последующих
   прогонов.
2. **Грепнул остаточные `http`/`src=`/`@import`/`url(` в очищенном теле
   первой live-страницы** (`(?i)<link|<script|@import|url\(`,
   `(?i)src=|srcset=|<img|<iframe|background-image|poster=`) — ноль
   совпадений (единственный `<img>` уже без `src`, единственные `http(s)://`
   — три обычных `<a href>` в футере, не авто-загружаемые). Глубина
   усечения подтверждена достаточной, второй уровень вложенности не нашёл.
3. **Вскрылась ВТОРАЯ причина, не входившая в исходный диагноз critic.**
   После полной сетевой изоляции первый повторный прогон упал НЕ крашем
   qemu, а `TimeoutException` на `open_tab("Settings")` — устройство
   ЖИВО (`Get-Device: DEVICE` сразу после), т.е. другой класс отказа.
   Диагностика диагностическим addon'ом + захват page-source (Allure XML)
   показала: WebView реально ушёл на live-страницу `/people/search` (200
   `is_replay=None` — форвард, при этом ЦЕЛЕВОЙ replay-flow только что
   матчился `is_replay=response` — т.е. это НЕ форвард содержимого нашего
   flow, а ПОБОЧНЫЙ клик по ссылке, взятой ИЗ него). Корень: страница —
   реальная разметка AO3 с CSS-классами `.narrow-hidden` (форма
   `#work-filters`) и `.dropdown .menu` (выпадающие подменю хедера,
   включая `<a href="/people/search">People</a>`), которые в РЕАЛЬНОМ AO3
   скрыты внешней CSS (`<link rel=stylesheet>`), а в НАШЕЙ self-contained
   truncation эта CSS вырезана целиком → элементы рендерятся РАЗВЁРНУТО.
   `framework/screens/navigation.py::_find_pill` («самый нижний кликабельный
   не-WebView View», используется `ensure_visible()`/`_expand_pill()` перед
   каждым `open_tab`) фильтрует кандидатов только по `"WebView" not in class`
   — но виртуальные a11y-узлы ВНУТРИ WebView (ссылки/чекбоксы страницы)
   экспонируются с классами `android.view.View`/`android.widget.*`, НЕ
   содержащими строку "WebView", и потому НЕ отфильтровываются. Развёрнутая
   без CSS форма/подменю дают a11y-узлы с большим `bounds.y`, `_find_pill`
   иногда выбирает ссылку страницы вместо нативной ручки-пилюли и кликает
   по ней — реальная live-навигация уводит WebView необратимо (Settings
   после этого никогда не появится, что и объясняет исходный симптом
   `open_tab("Settings")` timeout, задокументированный ещё test-automator'ом
   ДО этой сессии). Чинить `_find_pill` (расширять фильтр на потомков
   WebView) — за пределами узкого скоупа B4 (это framework-механизм с
   более широким blast radius, затрагивающий ВСЕ тесты, использующие
   `open_tab`); вместо этого восстановил CSS-скрытие МИНИМАЛЬНЫМ inline
   `<style>` (`.narrow-hidden, .hidden, .dropdown .menu { display: none
   !important; }`) в теле ОБОИХ `/tags/Fluff/works` flow — ноль сетевых
   запросов, точное соответствие поведению живого AO3 (форма и так скрыта
   на узких вьюпортах в реальности — это не маскировка, а восстановление
   правильного поведения, случайно снятого грубой truncation).
4. **DoD подтверждён witness'ом:** TC-040 — 3 прогона подряд,
   `Get-Device: DEVICE` перед каждым, `PYTEST_EXIT=0`/`1 passed` все три
   раза (41.00s, 40.31s, 40.23s), ни одного краша qemu ни в одном из ВСЕХ
   прогонов этого захода (включая 2 диагностических до финального фикса
   стиля — оба упали таймаутом на "Settings", НЕ крашем qemu). TC-041 —
   `PYTEST_EXIT=0`, `1 passed in 45.86s`. `@pytest.mark.skip` снят,
   `automated_by` в `test-cases/filter-profiles/TC-040.md` заполнен
   (`framework/tests/test_filter_profiles.py::test_save_filter_profile`).
   `status` TC-040.md НЕ переведён в `Automated` этим ходом — по
   `schemas/transitions.yaml` это легально только `by: [test-reviewer]`.

Гипотеза «systemic SwiftShader-JIT-хрупкость под тяжёлым live-рендером»
(из предыдущей записи) — НЕ подтвердилась как единственная причина: после
полной сетевой изоляции (закрытие последней live-forward точки) краш qemu
пропал полностью, а оставшаяся нестабильность оказалась ДЕТЕРМИНИРОВАННЫМ
локаторным багом (`_find_pill` кликает в WebView), не средовой хрупкостью.
Стоп-гейт (вариант 3, env-митигация GPU) не потребовался — не пришлось
столкнуться ни с одним крашем qemu после полной изоляции.

Новый блокер, найденный в ходе этой починки (механизм `_find_pill`
латентно хрупок для ЛЮБОГО другого теста с `open_tab`, не только для этой
фикстуры) — заведён отдельным test_debt `bugs/AT-BUG-019.md`
(`debt_kind: weak_locator`, minor, Open), не расширяя scope этого B4-захода
(D-0037: баг + доклад, решение о диспатче — за Lead/test-strategist).
Сам инстанс на `sort_filter_form.mitm` закрыт локально (восстановление
CSS-скрытия, выше) — AT-BUG-019 про сам механизм `_find_pill`.
