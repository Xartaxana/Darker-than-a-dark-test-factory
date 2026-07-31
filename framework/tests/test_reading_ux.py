"""Reading-UX тап-зоны work-страницы (`ao3_bridge.js:1149-1166`,
docs/01-test-strategy.md §9 «reading-UX жесты и их тумблеры» —
browse-tap-to-scroll/browse-tap-fullscreen). Три равные трети viewport:
верхняя скроллит вверх, нижняя — вниз, средняя переключает fullscreen; guard
whitelist-узлов (`closest('a, button, input, select, textarea, label, summary,
[role="button"]')`) выполняется РАНЬШЕ вычисления трети и гейтит ВЕСЬ
обработчик флагом `window.__ao3TapToScroll` — TC-126/TC-127/TC-128 несут
`tap_to_scroll = ON` как общее предусловие. TC-123 держит СИММЕТРИЧНЫЙ
негативный инвариант: `tap_to_scroll = OFF` (дефолт) — тот же единственный
гейт (`ao3_bridge.js:1153`) применяется ДО вычисления третьей тапа, поэтому
ни одна из трёх третей не производит эффекта независимо от координаты.

Узел 3 AT-BUG-030 (высота документа >= 3×innerHeight) уже присутствует во всех
четырёх потребителях `render_work_page_html`, включая `work_with_download.mitm`
(общий с TC-032/033/119/120/122) — TC-126/TC-127 используют его для
диагностической силы Then (страница не должна упираться в границу скролла ДО
тапа), TC-128 не зависит от высоты/скролла вовсе, но переиспользует ту же
короткую-по-сути (структурно) фикстуру без изменений.

Тап дispatch'ится синтетическим `MouseEvent` через `document.elementFromPoint`
(`browser_steps.dispatch_synthetic_viewport_tap`) — целевой узел определяется
РЕАЛЬНОЙ геометрией страницы в момент тапа, не хардкодом CSS-селектора;
центральная колонка X (`innerWidth/2`) промахивается мимо узлов 1/2 AT-BUG-030
(`left:24px; width:200px`) независимо от Y/scroll-позиции, поэтому целью тапа
всегда оказывается обычный `<p>`-филлер (неинтерактивный, вне whitelist).

Порядок навигации в Given TC-128 (work-страница — вкладка-0, вторая вкладка
открыта ПОСЛЕ через Library) — тот же паттерн, что `test_tap_zone_guard.py`
(AT-BUG-018/019/022: единственный Appium `WEBVIEW_<pkg>` context прилипает к
вкладке-0 независимо от визуально активной вкладки).

TC-124 проверяет ДВА механизма синхронизации самого флага `tap_to_scroll`
(отдельно от гейта `ao3_bridge.js:1153`, который проверяют TC-123/126/127):
(1) реактивный live-push на уже открытую вкладку без reload
(`LaunchedEffect(tapToScroll)`, `BrowserScreen.kt:187-192` —
`evaluateJavascript` на ВСЕ живые WebView при переключении тумблера); (2)
реинъекция при (пере)загрузке (`onPageFinished`, `BrowserScreen.kt:603`),
наблюдаемая через reload от смены темы — тумблер обязан пережить его, а не
сброситься к дефолту `false`. Оба пути дают идентичный наблюдаемый эффект
тапа (инвариант кейса), поэтому Then в обоих When-блоках — один и тот же
`assert_tap_to_scroll_delta`, что и у TC-127 (тот же тап по нижней трети)."""
from __future__ import annotations

import re

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, library_steps, rating_steps, settings_steps

# Калибровка TC-119/120/122 (AT-BUG-030, живой прогон) — светлая статичная
# фикстура даёт скромный luma-контраст, не дефолтные 0.5 (TC-058).
_TOP_CHROME_RATIO = 0.7


