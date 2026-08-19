"""Реестр контракта DOM-селекторов, которые `ao3_bridge.js` реально ЧИТАЕТ/ПИШЕТ
(Р2, `docs/tasks/p2-pyramid-bridge.md`) — систематизация класса AT-BUG-074: bridge
скрейпит узел X, но НИ ОДНА device-free фикстура его не несёт, и дефект остаётся
невидим до 40-минутного device-прогона.

НЕ дублирует `framework/web/selectors.py` — тот файл собирает локаторы для
device-АВТОМАТИЗАЦИИ (Appium/Selenium, синтаксис CSS для `find_element`), этот —
контракт САМОГО bridge-скрипта (какой JS-селектор какая функция читает и на каких
фикстурах узел обязан существовать). Пересечение синтаксиса CSS ожидаемо (оба
описывают ту же разметку), пересечение назначения — нет.

Формат: `BridgeSelectorEntry(selector, functions, pages)`:
  - `selector` — CSS-селектор буквально ИЗ `ao3_bridge.js` (не адаптация);
  - `functions` — какие функции/маршруты bridge читают или пишут этот узел
    (для навигации по коду при разборе дрейфа — не машинно проверяется);
  - `pages` — какие device-free фикстуры ОБЯЗАНЫ нести узел: либо имя
    сгенерированной записи (`*.mitm`, `scripts/build_replay_recordings.py`),
    либо `"render_*_html (generator)"` — сам генератор `recording_builder.py`
    (для узлов, проверяемых юнитами `test_recording_builder_unit.py` напрямую
    на выводе функции, а не только на собранной записи).

N5 (этот модуль, `docs/tasks/p2-pyramid-bridge.md` DAG) заводит НАЧАЛЬНЫЙ реестр
по фактам recon (Р2) — N6 (контракт-слой, СТРОГО после N5) доводит `pages` под
ПОЛНЫЙ список записанных страниц и добавляет сами Р2-тесты реестра:
  (1) каждый `selector` встречается в `ao3_bridge.js` (детектор переименования/
      удаления — ОДНОСТОРОННИЙ, явная граница Р2: НОВЫЙ селектор бриджа, никогда
      не попадавший в реестр, этой проверкой не ловится; компенсация — bridge в
      `state/impact-map.yaml` остаётся `wide_impact`, Р5);
  (2) каждая страница из `pages` несёт узлы ВСЕХ селекторов, заявленных на неё.
Оба теста живут в `framework/tests/bridge/test_contract_*.py` (N6), не здесь.

ВНЕ скоупа реестра (Р2, явная строка): динамически СОБИРАЕМЫЕ селекторы —
`label[for=…]` (id генерируется AO3, не литерал в bridge) и `'work_' + id`
(id — данные, не CSS-константа)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeSelectorEntry:
    selector: str
    functions: tuple[str, ...]
    pages: tuple[str, ...]


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
    BridgeSelectorEntry(
        selector="dd.relationship a.tag",
        functions=("onWorkPageInfo",),
        pages=("render_work_page_html (generator)",),
    ),
    BridgeSelectorEntry(
        selector="dd.freeform a.tag",
        functions=("onWorkPageInfo",),
        pages=("render_work_page_html (generator)",),
    ),
    # --- Work-страница: auto-mark-as-read metadata scrape (onScroll, AT-BUG-074) ---
    BridgeSelectorEntry(
        selector="dd.fandom a",
        functions=("onScroll (auto-mark-as-read metadata scrape)",),
        pages=("render_work_page_html (generator)",),
    ),
    BridgeSelectorEntry(
        selector="dd.words",
        functions=("onScroll (auto-mark-as-read metadata scrape)",),
        pages=("render_work_page_html (generator)",),
    ),
    BridgeSelectorEntry(
        selector="#chapters",
        functions=("onScroll (auto-mark-as-read chapters gate)",),
        pages=("render_work_page_html (generator)",),
    ),
    BridgeSelectorEntry(
        selector="#selected_id",
        functions=("ao3ReportProgress (reading progress)",),
        pages=(),  # ao3BridgeInit деградирует мягко (sel ? ... : 1) — ни одна
        # текущая фикстура узел не несёт; явно пусто, не молчаливый пропуск.
    ),
    # --- Kudos (AT-BUG-035) ---
    BridgeSelectorEntry(
        selector="#kudo_submit",
        functions=("evalJs kudos auto-click (BrowserViewModel.kt)",),
        pages=("work_with_download.mitm", "render_work_page_html (generator)"),
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
    BridgeSelectorEntry(
        selector='input[name="work_search[words_from]"]',
        functions=("injectSaveFilterButton",),
        pages=("sort_filter_form.mitm",),
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
