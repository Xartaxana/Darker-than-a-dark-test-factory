"""Canary-suite (R-02) — поведенческий контроль guard'а тап-зон
(`ao3_bridge.js:1152-1166`, `bridge-tap-zone-guard`, docs/01-test-strategy.md §9
«Дополнение области» 2026-07-28). Фикстурные узлы (`data-tap-marker`) добавлены
`recording_builder.py::render_work_page_html` (AT-BUG-030, Fixed) — тело
work-страницы теперь несёт whitelisted `<button>` со `<span>`-потомком (узел 1),
не-whitelisted `<div onclick>` (узел 2) и филлер высотой >= 3×innerHeight
(узел 3), все три — ПОСЛЕ `_download_list_html` в исходном HTML (регрессия
download-flow TC-032/033 не задета, см. `bugs/AT-BUG-030.md` таблицу
верификации).

TC-119/TC-120/TC-121/TC-122 — четыре грани одного и того же guard'а
(`e.target.closest('a, button, input, select, textarea, label, summary,
[role="button"]')`): TC-119 — whitelisted-узел подавляет зональное действие,
TC-120 — не-whitelisted узел С обработчиком ПРОПУСКАЕТ guard (оба эффекта),
TC-122 — closest-семантика (тап по потомку whitelisted-узла ведёт себя как тап
по самому узлу). Полное геометрическое обоснование (почему средняя треть/band
44-56% обязательны для диагностической силы, а не для физической
достижимости) — `bugs/AT-BUG-030.md`, раздел «Геометрия узлов 1 и 2».

Формулировка позитивных Then-конъюнктов этой сюиты (TC-119/121/122) уточнена
ревью F1 2026-07-29: `dispatchEvent` адресует событие узлу напрямую, минуя
hit-testing и нативный touch-стек, — «тап физически дошёл до узла» этими
ассертами НЕ доказывается. Доказывается, что действие узла (дефолтная
навигация ссылки, срабатывание собственного обработчика) НЕ было перехвачено
guard'ом: `closest()`-проверка (`ao3_bridge.js:1155`) возвращает управление ДО
любой из веток `scrollBy`/`toggleFullscreen`/`preventDefault` (`:1157-1165`).

Остаточный риск (рекомендация критика a49d0059b695ed179, №2): диагностическая
сила негативных Then в верхней/нижней трети (в отличие от средней) зависит от
того, что `ao3_bridge.js` продолжает вызывать `e.preventDefault()` в
скролл-ветках (`:1165`) — именно отмена дефолтного действия там ловится
`assert_active_tab_url`/аналогичными ассертами навигации; перестань
приложение звать `preventDefault` в этих ветках, регрессия guard'а в
верхней/нижней трети станет невидимой для навигационного ассерта.

TC-121 замыкает 2×2-матрицу whitelist×обработчик, которую вместе объявляют
TC-119 (whitelist=true, обработчик=true) и TC-120 (whitelist=false,
обработчик=true): TC-121 — whitelist=true, обработчик=false (реальная
download-ссылка `<a href>` work-страницы, `_download_list_html`, TC-032/033 —
никакого нового фикстурного узла AT-BUG-030 заводить не нужно). Позиция тапа
здесь НЕ завязана на среднюю треть — guard's `closest()`-проверка отсекает
whitelisted-тег ДО вычисления третьей (`ao3_bridge.js:1155-1156`),
независимо от координаты клика — в отличие от TC-119/120/122, geometry-band
ассерт для этого узла неуместен (см. `dispatch_tap_zone_download_link_tap`
докстринг). Позитивная сверка Then — дефолтная навигация ссылки происходит
(WebView переходит на скачиваемый `.html`, записанный ВТОРЫМ flow в том же
`work_with_download.mitm`) — доказывает, что дефолтное действие ссылки НЕ
отменено guard'ом (см. уточнение формулировки выше).

Порядок навигации в Given — НЕ произвольный. `BrowserScreen.webview_rect`/
`close_leftmost_tab` docstring (AT-BUG-018/019/022 разведка) документирует:
при >1 живых `android.webkit.WebView` единственный context `WEBVIEW_<pkg>`
ПРИЛИПАЕТ к вкладке-0 (первой когда-либо созданной WebView), НЕЗАВИСИМО от
того, какая вкладка визуально активна в UI. Наши проверки (`dispatch_synthetic_
tap`/`assert_tap_marker_tapped`) — WEBVIEW-контекстные операции, поэтому
work-страница с фикстурными узлами ОБЯЗАНА оказаться именно вкладкой-0: сначала
`rating_steps.open_work_page` (навигация АКТИВНОЙ — единственной пока —
вкладки-0 IN PLACE на work.url), и только ПОТОМ открывается вторая вкладка
(через Library — TabStrip-кнопка "New tab" недоступна, пока вкладок < 2,
классическое яйцо-курица) — её конкретное содержимое не важно, нужен только
факт tabs.size>1 для рендера TabStrip (`MainActivity.kt ~406`). Проверено
живым прогоном этой сессии: `contexts.in_webview` после этого ВСЁ ЕЩЁ читает
work-страницу (вкладка-0), даже когда вкладка-1 визуально активна, и
`Android.toggleFullscreen()`, вызванный из JS вкладки-0 (физически в фоне),
корректно переключает ОБЩЕЕ (не per-tab) состояние `isFullscreen`
(`MainActivity.kt`), наблюдаемое пиксельным прокси TabStrip независимо от
того, какая вкладка отображается.

Калибровка `ratio` в `assert_top_chrome_darkened`/`assert_top_chrome_not_
darkened` — 0.7, не дефолтные 0.5 (TC-058): дефолт калибровался на живой/
tab_markers-странице, дающей глубокое затемнение (baseline≈234 ->
fullscreen≈86, ratio 0.5 с запасом). Наша фикстура — светлый статичный HTML
(белый фон, чёрный текст) под верхней кромкой, поэтому измеренный контраст
скромнее (живой прогон этой сессии: baseline≈232 -> fullscreen≈137, ratio
≈0.59) — 0.7 даёт запас в обе стороны (darkened: 137 < 232*0.7=162.4;
not-darkened: 232 >= 162.4) без риска ложного срабатывания на шуме скриншота.
"""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, library_steps, rating_steps, settings_steps

