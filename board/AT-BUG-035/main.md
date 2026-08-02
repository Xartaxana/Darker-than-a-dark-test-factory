---
key: "AT-BUG-035"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "render_work_page_html не несёт узел #kudo_submit ни в одной replay-фикстуре — блокирует автоматизацию всей области rating/bridge auto-kudos (TC-138..144, ядро BUG-015)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-138", "test_case:TC-139", "test_case:TC-140", "test_case:TC-141", "test_case:TC-142", "test_case:TC-143", "test_case:TC-144", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-02T02:41:00Z"
updated: "2026-08-02T02:41:00Z"
archived: false
resolution: "done"
---

# render_work_page_html не несёт узел #kudo_submit ни в одной replay-фикстуре — блокирует автоматизацию всей области rating/bridge auto-kudos (TC-138..144, ядро BUG-015)

_Спроецировано из `bugs/AT-BUG-035.md` (источник правды).
Статус в нашей машине: **Verified**._

# AT-BUG-035 — Ни одна replay-фикстура не несёт узел `#kudo_submit`, наблюдаемость kudos-эффекта недостижима

## Окружение

Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
`debt_kind: missing_fixture`). Текущая тестируемая сборка 1.10 (versionCode 11).
Класс СМЕЖНЫЙ с `AT-BUG-004`/`AT-BUG-029` (обе — про replay-инфраструктуру для
`rating`/`downloads`), но не дубликат: `AT-BUG-004` закрыл отсутствие
replay-инфраструктуры КАК ТАКОВОЙ, `AT-BUG-029` — недостающую ОДНУ транзакцию для
конкретного `.html`-скачивания. Эта находка — про отсутствующий DOM-узел, по
которому приложение стреляет `evalJs`-кликом, а не про отсутствующую HTTP-
транзакцию: без узла ни один из семи спроектированных kudos-кейсов не может быть
ни закодирован (позитив недостижим), ни осмысленно негативно проверен (негатив
вакуумно-истинен НЕЗАВИСИМО от того, сработал ли предикат — тот же класс, что
`bugs/AT-BUG-029.md` §«Суть долга» про молчаливый провал незаписанного запроса,
и класс «Наблюдаемость негативного Then», зафиксированный Lead 2026-07-30).

## Суть долга

`BrowserViewModel.kt` в ДВУХ местах (`applyRating:859`,
`onRateWorkRequested/pendingPanelSave:1054`) выполняет ровно два вызова
`evalJs` с kudos-кликом (исправлено critic attempt2, 2026-07-31: черновик
ошибочно называл «три места», хотя грепом по
`document.getElementById('kudo_submit')` в файле находится ровно два вызова —
третья ветка, `savePanelRating:743-758`, kudos НЕ кликает вовсе, это и есть
асимметрия путей, см. `bugs/BUG-015.md`):

```kotlin
evalJs(tabId, "var b=document.getElementById('kudo_submit');if(b)b.click();")
```

— то есть весь наблюдаемый эффект правила «rating/bridge: авто-клик kudos»
(`bugs/BUG-015.md`, `docs/01-test-strategy.md` §9) существует ТОЛЬКО если на
работе, показанной в WebView, есть узел с `id="kudo_submit"`, а сам клик
оставляет наблюдаемый след.

Парсинг `framework/data/recording_builder.py::render_work_page_html` (:546-585)
показывает: функция рендерит `#workskin`, `.preface`, `_download_list_html`
(валидную download-ссылку) и три дополнительных узла для tap-zone-guard/
reading-UX (`AT-BUG-030`) — но НИ ОДНОГО узла с `id="kudo_submit"`. Единственное
упоминание «kudos» в модуле — статичный нередактируемый счётчик
`<dd class="kudos">0</dd>` (:301), не интерактивный элемент. Функция ОБЩАЯ для
ВСЕХ фикстур, несущих work-страницу (`build_listing_basic`, `build_work_with_
download`, `build_works_multi`, `build_listing_paginated`) — узла нет ни в одной
из них (`listing_basic.mitm`, `work_with_download.mitm`, `works_multi.mitm`,
`listing_paginated.mitm`).

