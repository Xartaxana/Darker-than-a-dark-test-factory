"""Область compatibility (test-cases/compatibility/, docs/01-test-strategy.md §9
area E3): TC-109 (smoke на втором (нижнем практичном) API level, см. AT-BUG-028
за причиной смены API 26 -> API 29), TC-110 (системная dark/light матрица),
TC-111 (portrait/landscape).
"""
from __future__ import annotations

import allure
import pytest

from framework.core import adb
from framework.data import works as W
from framework.steps import (
    app_steps,
    browser_steps,
    library_steps,
    rating_steps,
)

# AT-BUG-028 (2026-07-22): изначальный второй AVD `ao3_test_api26` (API 26,
# ровно minSdk манифеста) нёс embedded WebView Chrome 69.0.3497 (EOL) — ЛЮБОЙ
# chromedriver, поддерживающий эту версию Chrome (2.41-2.44, диапазоны v67-71),
# эмпирически не несёт поля `ready` в /status (проверено запуском бинарников
# локально: 2.41/2.42/2.43/2.44 -> нет `ready`; 2.45, v70-72, -> есть) —
# текущий appium-chromedriver (`commands/process.js::waitForOnline`) жёстко
# требует `status.ready` истинным, так что ЛЮБОЙ chromedriver, совместимый с
# Chrome 69, структурно не проходит readiness-проверку современного Appium
# независимо от того, найден бинарник или нет (путь "в) legacy chromedriver
# руками" — тупиковый, не просто "трудно найти бинарник"). Второй AVD
# переведён на `system-images;android-29;google_apis;x86_64` (тот же класс
# образа — rootable, `PlayStore.enabled=no`, см. AT-BUG-024) — embedded
# WebView этого образа Chrome 74.0.3729.185 (`dumpsys package
# com.google.android.webview`), chromedriver 2.45+ (несёт `ready`) для него
# доступен через штатный autodownload. Это НЕ буквальная нижняя граница
# minSdk (26) — ближайший практичный API >=26, разрешённый критерием
# готовности AT-BUG-028/AT-BUG-024 явно ("допустимо взять ближайший
# практичный образ, если 26 недоступен как ЖИЗНЕСПОСОБНЫЙ канал" — здесь
# образ API 26 физически доступен, но структурно недоступен современному
# Appium ни одним совместимым chromedriver). Смещение риска: R-14 больше не
# покрывает буквальный minSdk=26 рендер, а нижнюю практично-автоматизируемую
# границу (26 остаётся покрыт нативной установкой/запуском — TC preflight
# ниже всё ещё умеет проверить любой заданный уровень, см. SECOND_AVD_API_LEVEL);
# отмечено для прохода test-strategist (docs/01-test-strategy.md §9).
SECOND_AVD_API_LEVEL = "29"
SECOND_AVD_NAME = "ao3_test_api29"