# Калибровка живым прогоном этой сессии (см. докстринг модуля) — светлая
# статичная фикстура даёт более скромный luma-контраст, чем tab_markers.mitm
# (TC-058, дефолт 0.5).
_TOP_CHROME_RATIO = 0.7


def _given_work_page_as_tab_zero_with_tabstrip(driver, work) -> float:
    """Общий Given TC-119/120/122: tap_to_scroll включён, work-страница LOVED —
    вкладка-0 (WEBVIEW-context-цель), вторая вкладка открыта ТОЛЬКО чтобы
    TabStrip отрендерился (см. докстринг модуля за обоснованием порядка).
    Возвращает измеренный baseline верхней полосы (TabStrip светлый, fullscreen
    ещё не входили)."""
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_tap_to_scroll(driver)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_tab(driver, "Library")
    library_steps.open_work_in_browser(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver)
    return browser_steps.measure_top_chrome_luma(driver)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-119")
@allure.title("Guard тап-зон блокирует зональное действие при тапе по whitelisted-узлу (button) в теле work-страницы (replay)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_guard_blocks_whitelisted_button(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница LOVED — вкладка-0, TabStrip
    # виден (>=2 вкладки); в теле присутствует фикстурный
    # <button data-tap-marker="button"> (AT-BUG-030, узел 1) в средней трети
    # viewport
    work = loved_work_seeded
    baseline_luma = _given_work_page_as_tab_zero_with_tabstrip(driver, work)

    # When пользователь тапает по этому <button> (синтетический клик, координата
    # — центр РЕАЛЬНОГО bounding rect узла)
    browser_steps.dispatch_tap_zone_button_tap(driver)

    # Then зональное действие средней трети (toggleFullscreen) НЕ вызывается —
    # верхняя полоса (TabStrip) не темнеет относительно baseline
    browser_steps.assert_top_chrome_not_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)
    # And собственный обработчик кнопки СРАБАТЫВАЕТ (data-tapped проставлен) —
    # его действие НЕ перехвачено guard'ом, просто не породило зонального
    # эффекта (см. уточнение формулировки в докстринге модуля)
    browser_steps.assert_tap_zone_button_tapped(driver)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-120")