Следствие для ВСЕХ семи спроектированных кейсов (`TC-138..144`):
- **Позитивы (TC-138, TC-144)** физически недостижимы: `document.getElementById('kudo_submit')`
  вернёт `null`, `if(b)b.click()` — no-op, атрибут `data-kudo-clicked` неоткуда
  взяться. Кейсы невозможно закодировать без узла в принципе, не только
  «сложно проверить».
- **Негативы (TC-139..143)** без узла вакуумно-истинны НЕЗАВИСИМО от того,
  сработал ли level-предикат `:856`/`:1053` — тот же класс ложно-зелёного, что
  `AT-BUG-029` (незаписанная транзакция) и прецедент двух ложных «Replay не
  требуется» из калибровки Lead 2026-07-30 (`bugs/AT-BUG-029.md` цитируется
  промптом test-designer как образец класса): assert «клика не было» истинен
  и при штатной работе, и при недоступном узле, и при реальном срабатывании
  дефекта — негатив не отличает баг от дыры в фикстуре.

Технический приём для инструментирования УЖЕ есть в кодовой базе фикстур —
`_tap_zone_guard_nodes_html` (`recording_builder.py:511/518`) использует
`onclick="this.setAttribute('data-tapped', '1')"` для того же класса задачи
(сделать клик наблюдаемым атрибутом DOM, читаемым `driver.execute_script` через
`framework/core/contexts.py::in_webview`). **Прямой аналог с КОНСТАНТОЙ
неприменим (исправлено critic attempt2, 2026-07-31, B2):** `TC-138`/`TC-144`
Then явно требует различить «ровно один клик» от «два клика» (класс
edge-vs-level этой же области, батарея правил-реакций, пункт
«идемпотентность») — атрибут-константа `'1'` не различает эти случаи: два
клика подряд дали бы то же самое `data-kudo-clicked="1"`, что и один. Узел
несёт ИНКРЕМЕНТНЫЙ счётчик клика, не константу:
`onclick="this.setAttribute('data-kudo-clicked', String(1+Number(this.getAttribute('data-kudo-clicked')||0)));return
false;"` — `return false` предотвращает переход по фиктивному href в
синтетической фикстуре (в реальном AO3 узел — кнопка/ссылка с собственным JS,
не имеющая значения для проверяемого поведения нашего приложения). Baseline
(атрибута нет) читается как `0` (`Number(null||0)`), первый клик даёт `"1"`,
гипотетический двойной клик — `"2"`, отличимый от одинарного.

## Критерий готовности (Fixed)

Минимальный фикс — добавить инструментированный узел `#kudo_submit` В ОБЩУЮ
`render_work_page_html()` (`framework/data/recording_builder.py:546-585`), по
образцу `_tap_zone_guard_nodes_html`, и пересобрать записи
(`python scripts/build_replay_recordings.py`):

```python
kudo_submit_html = (
    '<p class="kudos"><a href="#" id="kudo_submit" role="button" '
    'onclick="this.setAttribute(\'data-kudo-clicked\', '
    'String(1+Number(this.getAttribute(\'data-kudo-clicked\')||0)));'
    'return false;">'
    'Give Kudos</a></p>'
)
```

**Инкрементный счётчик, не константа** (B2, critic attempt2): `TC-138`/`TC-144`
проверяют «ровно один клик, не два» — с константой `'1'` двойной клик
неотличим от одинарного. Baseline (нет атрибута) = `0`, первый клик = `"1"`,
гипотетический повторный клик = `"2"`.

Место вставки — ВНЕ `.wrapper`/тела главы (regression-требование `AT-BUG-030`:
порядок тап-зон-guard/reading-UX узлов ПОСЛЕ `_download_list_html` не должен
меняться): **рядом с `<ul class="work navigation actions">` (сиблингом, не
внутрь)** — вариант «сразу после `_download_list_html(work)` ВНУТРИ неё»
СНЯТ критик-ревью (нит 5, 2026-07-31): `<p>` внутри `<ul>` — невалидная
вложенность (браузер оставит его дочерним узлом `ul`; локаторы
`li.download a` не пострадают, но валидность рендера портить незачем).
Точное место выбирает test-maintainer при фиксе, с обязательной регрессией потребителей
`render_work_page_html` (TC-009 x5, TC-032/033/114/115/116/117, TC-026,
TC-084, TC-119/120/122..127) — вставка НЕ должна сдвигать порядок/индексы
существующих узлов, на которые полагаются их локаторы.

