"""Реестр контракта DOM-селекторов, которые `ao3_bridge.js` реально ЧИТАЕТ/ПИШЕТ
(Р2, `docs/tasks/p2-pyramid-bridge.md`) — систематизация класса AT-BUG-074: bridge
скрейпит узел X, но НИ ОДНА device-free фикстура его не несёт, и дефект остаётся
невидим до 40-минутного device-прогона.

НЕ дублирует `framework/web/selectors.py` — тот файл собирает локаторы для
device-АВТОМАТИЗАЦИИ (Appium/Selenium, синтаксис CSS для `find_element`), этот —
контракт САМОГО bridge-скрипта (какой JS-селектор какая функция читает и на каких
фикстурах узел обязан существовать). Пересечение синтаксиса CSS ожидаемо (оба
описывают ту же разметку), пересечение назначения — нет.

Формат: `BridgeSelectorEntry(selector, functions, pages, source, code_token)`:
  - `selector` — CSS-ФОРМА узла для проверки СТРАНИЦ (тест 2,
    `test_contract_pages_carry_declared_selectors.py`): валидный CSS,
    скармливаемый `document.querySelectorAll` напрямую — не обязан быть
    литералом кода (id-селекторы вроде `#kudo_submit` пишутся с `#`, хотя
    код читает узел через `getElementById('kudo_submit')`, без решётки);
  - `functions` — какие функции/маршруты bridge читают или пишут этот узел
    (для навигации по коду при разборе дрейфа — не машинно проверяется);
  - `pages` — какие device-free фикстуры ОБЯЗАНЫ нести узел: либо имя
    сгенерированной записи (`*.mitm`, `scripts/build_replay_recordings.py`),
    либо `"render_*_html (generator)"` — сам генератор `recording_builder.py`
    (для узлов, проверяемых юнитами `test_recording_builder_unit.py` напрямую
    на выводе функции, а не только на собранной записи);
  - `source` (опционально, default `BRIDGE_JS_SOURCE` — путь до
    `ao3_bridge.js` относительно корня репозитория) — файл-носитель
    КОНТРАКТА КОДА для теста 1 (путь тоже относительно корня репозитория).
    По умолчанию — сам bridge; переопределяется, когда узел контрактно
    читает ДРУГОЙ файл (пример: `#kudo_submit` читается инлайн-JS-строкой
    `evalJs(...)` из `BrowserViewModel.kt`, не из `ao3_bridge.js` вовсе —
    Lead-решение 2026-08-19, «гибрид (A)+(B), структурно, без потери
    детекторной силы»: детектор переименования не теряется, просто целится
    в ПРАВИЛЬНЫЙ файл);
  - `code_token` (опционально, default `None`) — литерал, который тест 1
    ищет в `source` ВМЕСТО `selector`. Без него — деривация по умолчанию:
    для ПРОСТОГО id-селектора вида `#name` (без комбинаторов/атрибутов)
    ищется ТОЛЬКО голый токен в кавычках (`'name'`/`"name"`) — закрывает
    разрыв `getElementById(id)` (код без решётки); сырой `selector` (с `#`)
    в поиск НЕ включается (attempt 2, критик-вход Б2 — сырой `#id` матчил
    бы ЛЮБОЕ упоминание строки, включая устаревший КОММЕНТАРИЙ рядом с уже
    переименованным `getElementById`-вызовом, и матчил бы как ПОДСТРОКУ
    надмножество-переименование вроде `#chapters` → `#chaptersV2` — ни
    кавычечная форма не различает контекст комментарий/код (это остаётся
    заявленной слабостью текстового детектора, см. докстринг теста 1), ни
    кавычечный токен не матчит `id + суффикс` (закрывающая кавычка
    граничит точный литерал) — детекторнее, чем сырой вариант, но НЕ
    абсолютная гарантия). Для НЕ-id-селекторов (составные/атрибутные) —
    по-прежнему ищется сам `selector`. Явный `code_token` — когда код НЕ
    адресует узел ни селектором, ни `getElementById`-литералом, а
    паттерном (пример: `input[name="work_search[words_from]"]` — код
    итерирует `form.elements` ДВУМЯ regex'ами, оба несущие экранированный
    префикс `work_search\\[` — `code_token=r"work_search\\["` (СЫРАЯ строка)
    ловит исчезновение самого паттерна-префикса; см. комментарий записи).
    `code_token` не может быть пустой/пробельной строкой (вечнозелёная
    запись иначе — `_search_tokens` в тесте 1 бросает `ValueError`).

N5 (этот модуль, `docs/tasks/p2-pyramid-bridge.md` DAG) заводит НАЧАЛЬНЫЙ реестр
по фактам recon (Р2) — N6 (контракт-слой, СТРОГО после N5) доводит `pages` под
ПОЛНЫЙ список записанных страниц и добавляет сами Р2-тесты реестра:
  (1) каждый `selector`/`code_token` встречается в `source` (детектор
      переименования/удаления — ОДНОСТОРОННИЙ, явная граница Р2: НОВЫЙ
      селектор бриджа, никогда не попадавший в реестр, этой проверкой не
      ловится; компенсация — bridge в `state/impact-map.yaml` остаётся
      `wide_impact`, Р5);
  (2) каждая страница из `pages` несёт узлы ВСЕХ селекторов, заявленных на неё.
Оба теста живут в `framework/tests/bridge/test_contract_*.py` (N6), не здесь.

ВНЕ скоупа реестра (Р2, явная строка): динамически СОБИРАЕМЫЕ селекторы —
`label[for=…]` (id генерируется AO3, не литерал в bridge) и `'work_' + id`
(id — данные, не CSS-константа)."""
from __future__ import annotations