def _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work):
    """Общий Given TC-126/127/128: tap_to_scroll включён, work-страница —
    вкладка-0 (WEBVIEW-context-цель), вторая вкладка открыта, чтобы TabStrip
    отрендерился (`tabs.size>1`), не fullscreen."""
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_tap_to_scroll(driver)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_tab(driver, "Library")
    library_steps.open_work_in_browser(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-126")
@allure.title("Тап по верхней трети work-страницы скроллит страницу вверх (tap-to-scroll ON)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_top_third_scrolls_up(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница (высота >= 3×innerHeight, узел 3
    # AT-BUG-030) — вкладка-0, TabStrip виден (>=2 вкладки), не fullscreen;
    # страница предварительно проскроллена вниз так, что scrollY > 0.95×innerHeight
    # (execute_script — дешевле и не создаёт зависимости от TC-127)
    work = loved_work_seeded
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)
    scroll_before, inner_height = browser_steps.prescroll_past_tap_to_scroll_threshold(driver)

    # When пользователь тапает по верхней трети экрана (clientY < innerHeight/3,
    # цель — неинтерактивный узел)
    browser_steps.dispatch_tap_to_scroll_up_tap(driver)

    # Then window.scrollY уменьшается примерно на 0.95×innerHeight (измерение
    # CH-005: dy ≈ -1710 при innerHeight=1800)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before, inner_height, direction=-1)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-127")
@allure.title("Тап по нижней трети work-страницы скроллит страницу вниз (tap-to-scroll ON)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_bottom_third_scrolls_down(loved_work_seeded, replay, driver):
    # Given tap_to_scroll включён, work-страница (высота >= 3×innerHeight, узел 3
    # AT-BUG-030) — вкладка-0, TabStrip виден (>=2 вкладки), не fullscreen;
    # страница в начальной позиции (scrollY = 0, штатное состояние после
    # свежей загрузки — не требует предскролла, в отличие от TC-126)
    work = loved_work_seeded
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)
    scroll_before = browser_steps.get_webview_scroll_y(driver)
    assert scroll_before == 0, (
        f"Given TC-127 требует scrollY=0 (свежая загрузка), фактически {scroll_before}"
    )
    inner_height = browser_steps.get_webview_inner_height(driver)

    # When пользователь тапает по нижней трети экрана (clientY >= 2×innerHeight/3,
    # цель — неинтерактивный узел)
    browser_steps.dispatch_tap_to_scroll_down_tap(driver)

    # Then window.scrollY увеличивается примерно на 0.95×innerHeight (измерение
    # CH-005: dy ≈ +1710 при innerHeight=1800), не превышая максимально
    # возможный скролл документа (узел 3 AT-BUG-030 даёт достаточный запас)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before, inner_height, direction=1)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-128")
@allure.title("Тап по средней трети work-страницы переключает fullscreen (вход и выход)")
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_middle_third_toggles_fullscreen(loved_work_seeded, replay, driver):
    # Given открыты 2 вкладки Browse, активная — replay work-страница; TabStrip
    # виден вверху экрана; tap_to_scroll включён (routine, вне скоупа этого
    # кейса); режим fullscreen выключен
    work = loved_work_seeded
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)
    baseline_luma = browser_steps.measure_top_chrome_luma(driver)

    # When пользователь тапает по средней трети экрана (координата — центр
    # вьюпорта, ПЕРЕСЧИТЫВАЕМЫЙ перед каждым тапом — innerHeight меняется между
    # входом/выходом из fullscreen, см. заметки кейса)
    browser_steps.dispatch_tap_zone_fullscreen_toggle_tap(driver)

    # Then режим fullscreen включается: TabStrip скрывается (тот же пиксельный
    # прокси, что TC-058, top_chrome_avg_luma)
    browser_steps.assert_top_chrome_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)

    # When пользователь тапает по средней трети экрана ещё раз (координата
    # пересчитана заново как защитная мера — на этом стенде innerHeight
    # эмпирически не меняется между тапами, см. заметки кейса TC-128)
    browser_steps.dispatch_tap_zone_fullscreen_toggle_tap(driver)

    # Then режим fullscreen выключается: TabStrip снова отображается — toggle
    # симметричен, второй тап возвращает исходное наблюдаемое состояние
    browser_steps.assert_top_chrome_restored(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)