@pytest.fixture()
def api26_device_required():
    """TC-109 форвард-флаг (заметки кейса, приёмка AT-BUG-024, критик-вход):
    `scripts/doctor.py` проверяет только основной AVD (`ao3_test_api34`) — без
    явной проверки здесь забытое переключение эмулятора на второй AVD привело бы
    либо к молчаливому прогону НЕ на нужном API level, либо к таймауту (если
    устройства нет вовсе). Проверяет ФАКТИЧЕСКИЙ API level ПОДКЛЮЧЁННОГО
    устройства (`adb shell getprop ro.build.version.sdk`) — диагностируемый
    fail-fast вместо таймаута, сам fixture не пытается переключать эмулятор
    (это делает оператор/оркестратор через `Start-Emulator -WritableSystem
    -AvdName ao3_test_api29`, см. docs/environment-setup.md). Имя фикстуры
    сохранено (`api26_device_required`) ради минимальной правки call site —
    проверяемый уровень теперь `SECOND_AVD_API_LEVEL` (AT-BUG-028, см. выше)."""
    actual = adb.shell("getprop ro.build.version.sdk").strip()
    assert actual == SECOND_AVD_API_LEVEL, (
        f"TC-109 требует эмулятор API {SECOND_AVD_API_LEVEL} (AVD {SECOND_AVD_NAME}), "
        f"подключено устройство с API {actual!r} — переключите эмулятор: "
        f"`Start-Emulator -WritableSystem -AvdName {SECOND_AVD_NAME}` (см. AT-BUG-028)"
    )


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-109")
@allure.title("Базовый smoke-путь на втором AVD (API 29, ближайший практичный уровень >= minSdk 26) — без регресса относительно API 34")
@pytest.mark.parametrize("placeholder_seeded_work", [W.LOVED], indirect=True)
def test_smoke_path_on_api26_no_regression(api26_device_required, placeholder_seeded_work, driver):
    # AT-BUG-028 (skip снят 2026-07-22): второй AVD переведён API 26 -> API 29
    # (см. блок комментариев над SECOND_AVD_API_LEVEL выше — EOL WebView Chrome 69
    # структурно несовместим с readiness-проверкой текущего Appium ни одним
    # chromedriver'ом, легковесный legacy-бинарник тоже опробован и отвергнут
    # эмпирически, не только по недоступности). WebView образа API 29 — Chrome
    # 74.0.3729.185, autodownload находит совместимый chromedriver штатно, без
    # ручного capability (settings.CHROMEDRIVER_EXECUTABLE остаётся доступной
    # общей механикой для будущих аналогичных случаев, см. capabilities.py,
    # но НЕ требуется для ЭТОГО теста — env var не задаётся).
    work = placeholder_seeded_work
    # Given приложение установлено и запущено на втором AVD (API 29, см. AT-BUG-024/
    # AT-BUG-028, `api26_device_required` preflight выше), работа W засеяна тем же способом,
    # что на основном AVD (переиспользован seed TC-009/TC-006/TC-007)
    # When базовый smoke-путь: запуск -> Browse (работа W) -> простановка рейтинга
    # -> Library (вкладка рейтинга) -> открытие/закрытие вкладки — переиспользованы
    # шаги TC-001/006/007/098 (тот же приём, что TC-098/TC-105), не изобретаем
    # новый маршрут
    app_steps.wait_app_ready(driver)
    rating_steps.open_work_page(driver, work.ao3_id)
    rating_steps.rate_current_work(driver, "SAVE")

    # Then рейтинг сохраняется и виден без reload, работа появляется в
    # соответствующей вкладке Library — тот же наблюдаемый результат, что на API 34
    app_steps.open_tab(driver, "Library")
    library_steps.assert_work_in_tab(driver, "SAVE", work.title)

    # And таб открывается/закрывается без краша — WebView и Compose UI рендерятся
    # корректно на нижней границе minSdk
    app_steps.open_tab(driver, "Browse")
    app_steps.open_deep_link(browser_steps.HOME_URL)
    browser_steps.assert_tab_strip_visible(driver, timeout=10)
    browser_steps.swipe_close_tab(driver, 0)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-110")
@allure.title("Системная dark/light матрица: базовый smoke-путь без регресса в обоих системных режимах")
def test_smoke_path_in_system_dark_and_light_modes(driver):
    work = W.LOVED
    try:
        # Given/When: маршрут проходится ДВАЖДЫ на чистых данных (`pm clear` между
        # прогонами) — шаг 1 под системным `night yes` (day->night), шаг 2 под
        # `night no` (night->day) — оба направления переключения (Инвариант кейса)
        for dark in (True, False):
            # placeholder-сидинг (rating=None, title/author заполнены) — тот же
            # приём, что test_rating.py (синтетический ao3_id иначе даёт скрейп
            # пустых title/author со страницы 404, см. докстринг test_rating.py)
            app_steps.clean_state()
            app_steps.seed_with_comment([(work, None, None, None)])
            app_steps.set_system_dark_mode(dark)
            # restart_app_via_adb (adb force-stop + am start -W) — тот же приём,
            # что TC-025: перезапускает процесс приложения В ТОЙ ЖЕ сессии Appium,
            # подхватывая новые данные/системный режим без пересоздания сессии
            app_steps.restart_app_via_adb(driver)

            app_steps.wait_app_ready(driver)
            rating_steps.open_work_page(driver, work.ao3_id)
            rating_steps.rate_current_work(driver, "SAVE")

            # Then рейтинг сохраняется и виден, работа появляется в нужной вкладке
            # Library — тот же наблюдаемый результат независимо от направления
            # переключения системного режима
            app_steps.open_tab(driver, "Library")
            library_steps.assert_work_in_tab(driver, "SAVE", work.title)

            # And таб открывается/закрывается без краша
            app_steps.open_tab(driver, "Browse")
            app_steps.open_deep_link(browser_steps.HOME_URL)
            browser_steps.assert_tab_strip_visible(driver, timeout=10)
            browser_steps.swipe_close_tab(driver, 0)
    finally:
        # Системная тема ОС — общий ресурс эмулятора, переживающий тест; тот же
        # паттерн уборки, что TC-049/TC-059.
        app_steps.set_system_dark_mode(False)