Готово, когда:
- `render_work_page_html()` несёт узел `id="kudo_submit"` с инструментированным
  `onclick`, фиксирующим факт клика атрибутом, читаемым без сети/AO3.
- `listing_basic.mitm`, `work_with_download.mitm`, `works_multi.mitm`,
  `listing_paginated.mitm` пересобраны (`python scripts/build_replay_recordings.py`).
- Новый device-free юнит (аналог `test_recording_builder_unit.py` из
  `AT-BUG-029`) подтверждает: узел присутствует в отрендеренном HTML каждой
  работы, `onclick` содержит `data-kudo-clicked` инкрементным счётчиком (не
  константой «1») — юнит явно проверяет, что ДВА вызова `onclick` подряд (в
  JS-среде юнита или эквивалентной эмуляцией) дают `"1"` затем `"2"`, не `"1"`
  оба раза.
- Регрессия существующих потребителей `render_work_page_html` зелёная:
  `python -m pytest scripts/tests -q` без регресса; смок хотя бы одного
  живого потребителя (например `TC-009` x5 параметризаций или `TC-119/120`
  tap-zone-guard) подтверждает, что новый узел не сломал порядок/локаторы
  существующих assert'ов.
- Ни один из TC-138..144 зелёным прогоном НЕ входит в критерий Fixed этого
  долга — TC-139 (ядро BUG-015) ОСТАЁТСЯ ожидаемо-красным до фикса продуктового
  `bugs/BUG-015.md` (это регрессионный замок, не признак незакрытого долга,
  прецедент `AT-BUG-029`/`bugs/BUG-014.md`); TC-138/140/141/142/143/144 — их
  первый зелёный прогон подтверждает Fixed по факту (реализованы и подключены),
  но формального требования «все шесть зелёные» в критерий не входит, так как
  реализация самих тестов — отдельная работа test-automator/B3, не входящая в
  границы ЭТОГО фикстурного долга (тот же принцип разведения, что `AT-BUG-029`).

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| — | — | — | — | Open, ждёт фикса |
| 2026-08-01 | 1.10 (versionCode 11), фикс не требует пересборки приложения (test_debt) | Долг (не TC-138..144, см. критерий готовности): device-free юнит `framework/tests/test_recording_builder_unit.py` (4 новых теста) + `python -m pytest scripts/tests -q` + живой смок TC-009 (x5)/TC-119/TC-120/TC-121/TC-122 — 3 прогона подряд | Все зелёные, без регресса | test-maintainer: Fixed, ждёт fix-verifier (переход Fixed→Verified не входит в мой guard) |
| 2026-08-02 | 1.10 (versionCode 11), test_debt (framework-only, без пересборки приложения) | НЕЗАВИСИМАЯ верификация fix-verifier (не переиспользую прогоны test-maintainer): (1) чтение кода — `_kudo_submit_html()` подтверждена инкрементным счётчиком (`String(1+Number(this.getAttribute('data-kudo-clicked')\|\|0)))`, НЕ константой, вызов вставлен СИБЛИНГОМ `<ul class="work navigation actions">` (между `</ul>` и `<div class="wrapper">`), не внутрь нeё — `recording_builder.py:548-555,613-616`; (2) `python -m pytest scripts/tests -q` → `792 passed, 1 skipped in 25.25s` (без регресса; 792 против заявленных test-maintainer 783 — разница объясняется другими параллельными изменениями репозитория за сутки, не этим фиксом, ни одного failed); (3) `powershell -NoProfile -ExecutionPolicy Bypass -Command ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest tests/test_recording_builder_unit.py -q"` → `44 passed in 0.26s PYTEST_EXIT=0`; (4) `python scripts/arch_check.py` → `ошибок 0, предупреждений 0`, `python scripts/validate_frontmatter.py` → `ошибок 0, предупреждений 0`; (5) НЕЗАВИСИМЫЙ живой смок на эмуляторе (свой отдельный подъём env.ps1→tasks.ps1→`Start-Emulator -WritableSystem`→`Get-Device` DEVICE→`Install-App` Success→`Start-Appium`, НЕ переиспользую прогоны test-maintainer): `Invoke-Pytest tests/test_rating_listing.py -k rate_work_from_listing_overlay -v` (TC-009, все 5 параметризаций, `listing_basic.mitm`) → `5 passed, 11 deselected in 171.24s PYTEST_EXIT=0`; `Invoke-Pytest tests/canary/test_tap_zone_guard.py -v` (TC-119/120/121/122, `work_with_download.mitm`) → `4 passed in 216.39s PYTEST_EXIT=0`. TC-138..144 сознательно НЕ прогонялись (вне критерия готовности этого долга, п.5 задачи). Appium/эмулятор погашены (`Stop-NodeProcesses` + `adb emu kill`) по завершении. `app-under-test/` не тронут. | Все зелёные, без регресса, независимо подтверждено | fix-verifier: Verified |

## Обсуждение

**2026-07-31 — test-designer, заведение (правило 4 промпта test-designer).**
Блокер обнаружен при проектировании области `rating/bridge: авто-клик kudos`
(§9 docs/01-test-strategy.md, needs-design, вход `bugs/BUG-015.md`). Дизайн ШЕСТИ
кейсов (`TC-138..143`, design-пункт §9 «снятие рейтинга и переход…» разделён на
два — `TC-142`/`TC-143`, тот же принцип, что развёл `TC-116`/`TC-117` для
авто-скачивания) завершён и полон — ограничена ТОЛЬКО автоматизация, ни один
кейс не переведён в `Blocked` (тот же прецедент/основание, что `AT-BUG-029`:
`schemas/transitions.yaml`, `initial: [Draft, Review]`, комментарий у `initial`
и запись `{from: "*", to: Review, ref: "вернуть на доработку (прецедент TC-009:
replay-блокер)"}` легализуют статус `Review` для этого класса ситуации). Один
тикет на ШЕСТЬ кейсов (не по кейсу) — блокер один и тот же (общая функция
`render_work_page_html`), правило test-designer явно требует единый баг на
общий блокер, не россыпь дубликатов.

Проверены дубликаты среди открытых test_debt: не совпадает с `AT-BUG-004`
(инфраструктура replay КАК ТАКОВАЯ, давно Verified), `AT-BUG-029` (недостающая
HTTP-транзакция для download, другой класс пробела — там сеть, здесь DOM-узел),
`AT-BUG-030` (tap-zone-guard/reading-UX узлы — уже присутствуют, этот баг их не
трогает, только добавляет соседний узел с явным regression-требованием не
сдвигать их порядок), `AT-BUG-033`/`AT-BUG-034` (другой домен — log_append.py).

`app-under-test/` не тронут (только чтение `BrowserViewModel.kt` для локализации
мест вызова evalJs). Аналогов класса «общая рендер-функция фикстуры не
несёт узел, нужный целому классу правил-реакций» в других областях (auto-
download, badge-sync) при этом проектировании не замечено — там наблюдаемость
уже обеспечена (download через реальный HTTP-flow, badge через
`window.__ao3Ratings`/DOM-бейдж, оба уже читаемые существующими степами) — не
докладываю новую ось SIBLING_MAP.

**2026-07-31 — test-designer, доработка attempt2 (критик-вход, вердикт
ДОРАБОТАТЬ по 3 блокерам + 5 should-fix, разбор в `test-cases/rating/`).**
Правки этого бага в рамках того же ретрая:
- **S1:** «в трёх местах» исправлено на фактические ДВА вызова `evalJs` с
  kudos-кликом (`:859`, `:1054`, сверено критиком грепом) — черновик attempt1
  посчитал третью (некликающую) ветку `savePanelRating:743-758` как «место»,
  хотя она структурно НЕ содержит вызова; строка `:546-587` (дважды здесь, один
  раз в TC-138) исправлена на фактическую `:546-585` (конец функции —
  закрывающая `"""` на строке 585, не 587).
- **B2:** инструментация `#kudo_submit` переведена с атрибута-константы `'1'`
  на инкрементный счётчик (`String(1+Number(...||0))`) — константа не
  различала один клик от двух, что обесценивало assert «ровно один, не два» в
  TC-138/TC-144. Критерий готовности (юнит-тест) и код-сниппет фикса обновлены
  согласованно.
- **B3 (седьмой кейс, решение Lead):** `test_cases` расширен `TC-144` —
  позитивная граница ТРЕТЬЕЙ ветки (`onRateWorkRequested`/`pendingPanelSave`,
  `:1053-1054`, первое сохранение через панель, запись ещё не в Room) — этот
  call site не был покрыт ни одним кейсом attempt1; заодно закрывает
  позитивный контроль негатива `TC-141` на том же панельном механизме.
- Заголовок бага (`TC-138..143`) и упоминания «шести кейсов»/«трёх мест» по
  тексту приведены к фактическим семи кейсам/двум местам этим же ходом.

**2026-08-01 — test-maintainer, фикс (B4).** Дословно по критерию готовности:

1. **Узел `#kudo_submit`.** Добавлена `_kudo_submit_html()`
   (`framework/data/recording_builder.py`, рядом с `_tap_zone_guard_nodes_html`)
   — ТОЧНО код-сниппет из этого бага (инкрементный `data-kudo-clicked`, не
   константа; `return false` против навигации по фиктивному `href="#"`).
   Вызов вставлен в `render_work_page_html()` СИБЛИНГОМ
   `<ul class="work navigation actions">` — между закрывающим `</ul>` и
   `<div class="wrapper">`, НЕ внутрь `<ul>` (валидность вложенности, критик-
   ревью нит 5 из этого же бага).
2. **Пересборка записей.** `python scripts/build_replay_recordings.py`
   (через `framework/.venv/Scripts/python.exe`, env.ps1) — пересобрал ВСЕ 6
   фикстур; git-диффом изменились ровно 4, несущие work-страницы:
   `listing_basic.mitm`, `work_with_download.mitm`, `works_multi.mitm`,
   `listing_paginated.mitm` (`tab_markers.mitm`/`listing_duplicate_work.mitm`
   байт-идентичны — ожидаемо, они не используют затронутый путь код).
3. **Место вставки.** Проверено ДВУМЯ новыми юнитами
   (`test_render_work_page_html_kudo_submit_is_sibling_not_nested`): узел
   ОТСУТСТВУЕТ внутри блока `<ul>...</ul>` и стоит строго МЕЖДУ `</ul>` и
   `<div class="wrapper">` в исходном HTML — порядок/индексы
   `_download_list_html` (внутри `<ul>`, полностью предшествует) и
   tap-zone-guard/reading-UX узлов (`AT-BUG-030`, внутри `.wrapper`, идут
   строго после) не сдвинуты.
4. **Новый device-free юнит.** `framework/tests/test_recording_builder_unit.py`
   — 4 новых теста (секция «AT-BUG-035»): присутствие узла в отрендеренном
   HTML (`render_work_page_html` напрямую) и в СОБРАННОЙ записи
   (`works_multi.mitm`, обе work-страницы), место вставки (п.3 выше) и
   ИНКРЕМЕНТНОСТЬ счётчика — `_run_kudo_onclick` реально исполняет (`eval`,
   узкий JS→Python транслятор `this.`→`node.`, `||`→`or`) ТЕКСТ `onclick`,
   извлечённый regex'ом из отрендеренного HTML (не переписанную вручную
   копию формулы): два вызова подряд дают `"1"`, затем `"2"`, не `"1"` оба
   раза — witness: `powershell -NoProfile -ExecutionPolicy Bypass -Command
   ". D:\AO3_tests\scripts\tasks.ps1; Invoke-Pytest
   tests/test_recording_builder_unit.py -q"` → `44 passed in 0.26s
   PYTEST_EXIT=0` (было 40 тестов до фикса, +4 новых).