from dataclasses import dataclass

# Путь до `ao3_bridge.js` ОТНОСИТЕЛЬНО КОРНЯ РЕПОЗИТОРИЯ — дефолт поля
# `source` (см. докстринг `BridgeSelectorEntry` ниже) и то, что читает
# `bridge_js_path`-фикстура `conftest.py` (сверено — то же значение).
BRIDGE_JS_SOURCE = "app-under-test/app/src/main/assets/ao3_bridge.js"

# Путь до `BrowserViewModel.kt` ОТНОСИТЕЛЬНО КОРНЯ РЕПОЗИТОРИЯ — единственный
# на сегодня `source`-override реестра (`#kudo_submit`, класс AT-BUG-035):
# узел читается инлайн-JS-строкой `evalJs(...)` ИЗ ЭТОГО файла, не из
# `ao3_bridge.js` (Lead-решение 2026-08-19, см. докстринг `BridgeSelectorEntry`).
BROWSER_VIEW_MODEL_KT_SOURCE = (
    "app-under-test/app/src/main/java/com/example/ao3_wrapper/ui/browser/BrowserViewModel.kt"
)


@dataclass(frozen=True)
class BridgeSelectorEntry:
    selector: str
    functions: tuple[str, ...]
    pages: tuple[str, ...]
    source: str = BRIDGE_JS_SOURCE
    code_token: str | None = None


