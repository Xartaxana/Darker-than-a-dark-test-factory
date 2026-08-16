"""Volume-button paging на Browse (`browse-volume-button-paging`,
`MainActivity.kt:105-124,304-310` `volumePageHandler`,
`BrowserViewModel.scrollActivePageBy`, docs/01-test-strategy.md §9
«reading-UX: листание кнопками громкости»).

Блокер AT-BUG-072 (test_debt, Fixed) — примитив `app_steps.press_volume_key`
(обёртка `adb shell input keyevent KEYCODE_VOLUME_DOWN/UP` с параметризуемым
наблюдаемым оракулом, по образцу `app_steps.send_app_to_background`).

TC-252 — основной позитивный путь: пока перехват активен (настройка
`volume_button_scroll` ON, активная вкладка Browse фронтмост),
`MainActivity.onKeyDown` возвращает `true` — событие потребляется ДО штатной
обработки громкости системой, `onKeyUp` тоже глотается (иначе
`VolumeDialogImpl` остаётся «зависшим» после отпускания клавиши). Каждое
нажатие проверяется НЕЗАВИСИМО (Then TC-252 требует линейности — «без
накопления/пропуска»):
  - `browser_steps.assert_volume_page_scroll_delta` — сдвиг `window.scrollY`
    активной вкладки ~0.9×innerHeight (измерение `scrollActivePageBy`:
    `window.scrollBy(0, Math.round(innerHeight*0.9)*direction)`) —
    параллельная структура `assert_tap_to_scroll_delta` (TC-126/127), но
    другой множитель (0.9, не 0.95 — разные механизмы);
  - `app_steps.assert_no_volume_dialog_appears` — системный индикатор
    громкости (`VolumeDialogImpl`, `com.android.systemui`) НЕ появляется;
    это отдельное OS-окно вне `app_package`, недоступное Appium
    accessibility-локаторам — наблюдается через `adb.volume_dialog_visible()`
    (`dumpsys window windows`, эмпирика emulator-5554 2026-08-16).

`listing_paginated.mitm` (`recording_builder.LISTING_PAGINATED_FILENAME`) —
тот же длинный листинг (scrollHeight ~6.4×innerHeight), что использует
TC-129/130 (`test_infinite_scroll.py`) — достаточный запас скролла для двух
нажатий VOLUME_DOWN + двух VOLUME_UP от предскроллённой середины (S0=2×
innerHeight) без клампинга к границам документа в любую сторону."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.steps import app_steps, browser_steps, settings_steps


@pytest.mark.p1
@pytest.mark.replay
@allure.id("TC-252")
@allure.title(
    "Кнопки громкости листают Browse (Down — вперёд, Up — назад) без появления "
    "системного индикатора"
)
@pytest.mark.parametrize("replay", [rb.LISTING_PAGINATED_FILENAME], indirect=True)
def test_volume_buttons_page_browse_listing(replay, clean_app, driver):
    # Given настройка «Page with volume buttons» ON (явно — тот же приём, что
    # enable_infinite_scroll/enable_tap_to_scroll: Given кейса не должен
    # зависеть от значения дефолта), активная вкладка Browse открыта на
    # длинной странице (`listing_paginated.mitm`, тот же fixture, что
    # TC-129/130), предскроллена к середине (позиция S0)
    app_steps.wait_ui_ready(driver)
    app_steps.open_tab(driver, "Settings")
    settings_steps.enable_volume_button_scroll(driver)
    settings_steps.assert_volume_button_scroll_enabled(driver, expected=True)
    app_steps.open_tab(driver, "Browse")
    browser_steps.open_listing(driver, rb.LISTING_PAGINATED_URL)
    inner_height = browser_steps.get_webview_inner_height(driver)
    browser_steps.scroll_webview_to(driver, int(inner_height * 2))
    scroll_before = browser_steps.get_webview_scroll_y(driver)
    assert scroll_before > 0, (
        f"Given TC-252 предскролл к середине длинной страницы не сработал: "
        f"scrollY={scroll_before}"
    )

    # When пользователь дважды нажимает VOLUME_DOWN
    for _ in range(2):
        app_steps.press_volume_key(
            driver, "down",
            oracle=lambda: browser_steps.get_webview_scroll_y(driver) != scroll_before,
        )
        # Then каждое нажатие VOLUME_DOWN сдвигает scroll-позицию активной
        # вкладки ВПЕРЁД примерно на экран (линейно за каждое нажатие)
        scroll_before = browser_steps.assert_volume_page_scroll_delta(
            driver, scroll_before, inner_height, direction=1,
        )
        # And системный индикатор громкости НЕ появляется
        app_steps.assert_no_volume_dialog_appears()

    # затем дважды VOLUME_UP
    for _ in range(2):
        app_steps.press_volume_key(
            driver, "up",
            oracle=lambda: browser_steps.get_webview_scroll_y(driver) != scroll_before,
        )
        # Then каждое нажатие VOLUME_UP сдвигает позицию НАЗАД примерно на экран
        scroll_before = browser_steps.assert_volume_page_scroll_delta(
            driver, scroll_before, inner_height, direction=-1,
        )
        # And системный индикатор громкости НЕ появляется (перехват key-up
        # тоже работает — не остаётся «зависшего» системного UI)
        app_steps.assert_no_volume_dialog_appears()