@pytest.mark.p2
@pytest.mark.live
@allure.id("TC-111")
@allure.title("Portrait/landscape: поворот сохраняет активную вкладку/URL/скролл, не пересоздаёт WebView")
def test_orientation_rotation_preserves_tab_state(clean_app, driver):
    # Given приложение открыто на статической информационной странице AO3 (`/tos`)
    # в portrait, страница проскроллена вниз, WebView-маркер зафиксирован ДО
    # поворота. Используется `/tos` (`browser_steps.open_stable_tall_page`), НЕ
    # страница самой работы W: страница `/works/{synthetic_id}` (реальный 404 от
    # archiveofourown.org — синтетические ao3_id не существуют на сайте) на этом
    # эмуляторе имеет `scrollHeight=897 < innerHeight=1897` (эмпирически измерено
    # при написании теста, тот же класс, что AT-BUG-015 — Browse root тоже короче
    # экрана): `scrollTo` там легитимно клампится к 0, скроллить физически нечего.
    # `/tos` — тот же выбор, что TC-047 (см. её докстринг за полным обоснованием:
    # высок, стабилен между загрузками), поддержка поворота подтверждена по коду
    # (`AndroidManifest.xml` activity несёт `configChanges="uiMode|orientation|
    # screenSize|screenLayout|smallestScreenSize"`, без `screenOrientation`-лока;
    # `MainActivity.kt` ~561-579 — явная landscape-логика side panel).
    app_steps.wait_ui_ready(driver)
    url_before = browser_steps.open_stable_tall_page(driver)
    browser_steps.scroll_webview_to(driver, 900)
    scroll_before = browser_steps.get_webview_scroll_y(driver)
    # Детекция «WebView не пересоздан»: переиспользован СУЩЕСТВУЮЩИЙ примитив
    # `mark_no_reload_baseline`/`assert_no_reload_since` (TC-010/011) — window-
    # маркер, переживающий JS-обновления, но стираемый любой РЕАЛЬНОЙ навигацией/
    # пересозданием документа; предпочтён самодельному `window.__ao3TestMarker`
    # (упомянутому в заметках кейса как альтернатива) — тот же наблюдаемый факт,
    # уже принятый и проверенный в другом месте этого фреймворка (TC-010/011).
    marker = browser_steps.mark_no_reload_baseline(driver)

    # When устройство поворачивается в landscape
    browser_steps.rotate(driver, "LANDSCAPE")

    # Then активная вкладка/URL не изменились, WebView не пересоздан (маркер
    # пережил поворот), позиция скролла не сброшена к верху страницы (щедрый
    # допуск — не пиксель-в-пиксель, аналог TC-096/TC-099), компоновка WebView
    # соответствует landscape (ширина > высоты — прокси «landscape-компоновка
    # отрисована», НЕ пиксельное сравнение лейаута). Прокси НЕ через
    # взаимодействие с side panel: разведка (emulator-5554, 2026-07-22)
    # обнаружила, что side panel/TabStrip/BottomBar полностью пропадают из
    # accessibility-дерева СРАЗУ после поворота (не восстанавливаются за 10с
    # ожидания/тап) — тот же класс WebView-accessibility-reflow бага, что уже
    # задокументирован в `browser_screen.py::top_chrome_avg_luma` для
    # входа/выхода fullscreen, здесь триггерится поворотом. Находка для триажа
    # (доложена координатору отдельно), не блокер этого кейса — WebView-rect
    # прокси её не затрагивает.
    url_landscape = app_steps.wait_app_ready(driver)
    assert url_landscape.rstrip("/") == url_before.rstrip("/"), (
        f"URL изменился после поворота в landscape: {url_before} -> {url_landscape}"
    )
    browser_steps.assert_no_reload_since(driver, marker)
    scroll_landscape = browser_steps.get_webview_scroll_y(driver)
    # Щедрый допуск (50% от исходной позиции) — не пиксель-в-пиксель (лейаут
    # меняется при повороте, аналог бюджета TC-096/TC-099), но заведомо выше
    # «сброшен к началу страницы»
    assert scroll_landscape > scroll_before * 0.5, (
        f"скролл сброшен к верху страницы после поворота в landscape: "
        f"{scroll_landscape} (было {scroll_before} до поворота)"
    )
    browser_steps.assert_layout_matches_orientation(driver, landscape=True)

    # When устройство поворачивается ОБРАТНО в portrait — свойство симметрично
    # (Инвариант кейса: верно для КАЖДОГО направления, не только одного)
    browser_steps.rotate(driver, "PORTRAIT")

    # Then та же вкладка/URL/скролл сохранены, WebView всё ещё не пересоздан
    url_portrait = app_steps.wait_app_ready(driver)
    assert url_portrait.rstrip("/") == url_before.rstrip("/"), (
        f"URL изменился после поворота обратно в portrait: {url_before} -> {url_portrait}"
    )
    browser_steps.assert_no_reload_since(driver, marker)
    scroll_portrait = browser_steps.get_webview_scroll_y(driver)
    assert scroll_portrait > scroll_before * 0.5, (
        f"скролл сброшен к верху страницы после поворота обратно в portrait: "
        f"{scroll_portrait} (было {scroll_before} до поворота)"
    )
    browser_steps.assert_layout_matches_orientation(driver, landscape=False)