REGISTRY: tuple[BridgeSelectorEntry, ...] = (
    # --- Листинг: инъекция Rate-кнопки + getWorkData (initial injection, ao3BridgeInit) ---
    BridgeSelectorEntry(
        selector='li[id^="work_"].work.blurb',
        functions=("ao3BridgeInit (initial injection)", "applyRatings", "applyAllFilters", "getWorkData"),
        pages=(
            "listing_basic.mitm",
            "listing_duplicate_work.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "render_listing_html (generator)",
        ),
    ),
    BridgeSelectorEntry(
        selector='h4.heading a:not([rel="author"])',
        functions=("getWorkData",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector='h4.heading a[rel="author"]',
        functions=("getWorkData",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector="h5.fandoms.heading a.tag",
        functions=("getWorkData",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector=".stats dd.words",
        functions=("getWorkData",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector="ul.tags.commas li.relationships a.tag",
        functions=("getWorkData",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector="ul.tags.commas li.freeforms a.tag",
        functions=("getWorkData",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector="p.datetime",
        functions=("ao3BridgeInit (btn-wrap insertion anchor)",),
        pages=("listing_basic.mitm", "render_listing_html (generator)"),
    ),
    # --- Work-страница: onWorkPageInfo (AT-BUG-074) ---
    BridgeSelectorEntry(
        selector="h2.title.heading",
        functions=("onWorkPageInfo",),
        pages=("work_with_download.mitm", "render_work_page_html (generator)"),
    ),
    BridgeSelectorEntry(
        selector="h3.byline a",
        functions=("onWorkPageInfo",),
        pages=("work_with_download.mitm", "render_work_page_html (generator)"),
    ),
    # N6 (Р2 контракт-слой): `pages` доведены под ПОЛНЫЙ список записанных
    # `.mitm`, эмпирически подтверждённых `test_contract_pages_carry_declared_
    # selectors.py` (querySelectorAll через bridge-harness/jsdom на каждом
    # text/html flow) — ЛЮБОЙ `.mitm`, чей work-page flow построен
    # `render_work_page_html` (`recording_builder.py`), несёт ЭТИ узлы (N5
    # расширил генератор dd.relationship/dd.freeform/dd.fandom/dd.words/
    # #chapters/#kudo_submit — см. докстринг `render_work_page_html`), не
    # только "render_work_page_html (generator)" сам по себе (было — не-блокер
    # 1 критика N5: "их пока не проверяет НИЧТО", т.к. НИ ОДНА реальная
    # запись не была заявлена). `listing_duplicate_work.mitm`/
    # `sort_filter_form.mitm` НЕ несут work-страницу (render_listing_html/
    # реальный tag-listing без `/works/<id>` flow) — исключены (эмпирически
    # 0 совпадений).
    BridgeSelectorEntry(
        selector="dd.relationship a.tag",
        functions=("onWorkPageInfo",),
        pages=(
            "listing_basic.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "work_with_download.mitm",
            "work_with_download_epub.mitm",
            "work_no_epub_link.mitm",
            "work_multi_chapter.mitm",
            "render_work_page_html (generator)",
        ),
    ),
    BridgeSelectorEntry(
        selector="dd.freeform a.tag",
        functions=("onWorkPageInfo",),
        pages=(
            "listing_basic.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "work_with_download.mitm",
            "work_with_download_epub.mitm",
            "work_no_epub_link.mitm",
            "work_multi_chapter.mitm",
            "render_work_page_html (generator)",
        ),
    ),
    # --- Work-страница: auto-mark-as-read metadata scrape (onScroll, AT-BUG-074) ---
    BridgeSelectorEntry(
        selector="dd.fandom a",
        functions=("onScroll (auto-mark-as-read metadata scrape)",),
        pages=(
            "listing_basic.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "work_with_download.mitm",
            "work_with_download_epub.mitm",
            "work_no_epub_link.mitm",
            "work_multi_chapter.mitm",
            "render_work_page_html (generator)",
        ),
    ),
    BridgeSelectorEntry(
        selector="dd.words",
        functions=("onScroll (auto-mark-as-read metadata scrape)",),
        pages=(
            "listing_basic.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "work_with_download.mitm",
            "work_with_download_epub.mitm",
            "work_no_epub_link.mitm",
            "work_multi_chapter.mitm",
            "render_work_page_html (generator)",
        ),
    ),
    BridgeSelectorEntry(
        selector="#chapters",
        functions=("onScroll (auto-mark-as-read chapters gate)",),
        pages=(
            "listing_basic.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "work_with_download.mitm",
            "work_with_download_epub.mitm",
            "work_no_epub_link.mitm",
            "work_multi_chapter.mitm",
            "render_work_page_html (generator)",
        ),
    ),
    BridgeSelectorEntry(
        selector="#selected_id",
        functions=("ao3ReportProgress (reading progress)",),
        pages=("work_multi_chapter.mitm",),  # ao3BridgeInit деградирует мягко
        # (sel ? ... : 1) — единственная фикстура-носитель добавлена AT-BUG-089
        # (2026-08-20); НЕ добавлен "render_work_page_html (generator)" — у
        # него `chapter_titles` дефолтится в `None`, select не рендерится,
        # тест ушёл бы в красное (см. `_GENERATOR_PAGES` в
        # `test_contract_pages_carry_declared_selectors.py`).
    ),
    # --- Kudos (AT-BUG-035) --- N6: `pages` доведены под тот же полный
    # список work-page `.mitm`, что dd.*/#chapters выше (`#kudo_submit`
    # тоже вставляется `render_work_page_html`, см. её докстринг) — было
    # только `work_with_download.mitm`. `source` (Lead-решение 2026-08-19,
    # тест 1): узел читается инлайн-JS-строкой `evalJs(workTab.id,
    # "var b=document.getElementById('kudo_submit');if(b)b.click();")` из
    # `BrowserViewModel.kt:806`, а НЕ из `ao3_bridge.js` (в котором строки
    # "kudo"/"kudo_submit" нет вовсе, ни в коде, ни в комментарии — сверено
    # `Grep -i kudo` по файлу) — детектор теста 1 целится в ПРАВИЛЬНЫЙ файл,
    # не теряется как исключение.
    BridgeSelectorEntry(
        selector="#kudo_submit",
        functions=("evalJs kudos auto-click (BrowserViewModel.kt)",),
        pages=(
            "listing_basic.mitm",
            "listing_paginated.mitm",
            "works_multi.mitm",
            "work_with_download.mitm",
            "work_with_download_epub.mitm",
            "work_no_epub_link.mitm",
            "work_multi_chapter.mitm",
            "render_work_page_html (generator)",
        ),
        source=BROWSER_VIEW_MODEL_KT_SOURCE,
    ),
    # --- Sort & Filter форма AO3 (реальная запись, НЕ генерируется) ---
    BridgeSelectorEntry(
        selector="#include_relationship_tags",
        functions=("injectMainPairingCheckbox",),
        pages=("sort_filter_form.mitm",),
    ),
    BridgeSelectorEntry(
        selector="#exclude_relationship_tags",
        functions=("injectExcludeMainPairingCheckbox",),
        pages=("sort_filter_form.mitm",),
    ),
    BridgeSelectorEntry(
        selector="#work-filters",
        functions=(
            "injectMainPairingCheckbox (submit listener)",
            "injectExcludeMainPairingCheckbox (submit listener)",
            "injectSaveFilterButton",
        ),
        pages=("sort_filter_form.mitm",),
    ),
    # `code_token` (Lead-решение 2026-08-19, тест 1; ИСПРАВЛЕНО attempt 2 —
    # критик-вход Б1: экранирование в источнике не было сверено при первой
    # диктовке): bridge НЕ адресует это поле поимённо — `injectSaveFilterButton`
    # (`ao3_bridge.js:1002`/`1009`) итерирует `form.elements` и матчит КАЖДЫЙ
    # элемент ДВУМЯ regex'ами `/^(include_|exclude_)?work_search\[/` и
    # `/^(include_|exclude_)work_search\[(fandom|character|relationship|
    # freeform)_ids\]\[\]$/` — ОБА несут ЭКРАНИРОВАННЫЙ префикс
    # `work_search\[` (буквальный `\` перед `[` в исходнике — внутри JS
    # regex-литерала `[` обязан быть экранирован). Токен БЕЗ бэкслеша
    # (`"work_search["`) матчил бы ТОЛЬКО чужую строку `ao3_bridge.js:1022`
    # (`form.querySelector('select[name="work_search[language_id]"]')` —
    # другая переменная, `langSelect`, тот же физический литерал случайно
    # совпал бы, не детектируя нужный regex). `r"work_search\["` (СЫРАЯ
    # строка с бэкслешем) целится ИМЕННО в оба regex-префикса (эмпирически:
    # 2 попадания текстовым поиском, обе на строках 1002/1009); `selector`
    # здесь — CSS-форма ОДНОГО конкретного представителя семьи полей для
    # теста 2 (страница реально несёт этот input), а не то, что код ищет
    # литералом. Ровно оговорка Р2 "динамически собираемые селекторы вне
    # скоупа реестра", применённая СТРУКТУРНО: `code_token` ловит
    # исчезновение САМОГО ПАТТЕРНА-ПРЕФИКСА в коде (переименование
    # `work_search` в ОБОИХ regex уронит его), не конкретного поля
    # `words_from`.
    BridgeSelectorEntry(
        selector='input[name="work_search[words_from]"]',
        functions=("injectSaveFilterButton",),
        pages=("sort_filter_form.mitm",),
        code_token=r"work_search\[",
    ),
    # --- Пагинация (listing_paginated.mitm) — layout-НЕ-гейтировано (DOM-присутствие
    # ссылки, не геометрия/скролл) — сам ТРИГГЕР append (fetch+scroll-listener) остаётся
    # L3, но сама разметка ссылки — валидный device-free контракт-объект. ---
    BridgeSelectorEntry(
        selector="ol.pagination li.next a, .pagination li.next a",
        functions=("syncNextLinks", "fetchAndAppend (append-триггер — L3, layout-гейтирован)"),
        pages=("listing_paginated.mitm",),
    ),
)