@allure.title("Тап по НЕ-whitelisted узлу с собственным обработчиком в теле work-страницы запускает ОБА эффекта (guard-пробой, replay)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_guard_pierced_by_non_whitelisted_div(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница LOVED — вкладка-0, TabStrip
    # виден; в теле присутствует фикстурный
    # <div data-tap-marker="div" onclick=...> БЕЗ whitelisted-тега/role
    # (AT-BUG-030, узел 2), в band 44-56% viewport (рецепт CH-005)
    work = loved_work_seeded
    baseline_luma = _given_work_page_as_tab_zero_with_tabstrip(driver, work)

    # When пользователь тапает по этому узлу
    browser_steps.dispatch_tap_zone_div_tap(driver)

    # Then зональное действие средней трети (toggleFullscreen) ВЫЗЫВАЕТСЯ —
    # TabStrip темнеет относительно baseline
    browser_steps.assert_top_chrome_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)
    # And ОДНОВРЕМЕННО собственный обработчик узла СРАБАТЫВАЕТ (data-tapped
    # установлен) — guard НЕ отсёк тап, хотя у узла есть собственный обработчик,
    # потому что тег/role узла не входит в whitelist (CH-005 находка 2)
    browser_steps.assert_tap_zone_div_tapped(driver)


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-121")
@allure.title("Тап по whitelisted-ссылке (<a> download HTML, БЕЗ собственного обработчика) в теле work-страницы не запускает зональное действие — дефолтная навигация происходит (replay)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_guard_whitelisted_link_without_own_handler(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница LOVED — вкладка-0, TabStrip
    # виден (>=2 вкладки); в теле присутствует <a href="…/<id>/<slug>.html?…">
    # HTML</a> внутри li.download > ul.download-list — whitelisted тег `a`,
    # БЕЗ собственного JS-обработчика (обычный href, штатное поведение браузера)
    work = loved_work_seeded
    baseline_luma = _given_work_page_as_tab_zero_with_tabstrip(driver, work)

    # When пользователь тапает по этой ссылке (координата — центр её РЕАЛЬНОГО
    # bounding rect в естественном месте документа; позиция НЕ завязана на
    # среднюю треть — guard's closest() отсекает whitelisted-тег ДО вычисления
    # третьей, см. TC-121 «Заметки для автоматизации»)
    browser_steps.dispatch_tap_zone_download_link_tap(driver)

    # Then зональное действие (ни scrollBy, ни toggleFullscreen) НЕ вызывается —
    # верхняя полоса (TabStrip) не темнеет относительно baseline
    browser_steps.assert_top_chrome_not_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)
    # And дефолтное действие ссылки ПРОИСХОДИТ — WebView навигирует на скачиваемый
    # .html документ (render_downloaded_work_html, записан ВТОРЫМ flow в том же
    # .mitm) — используется как ПОЗИТИВНОЕ доказательство, что дефолтное действие
    # ссылки НЕ отменено guard'ом (см. уточнение формулировки в докстринге модуля)
    browser_steps.assert_active_tab_url(driver, rb.download_url(work, "html"))


@pytest.mark.p0
@pytest.mark.replay
@allure.id("TC-122")
@allure.title("Тап по потомку (span) whitelisted-узла в теле work-страницы блокирует зональное действие через closest — семантика предка, не изолированной проверки target (replay)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_guard_closest_semantics_on_descendant(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница LOVED — вкладка-0, TabStrip
    # виден; тот же фикстурный <button> (узел 1), что TC-119, несёт вложенный
    # <span data-tap-marker-child="span"> — целевой узел клика (e.target), НЕ
    # сам button
    work = loved_work_seeded
    baseline_luma = _given_work_page_as_tab_zero_with_tabstrip(driver, work)

    # When пользователь тапает по span'у (координата — центр РЕАЛЬНОГО bounding
    # rect span'а, физически НЕ совпадающего с bounding rect всего button)
    browser_steps.dispatch_tap_zone_button_child_tap(driver)

    # Then зональное действие НЕ вызывается — e.target.closest(...) находит
    # <button> как ПРЕДКА <span>, whitelist срабатывает независимо от того, что
    # непосредственная цель клика (e.target) — сам span, а не whitelisted-узел
    # напрямую
    browser_steps.assert_top_chrome_not_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)
    # And собственный обработчик КНОПКИ (не span'а — обработчик висит на button)
    # СРАБАТЫВАЕТ — событие клика по потомку доходит до обработчика предка
    # обычным пузырением DOM, независимо от guard'а
    browser_steps.assert_tap_zone_button_tapped(driver)