def _given_tap_to_scroll_disabled_work_page_as_tab_zero_with_tabstrip(driver, work):
    """Given TC-123: tap_to_scroll ОСТАЁТСЯ выключенным (дефолт после `pm clear`,
    ничего не включаем), work-страница — вкладка-0 (WEBVIEW-context-цель),
    вторая вкладка открыта, чтобы TabStrip отрендерился (`tabs.size>1`), не
    fullscreen. Given-предпосылка тумблера сверена явным assert'ом
    (`settings_steps.assert_tap_to_scroll_enabled(expected=False)`), а не
    молчаливо предположена по дефолту — тот же класс, что TC-127 сверяет
    `scrollY=0` собственным assert'ом вместо допущения «свежая загрузка и так
    даёт 0»."""
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_tap_to_scroll_enabled(driver, expected=False)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_tab(driver, "Library")
    library_steps.open_work_in_browser(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-123")
@allure.title(
    "Tap to scroll: тумблер OFF — тап ни по одной трети work-страницы не "
    "производит эффекта (негативный инвариант)"
)
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_zone_disabled_no_effect_in_any_third(loved_work_seeded, replay, driver):
    # Given tap_to_scroll = OFF (дефолт, ничего не включаем, сверено assert'ом);
    # work-страница (высота >= 3×innerHeight, узел 3 AT-BUG-030) — вкладка-0,
    # TabStrip виден (>=2 вкладки), не fullscreen; страница предварительно
    # проскроллена к scrollY=S≈innerHeight, СТРОГО не у края (иначе негативный
    # Then неотличим от клампа к границе даже при сломанном гейте)
    work = loved_work_seeded
    _given_tap_to_scroll_disabled_work_page_as_tab_zero_with_tabstrip(driver, work)

    # Given-предпосылка гейта (`ao3_bridge.js:1154`) сверена явно, а не
    # предположена по факту навигации через rating_steps.open_work_page: без
    # этого якоря негативный Then неотличим от «тап пришёлся на нештатную
    # страницу, где обработчик и так бы не сработал» (класс 1 ложно-зелёных
    # негативов — критик-вход B1/N2)
    pathname, _search = browser_steps.get_webview_location(driver)
    assert re.match(r"^/works/\d", pathname), (
        f"pathname={pathname!r} не соответствует ^/works/\\d — открыта НЕ work-страница "
        f"(тот же паттерн проверяет гейт тап-зон, ao3_bridge.js:1154); Given TC-123 не выполнен"
    )

    scroll_at_s = browser_steps.prescroll_to_tap_zone_invariant_position(driver)
    # baseline_luma снят в Given (не после первого тапа) — узкая дыра
    # маскировки состояния fullscreen: замер ПОСЛЕ первого тапа не отличил бы
    # «fullscreen уже был не тем, что ожидалось, до среднего тапа» от «средний
    # тап не переключил fullscreen» (образец TC-128, критик-вход N3)
    baseline_luma = browser_steps.measure_top_chrome_luma(driver)

    # When пользователь тапает по верхней трети экрана
    tap_top = browser_steps.dispatch_tap_to_scroll_up_tap(driver)
    # Then тап физически попал на НЕинтерактивный узел (closest(whitelist) —
    # тот же guard, что ao3_bridge.js:1155) — иначе негативный Then ниже был бы
    # вакуумно истинен (тап промахнулся мимо обработчика независимо от
    # значения tap_to_scroll, класс 1 ложно-зелёных негативов, критик-вход B1)
    assert tap_top["interactive"] is False, (
        f"тап по верхней трети попал на интерактивный узел (tagName="
        f"{tap_top.get('tagName')!r}) — негативный Then ниже неинтерпретируем: "
        f"эффект мог отсутствовать из-за guard'а тап-зон (ao3_bridge.js:1155), "
        f"а не из-за проверяемого гейта tap_to_scroll (ao3_bridge.js:1153)"
    )
    # Then window.scrollY остаётся равным S (не S - 0.95×innerHeight)
    browser_steps.assert_scroll_unchanged(driver, scroll_at_s)

    # When пользователь тапает по средней трети экрана
    tap_middle = browser_steps.dispatch_tap_zone_fullscreen_toggle_tap(driver)
    # Then тап физически попал на неинтерактивный узел (см. выше)
    assert tap_middle["interactive"] is False, (
        f"тап по средней трети попал на интерактивный узел (tagName="
        f"{tap_middle.get('tagName')!r}) — негативный Then ниже неинтерпретируем"
    )
    # Then fullscreen не включается (TabStrip остаётся видимым)
    browser_steps.assert_top_chrome_not_darkened(driver, baseline_luma, ratio=_TOP_CHROME_RATIO)

    # When пользователь тапает по нижней трети экрана
    tap_bottom = browser_steps.dispatch_tap_to_scroll_down_tap(driver)
    # Then тап физически попал на неинтерактивный узел (см. выше)
    assert tap_bottom["interactive"] is False, (
        f"тап по нижней трети попал на интерактивный узел (tagName="
        f"{tap_bottom.get('tagName')!r}) — негативный Then ниже неинтерпретируем"
    )
    # Then window.scrollY остаётся равным S (не S + 0.95×innerHeight)
    browser_steps.assert_scroll_unchanged(driver, scroll_at_s)


def _given_tap_to_scroll_off_live_work_page_as_tab_zero_with_tabstrip(driver, work):
    """Given TC-124: tap_to_scroll ОСТАЁТСЯ выключенным (дефолт, сверено
    assert'ом) — критично, что work-страница открывается ДО того, как тумблер
    будет включён (первый When теста): иначе реактивный live-push
    (`LaunchedEffect(tapToScroll)`, `BrowserScreen.kt:187-192`) неотличим от
    обычной реинъекции при (пере)загрузке страницы (`onPageFinished`,
    `BrowserScreen.kt:603`) — тот же класс задачи, что различает второй When
    кейса (reload от темы). Вкладка-0 (WEBVIEW-context-цель), вторая вкладка
    открыта, чтобы TabStrip отрендерился (`tabs.size>1`), не fullscreen —
    тот же паттерн, что TC-123/126/127/128.

    Тема ЯВНО закреплена как LIGHT ПЕРЕД началом сценария (rework attempt 2,
    критик-вход B1'): дефолт `themeMode = SYSTEM` (`SettingsScreen.kt:70,96`),
    `darkTheme = when(themeMode){...; SYSTEM -> systemDark}` (`MainActivity.kt
    :137-140`) — если системная тема эмулятора уже ночная (её мутируют
    TC-049/TC-059, восстановление только в finally, может остаться грязной
    после прерванного прогона), переход SYSTEM->DARK во втором When теста НЕ
    изменил бы `darkTheme` (уже был `true`), и `wv.reload()`
    (`BrowserScreen.kt` `LaunchedEffect(darkTheme)`, срабатывает только на
    ИЗМЕНЕНИИ значения) не произошёл бы — второй When/Then кейса выродился бы
    в повтор первого без проверяемого reload. Пиннинг к LIGHT — тот же приём,
    что `test_side_panel.py:30-32`/`test_settings.py` TC-047/TC-048 — гарантирует
    LIGHT->DARK детерминированно меняет `darkTheme: false -> true`."""
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "LIGHT")
    settings_steps.assert_tap_to_scroll_enabled(driver, expected=False)
    app_steps.open_tab(driver, "Browse")
    rating_steps.open_work_page(driver, work.ao3_id)
    app_steps.open_tab(driver, "Library")
    library_steps.open_work_in_browser(driver, work.title)
    browser_steps.assert_tab_strip_visible(driver)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-124")