5. **Регрессия.** `D:/AO3_tests/framework/.venv/Scripts/python.exe -m pytest
   scripts/tests -q` → `783 passed, 1 skipped in 23.36s` (skip не связан с
   этим фиксом). `framework/tests` собираются штатно (`--collect-only`
   подтверждён отдельно).
6. **Живой смок на эмуляторе.** Канонический подъём (`env.ps1` → `tasks.ps1`
   → `Start-Emulator -WritableSystem` → `Install-App` [первая попытка упала
   транзиентным `StorageManager.getVolumes()` NPE сразу после boot, устройство
   осталось живым по `Get-Device`, повторная попытка — `Success`; тот же
   класс, что известные транзиентные гонки системных сервисов сразу после
   `boot_completed=1`, не деградация среды] → `Start-Appium`). Прогнан TC-009
   (все 5 параметризаций рейтинга, `LISTING_BASIC_FILENAME`) и
   TC-119/120/121/122 (`tap-zone-guard`, `WORK_WITH_DOWNLOAD_FILENAME`) — оба
   набора используют пересобранные фикстуры с новым узлом. **3 прогона
   подряд, все зелёные:** run1 `5 passed, 11 deselected in 154.66s`
   (только TC-009) + отдельно `4 passed in 193.90s` (tap-zone-guard); run2 и
   run3 (объединённый вызов обеих сюит) — `9 passed, 11 deselected in
   348.24s` и `9 passed, 11 deselected in 344.26s`. Порядок/локаторы
   существующих assert'ов (download-ссылка, tap-zone узлы 1/2, TabStrip,
   RatingOverlay) не пострадали. Appium (`Stop-NodeProcesses`) и эмулятор
   (`adb emu kill`) погашены по завершении.