@allure.title(
    "Tap to scroll: включение тумблера применяется мгновенно к уже открытой "
    "work-странице (live-push) и переживает reload от смены темы"
)
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_to_scroll_live_push_and_reload_persistence(loved_work_seeded, replay, driver):
    # Given tap_to_scroll = OFF (дефолт, сверено assert'ом); work-страница
    # (высота >= 3×innerHeight, узел 3 AT-BUG-030) уже открыта — вкладка-0,
    # TabStrip виден (>=2 вкладки), не fullscreen; страница НЕ будет
    # перезагружаться/заново навигироваться до явного reload от темы на втором
    # шаге сценария
    work = loved_work_seeded
    _given_tap_to_scroll_off_live_work_page_as_tab_zero_with_tabstrip(driver, work)

    # Given документ work-страницы помечен уникальным маркером идентичности
    # (rework attempt 2, критик-вход B2') — маркер живёт на `window` текущего
    # документа: `reload()`/навигация пересоздают `window` с нуля (маркер
    # исчезает), `evaluateJavascript` на уже загруженный документ (live-push)
    # его не трогает (маркер переживает). Позитивный якорь, различающий два
    # структурно разных пути синхронизации `tap_to_scroll`, о которых говорит
    # инвариант кейса.
    doc_marker = browser_steps.mark_document_identity(driver)

    # When пользователь переходит в Settings и включает тумблер «Tap to scroll
    # (work pages)» — состояние подтверждается явным assert'ом сразу после
    # идемпотентного условного сеттера (класс 2 ложно-зелёных негативов:
    # `set_tap_to_scroll` тапает, только если текущее состояние не совпадает с
    # желаемым — без сверки несработавший тап оставил бы весь дальнейший
    # сценарий с тем же наблюдаемым результатом, что и до включения)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_tap_to_scroll(driver)
    settings_steps.assert_tap_to_scroll_enabled(driver, expected=True)

    # And возвращается на ТУ ЖЕ (не перезагруженную) вкладку
    app_steps.open_tab(driver, "Browse")

    # Then (позитивный якорь B2'): документ НЕ пересоздавался — доказывает, что
    # эффект тапа ниже применится реактивным push (`LaunchedEffect(tapToScroll)`),
    # а не переинъекцией при (пере)загрузке страницы, которой в этом сценарии
    # быть не должно
    browser_steps.assert_document_identity_preserved(driver, doc_marker)

    # And страница предварительно проскроллена к scrollY=S≈innerHeight, строго
    # не у края (тот же приём предскролла, что TC-123 — гарантирует запас на
    # изменение scrollY вниз без клампа к границе документа)
    scroll_before = browser_steps.prescroll_to_tap_zone_invariant_position(driver)
    inner_height = browser_steps.get_webview_inner_height(driver)

    # When пользователь тапает по нижней трети экрана
    browser_steps.dispatch_tap_to_scroll_down_tap(driver)

    # Then window.scrollY увеличивается примерно на 0.95×innerHeight — эффект
    # применился БЕЗ reload и БЕЗ повторной навигации, то есть именно
    # реактивным push (`LaunchedEffect(tapToScroll)`), а не переинъекцией при
    # загрузке страницы (которой в этом сценарии не было)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before, inner_height, direction=1)

    # When пользователь возвращается в Settings и переключает тему на Dark —
    # Given сценария закрепил исходную тему как LIGHT (rework attempt 2,
    # критик-вход B1'), поэтому LIGHT->DARK детерминированно меняет
    # `darkTheme: false -> true` и гарантированно вызывает `wv.reload()` для
    # существующих WebView (BrowserScreen.kt `LaunchedEffect(darkTheme)`), не
    # закрывая и не открывая заново саму work-вкладку (`select_theme` —
    # переиспользован из TC-047/TC-050)
    app_steps.open_tab(driver, "Settings")
    settings_steps.select_theme(driver, "DARK")

    # And возвращается на ту же вкладку
    app_steps.open_tab(driver, "Browse")

    # Then (точка синхронизации B2'): документ пересоздан — маркер идентичности
    # исчез, что одновременно доказывает, что reload реально произошёл, И
    # служит гарантией, что последующий предскролл видит уже финальный, новый
    # документ (после reload документ переразмечен заново со scrollY=0)
    browser_steps.wait_document_identity_changed(driver, doc_marker)
    scroll_before_2 = browser_steps.prescroll_to_tap_zone_invariant_position(driver)
    inner_height_2 = browser_steps.get_webview_inner_height(driver)

    # When пользователь тапает по нижней трети экрана ещё раз
    browser_steps.dispatch_tap_to_scroll_down_tap(driver)

    # Then страница снова скроллится вниз — тумблер пережил reload (реинъекция
    # `window.__ao3TapToScroll=true` в `onPageFinished`, `BrowserScreen.kt:603`,
    # а не сброс к дефолту `false`)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before_2, inner_height_2, direction=1)


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-125")
@allure.title(
    "Tap to scroll ON переживает kill+relaunch приложения (тумблер и эффект тапа)"
)
@pytest.mark.parametrize("replay", [rb.WORK_WITH_DOWNLOAD_FILENAME], indirect=True)
def test_tap_to_scroll_survives_kill_and_relaunch(loved_work_seeded, replay, driver):
    """`SettingsScreen.kt:177` читает `tap_to_scroll` из SharedPreferences ПРИ
    СТАРТЕ (не из живого процесса) — единственный способ реально проверить эту
    ветку кода, а не реактивный push (`BrowserScreen.kt:187-192`, покрытый
    TC-124), это РЕАЛЬНАЯ смерть процесса (`am force-stop`), тот же приём, что
    TC-025/TC-110 (`app_steps.restart_app_via_adb`, докстринг там же поясняет
    отличие от `driver.terminate_app`/`activate_app`).

    Второй (после relaunch) тап по нижней трети НЕ предваряется повторным
    `prescroll_to_tap_zone_invariant_position` (rework attempt 2, критик-вход
    Б2': арифметика заметок TC-125.md про «persisted scrollY≈0.95×innerHeight»
    предполагала, что baseline-тап делается СРАЗУ с scrollY=0 — но
    `prescroll_to_tap_zone_invariant_position` ПЕРЕД baseline-тапом уже даёт
    S≈1×innerHeight, так что позиция ДО kill была бы ≈1.95×innerHeight, если
    бы вообще имела отношение ко второму тапу). Диагностический запас второго
    тапа не зависит от этой арифметики вовсе: второй тап приходится на
    ДРУГУЮ, никогда не скролленную этим тестом вкладку (см. ниже) — она
    восстанавливается со свежим `scrollY=0`, и тот же запас, что даёт узел 3
    AT-BUG-030 (`maxScroll >= 2×innerHeight`) любому старту с нуля
    (TC-123/126/127), покрывает и её — дополнительный форс-скролл не нужен и
    не добавлен, чтобы не менять диагностическую силу Then молча.

    **Живой прогон (attempt 1) вскрыл инфраструктурный нюанс sticky-контекста
    после relaunch**, не описанный явно в докстринге модуля (уточнено rework
    attempt 2, критик-вход Б1': предыдущая редакция ошибочно утверждала, что
    persisted вкладка-0 остаётся HOME_URL/«фантомна» — опровергается кодом,
    см. ниже). Общий Given (`_given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip`)
    открывает work-страницу через `rating_steps.open_work_page` — СЫРУЮ
    навигацию chromedriver'ом ПРЯМО на sticky WEBVIEW-контекст (первый
    когда-либо созданный WebView, тот же quirk, что описан у
    `dispatch_synthetic_viewport_tap` и `browser_screen.py::tab_chip_locator`).
    Несмотря на сырую навигацию, `onPageFinished` (`BrowserScreen.kt:594`, ДО
    инъекции моста строкой 603) БЕЗУСЛОВНО вызывает
    `viewModel.onPageLoaded(tabId, url)` (`BrowserViewModel.kt:463-488`),
    который пишет реальный `url` в `TabInfo` и вызывает `saveTabsToPrefs()` —
    тот же механизм, что поясняет `browser_screen.py:39-50` для домашней
    страницы («`tabs[0].url` уже разошёлся с плейсхолдером `HOME_URL`»), и что
    подтверждено собственным witness'ом этого прогона: `window.__ao3TapToScroll`
    инжектируется той же цепочкой колбэка (`BrowserScreen.kt:603`), без этого
    TC-126/TC-127 не были бы зелёными. Поэтому persisted вкладка-0 несёт
    РЕАЛЬНЫЙ work-URL, не HOME_URL, и baseline-тап ДО kill (через
    sticky-контекст, привязанный к ПЕРВОЙ по порядку создания вкладке)
    скроллит именно её.

    После relaunch восстанавливаются РЕАЛЬНЫЕ persisted вкладки: `[0]` — та
    же work-страница (реальный URL, персистентно проскролленная baseline-
    тапом), `[1]` — вторая work-страница, открытая через Library (persisted
    `activeTabIndex` указывает на НЕЁ — это реально видимая после релонча
    вкладка). Sticky WEBVIEW-контекст снова цепляется к ПЕРВОЙ по порядку
    создания вкладке (`[0]`) — но это восстановленная НЕАКТИВНАЯ вкладка
    (persisted `activeTabIndex` её не выбирает): её WebView не проходит
    layout-pass, не будучи видимой/attached, поэтому `window.innerHeight ===
    window.innerWidth === 0` бессрочно (не транзиентная гонка — таймаут
    `wait_webview_viewport_ready` подтвердил это эмпирически) — причина не
    фантомность вкладки, а её неактивность после восстановления. Тот же
    класс задачи, что уже решён в TC-025 (см. её докстринг про «прилипание
    chromedriver к вкладке-0»): закрыть НЕАКТИВНУЮ вкладку на позиции 0
    нативным свайпом (`browser_steps.swipe_close_tab`, НЕ требует
    WebView-контекста) ДО того, как понадобится WebView-контент —
    уничтоженный `WebView.destroy()` убирает свой devtools-контекст из
    `driver.contexts`, и sticky-подбор следующим вызовом естественно находит
    единственный оставшийся (реальный, attached, АКТИВНЫЙ, никогда не
    скролленный этим тестом) контекст — вкладку `[1]`."""
    work = loved_work_seeded
    # Given tap_to_scroll = ON (включён через Settings ДО открытия work-страницы,
    # тот же общий Given, что TC-126/127/128); work-страница (высота
    # >= 3×innerHeight, узел 3 AT-BUG-030) — вкладка-0, TabStrip виден
    # (>=2 вкладки), не fullscreen
    _given_tap_to_scroll_work_page_as_tab_zero_with_tabstrip(driver, work)

    # And baseline: тап по нижней трети подтверждённо скроллит страницу ДО kill
    # (тот же предскролл к инвариантной позиции, что TC-123/124/126)
    scroll_before = browser_steps.prescroll_to_tap_zone_invariant_position(driver)
    inner_height = browser_steps.get_webview_inner_height(driver)
    browser_steps.dispatch_tap_to_scroll_down_tap(driver)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before, inner_height, direction=1)

    # When приложение убито (`adb shell am force-stop`) и перезапущено (без
    # очистки данных) — реплей-прокси (mitmproxy) переживает сам relaunch
    # приложения, тот же инфраструктурный факт, что уже проверен TC-025; pid-
    # проверка (AT-BUG-032) доказывает реальную смерть процесса, а не no-op
    # force-stop с доставкой intent'а живому инстансу
    app_steps.restart_app_via_adb_asserting_new_process(driver)
    app_steps.wait_ui_ready(driver)

    # Then тумблер «Tap to scroll (work pages)» в Settings по-прежнему
    # отображает ON (значение читается из SharedPreferences при старте,
    # SettingsScreen.kt:177 — НЕ из живого процесса, который был убит)
    app_steps.open_tab(driver, "Settings")
    settings_steps.assert_tap_to_scroll_enabled(driver, expected=True)

    # And на открытой после перезапуска replay work-странице тап по нижней
    # трети снова скроллит страницу — JS-состояние window.__ao3TapToScroll
    # корректно переинициализировано при свежей загрузке страницы после
    # релонча (значение тумблера пережило смерть процесса, а не сбросилось к
    # дефолту false). Без повторного prescroll (см. докстринг теста) —
    # стартовая позиция читается как есть.
    app_steps.open_tab(driver, "Browse")
    # Закрываем НЕАКТИВНУЮ восстановленную вкладку на позиции 0 (persisted
    # порядок создания: первая work-страница — position 0, вторая (через
    # Library) — position 1, см. докстринг теста про sticky-контекст и про то,
    # что вкладка-0 несёт РЕАЛЬНЫЙ work-URL, не HOME_URL) НАТИВНЫМ свайпом —
    # не требует WebView-контекста сам по себе, зато убирает из
    # `driver.contexts` вкладку, чей WebView не прошёл layout-pass (не будучи
    # активной после релонча, вечный innerHeight=0 — не фантом), оставляя
    # единственной РЕАЛЬНУЮ, активную, никогда не скролленную этим тестом
    # вторую work-страницу
    browser_steps.swipe_close_tab(driver, 0)
    inner_height_2 = browser_steps.wait_webview_viewport_ready(driver)
    scroll_before_2 = browser_steps.get_webview_scroll_y(driver)
    browser_steps.dispatch_tap_to_scroll_down_tap(driver)
    browser_steps.assert_tap_to_scroll_delta(driver, scroll_before_2, inner_height_2, direction=1)