Ни TC-138..144 не запускались как критерий Fixed (см. «Критерий готовности» —
формально не требуется, это отдельная работа test-automator).
`app-under-test/` не тронут — `git status` подтверждает пусто.

**2026-08-02 — fix-verifier, независимая верификация (mode=verify, D1).**
Подтверждаю Fixed → Verified. Сверка НЕ переиспользовала прогоны
test-maintainer: код перечитан заново (`_kudo_submit_html`, инкрементный
счётчик, место вставки — сиблинг `<ul class="work navigation actions">`);
`scripts/tests`, `test_recording_builder_unit.py`, `arch_check.py`,
`validate_frontmatter.py` перепрогнаны с нуля; живой смок — отдельный подъём
эмулятора (свежая установка приложения, свой Appium), TC-009 (5/5) через
`test_rating_listing.py` и TC-119/120/121/122 через
`framework/tests/canary/test_tap_zone_guard.py` (актуальный `automated_by` из
`test-cases/canary/TC-119..122.md` — файл `test_reading_ux.py`, названный в
задаче, кейсы TC-119..122 больше не покрывает, они переехали в
`tests/canary/test_tap_zone_guard.py`; замечание для координатора, если TC-119
упоминается где-то ещё со старым путём). Все прогоны зелёные, без регресса
порядка/локаторов `_download_list_html`/tap-zone-guard узлов. `known_issue`
уже был `"false"` — сбрасывать не потребовалось. Лок снят, окружение погашено.

## Чек-лист качества
- [x] Проверены дубликаты среди открытых test_debt-багов — не совпадает с
      AT-BUG-004/029/030/033/034 (см. «Обсуждение»)
- [x] Суть долга ясна и воспроизводима по коду
      (`recording_builder.py:546-585 render_work_page_html`,
      `BrowserViewModel.kt:856-861/1053-1054`)
- [x] Severity: minor — блокирует автоматизацию семи P1-кейсов ОДНОЙ области,
      не влияет на уже автоматизированные области (rating/downloads/tabs остаются
      зелёными), дизайн кейсов полон (design не заблокирован), фикс — точечная
      правка одной общей функции + пересборка записей (тот же порядок величины,
      что `AT-BUG-029`, минорный прецедент для многократно бóльшего числа
      заблокированных кейсов — оправдано тем же критерием: «дизайн не
      заблокирован, фикс точечный»)
- [x] Ни одно изменение не внесено в app-under-test/
- [x] `test_cases: ["TC-138", "TC-139", "TC-140", "TC-141", "TC-142", "TC-143", "TC-144"]`
      — все семь кейсов, заблокированных ЭТИМ ОДНИМ блокером
