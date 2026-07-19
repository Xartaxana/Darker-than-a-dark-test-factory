"""Экран Browser (главный). Контейнер WebView с AO3 + нативные оверлеи.
Знание о переключении контекстов делегировано core/contexts.
"""
from __future__ import annotations

import io

from appium.webdriver.common.appiumby import AppiumBy
from PIL import Image
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.interaction import POINTER_TOUCH

from framework.core import contexts
from framework.core.waits import wait_until
from framework.screens.base_screen import BaseScreen


class BrowserScreen(BaseScreen):
    def wait_ao3_loaded(self, timeout: int | None = None) -> str:
        """Ждёт, пока WebView догрузит страницу AO3; возвращает URL. Возврат в нативный контекст."""
        with contexts.in_webview(self.driver, timeout) as _:
            url = wait_until(
                self.driver,
                lambda d: d.current_url if "archiveofourown.org" in (d.current_url or "") else False,
                timeout=timeout,
                message="AO3 не загрузился в WebView",
            )
        return url

    def wait_home_page_loaded(self, timeout: int | None = None) -> None:
        """Ждёт, пока `onPageFinished` РЕАЛЬНО завершится для домашней страницы —
        не просто её navigation-commit (см. `wait_ao3_loaded`/`current_url` выше,
        который может отразить URL раньше, чем `onPageFinished` успеет выполниться:
        current_url — свойство навигационной записи chromedriver, обновляется на
        commit, а не на полную загрузку).

        Опрашивает JS-маркер `window.__ao3AppDark` — `BrowserScreen.kt onPageFinished`
        (app-under-test, ~594-600) вызывает `viewModel.onPageLoaded(tabId, url)`
        СИНХРОННО (обновляет `tabs[0].url` в StateFlow) НЕПОСРЕДСТВЕННО ПЕРЕД тем,
        как инжектит `window.__ao3AppDark = ...` тем же колбэком — появление маркера
        в DOM детерминированно доказывает, что `onPageLoaded` уже отработал и
        `tabs[0].url` уже разошёлся с плейсхолдером `HOME_URL`.

        Закрывает класс гонки TC-022/023/024/025 (ревью 2026-07-18, п.5): без этого
        первый `open_deep_link` после `wait_ui_ready`/`wait_ao3_loaded` мог обогнать
        `onPageLoaded`, и `BrowserViewModel.openOrNavigateDeepLink` (kt:637-644) шёл
        веткой navigate-in-place (`state.tabs[0].url == HOME_URL`) вместо добавления
        вкладки, что портило счёт/позиции вкладок во всех 4 сценариях по-разному."""
        with contexts.in_webview(self.driver, timeout) as _:
            wait_until(
                self.driver,
                lambda d: d.execute_script("return typeof window.__ao3AppDark !== 'undefined'"),
                timeout=timeout,
                message="домашняя страница AO3 не завершила загрузку (onPageFinished/window.__ao3AppDark не появился)",
            )

    def open_work(self, work_id: str) -> None:
        """Навигация WebView на страницу работы. В live — реальный переход по URL AO3.
        (Используется точечно; основной P0-smoke опирается на сидинг данных, чтобы
        не нагружать сторонний сайт AO3.)"""
        with contexts.in_webview(self.driver):
            self.driver.get(f"https://archiveofourown.org/works/{work_id}")
            wait_until(
                self.driver,
                lambda d: f"/works/{work_id}" in (d.current_url or ""),
                message="страница работы не открылась",
            )

    # --- Управление вкладками (tab bar виден, когда открыто >1 вкладки) ---
    _CLOSE_TAB_LOCATOR = (AppiumBy.ANDROID_UIAUTOMATOR,
                          'new UiSelector().description("Close tab")')

    def close_leftmost_tab(self) -> None:
        """Закрывает самую левую вкладку в tab-баре — используется, чтобы после
        открытия скачанного файла (BrowserViewModel.openTab ВСЕГДА добавляет
        вкладку, никогда не заменяет стартовую Home-вкладку) осталась ровно одна
        WebView-страница: при нескольких открытых страницах в ОДНОМ WEBVIEW-процессе
        chromedriver подключается к недетерминированной из них (см. TC-034 —
        `driver.current_url`/DOM-проверки иначе читают чужую вкладку).

        Сразу после открытия новой вкладки tab-бар может ещё анимироваться —
        вторая кнопка «Close tab» рендерится не мгновенно (гонка, поймана в
        прогоне полного файла: standalone-прогон не ловит), поэтому явно ждём
        появления ВТОРОЙ кнопки, а не довольствуемся первым снапшотом списка."""
        def _at_least_two(d):
            buttons = d.find_elements(*self._CLOSE_TAB_LOCATOR)
            return buttons if len(buttons) >= 2 else False
        try:
            buttons = wait_until(self.driver, _at_least_two, timeout=8,
                                 message="в tab-баре не появилась вторая вкладка для закрытия")
        except Exception:  # noqa: BLE001 — таймаут ожидания второй вкладки не фатален
            buttons = self.driver.find_elements(*self._CLOSE_TAB_LOCATOR)
        if len(buttons) <= 1:
            return
        leftmost = min(buttons, key=lambda e: e.rect["x"])
        leftmost.click()

    # --- TabStrip (ui/browser/TabStrip.kt) — рендерится только когда
    # !isFullscreen && tabs.size > 1 (MainActivity.kt ~406, TC-058). "New tab"
    # content-desc иконка — стабильный признак присутствия полосы, НЕ завязанный
    # на динамические заголовки чипов вкладок, но НАДЁЖЕН только ДО первого
    # полного цикла вход+выход fullscreen (см. `top_chrome_avg_luma` ниже).
    def is_tab_strip_visible(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_desc("New tab"), timeout=timeout if timeout is not None else 5)

    def top_chrome_avg_luma(self) -> float:
        """Средняя яркость (0..255) полосы у самого верха экрана (правее side panel,
        верхние ~12% высоты) — прокси видимости TabStrip/статус-бара через ПИКСЕЛИ,
        не accessibility-дерево (TC-058, диагностировано 2026-07-18 на живом дереве
        и скриншотах): `WindowInsetsControllerCompat.hide()`+`.show(systemBars())`
        (полный цикл вход+выход fullscreen, MainActivity.kt ~206-213) оставляет
        accessibility-провайдер WebView в состоянии, где ВСЕ соседние Compose-узлы
        вне side panel (TabStrip, BottomNav) перестают отдаваться в UiAutomator2-
        дерево — `is_tab_strip_visible`/поиск "Library" в BottomNav после этого
        стабильно не находят СУЩЕСТВУЮЩИЕ (визуально отрисованные, подтверждено
        скриншотом) элементы. Похоже на известный класс WebView-accessibility-
        багов при resize/reflow, НЕ связанный с самим TabStrip кодом — вне скоупа
        правки app-under-test. TabStrip.kt красит светлый Surface-фон в этой
        полосе (mean luma ~230 на emulator-5554); в fullscreen эта же полоса —
        чёрный статус-бар/тёмный верх WebView-контента (mean luma ~85) — разница
        измерена эмпирически (baseline≈234, fullscreen≈86, после выхода≈174),
        достаточна для ratio-порога относительно baseline того же прогона."""
        size = self.driver.get_window_size()
        png = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("L")
        box = (int(size["width"] * 0.2), 0, size["width"], int(size["height"] * 0.12))
        cropped = img.crop(box)
        hist = cropped.histogram()
        total = sum(hist)
        return sum(i * c for i, c in enumerate(hist)) / total

    # --- Двухпальцевые жесты над контентом (BrowserScreen.kt pointerInput ~255–312) ---
    # UiAutomator2 различает "font" (span меняется, пальцы движутся врозь по диагонали
    # — dy0/dy1 противоположных знаков, avgDy=0, totalDy не растёт) от "brightness"
    # (синхронный параллельный вертикальный драг, dy0/dy1 одного знака). Встроенные
    # `mobile: pinchOpenGesture`/`pinchCloseGesture` UiAutomator2 разводят/сводят два
    # пальца по диагонали от центра области — это меняет span, не даёт параллельного
    # totalDy, поэтому надёжно попадает в font-ветку, а не в brightness (см. TC-053/055).
    def _gesture_area(self) -> dict:
        size = self.driver.get_window_size()
        return {
            "left": int(size["width"] * 0.1),
            "top": int(size["height"] * 0.2),
            "width": int(size["width"] * 0.8),
            "height": int(size["height"] * 0.6),
        }

    def pinch_spread(self, percent: float = 0.15, speed: int = 1200) -> None:
        """Двухпальцевый spread (разведение) над областью контента — увеличивает
        fontSizeStep (тот же эффект, что «A+» в side panel, см. TC-051/TC-052)."""
        self.driver.execute_script("mobile: pinchOpenGesture", {**self._gesture_area(), "percent": percent, "speed": speed})

    def pinch_close(self, percent: float = 0.15, speed: int = 1200) -> None:
        """Двухпальцевый pinch (сведение) над областью контента — уменьшает fontSizeStep."""
        self.driver.execute_script("mobile: pinchCloseGesture", {**self._gesture_area(), "percent": percent, "speed": speed})

    def _two_finger_vertical_drag(self, dy_total_px: int, steps: int = 20, duration_ms: int = 40) -> None:
        """Синхронный параллельный вертикальный драг двумя пальцами — ветка «яркость»
        в pointerInput (avgDy считается только когда dy0*dy1 > 0, т.е. одного знака).
        Нет готового `mobile:`-жеста UiAutomator2 под два синхронных пальца — только
        сырые W3C Actions с двумя touch-pointer'ами, двигающимися идентично на каждом
        шаге (гарантирует одинаковый знак dy у обоих пальцев на каждом кадре).
        dy_total_px > 0 — вниз (снижение яркости), < 0 — вверх (повышение).
        """
        size = self.driver.get_window_size()
        w, h = size["width"], size["height"]
        x1, x2 = int(w * 0.3), int(w * 0.7)
        y_start = int(h * 0.08) if dy_total_px > 0 else int(h * 0.92)
        step_dy = dy_total_px / steps

        builder = ActionBuilder(self.driver)
        finger1 = builder.add_pointer_input(POINTER_TOUCH, "finger1")
        finger2 = builder.add_pointer_input(POINTER_TOUCH, "finger2")
        finger1.create_pointer_move(duration=0, x=x1, y=y_start)
        finger1.create_pointer_down()
        finger2.create_pointer_move(duration=0, x=x2, y=y_start)
        finger2.create_pointer_down()
        for i in range(1, steps + 1):
            y = int(y_start + i * step_dy)
            finger1.create_pointer_move(duration=duration_ms, x=x1, y=y)
            finger2.create_pointer_move(duration=duration_ms, x=x2, y=y)
        finger1.create_pointer_up(0)
        finger2.create_pointer_up(0)
        builder.perform()

    def drag_brightness_down(self, dy_total_px: int = 2000) -> None:
        """Двухпальцевый параллельный драг вниз — снижает яркость окна, а ниже
        системного минимума включает чёрный overlay (MainActivity.kt overlayAlpha)."""
        self._two_finger_vertical_drag(dy_total_px)

    def drag_brightness_up(self, dy_total_px: int = 2000) -> None:
        """Обратный драг вверх — убирает overlay и повышает яркость обратно."""
        self._two_finger_vertical_drag(-dy_total_px)

    def screenshot_avg_luma(self) -> float:
        """Средняя яркость (0..255) полноэкранного скриншота — прокси для реальной
        яркости окна/overlay (Window.attributes.screenBrightness UiAutomator2 не видит
        как UI-элемент; overlay визуально затемняет весь кадр, см. TC-055 заметки)."""
        png = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("L")
        hist = img.histogram()
        total = sum(hist)
        return sum(i * c for i, c in enumerate(hist)) / total

    # --- Filter panel (BottomBar.kt FilterPanel — "AO3 filter: <name>" триггер +
    # выпадашка сохранённых FilterProfile) — TC-041/TC-042. Видна только на
    # BROWSE + filterable-странице (BrowserViewModel.FILTERABLE_PAGE regex по
    # URL активной вкладки), И только когда нижняя pill-ручка раскрыта
    # (AnimatedVisibility делит секцию с Ao3BottomNav — см. navigation.py) —
    # раскрытие ручки не входит сюда: композиция с BottomNav делается в
    # browser_steps.py, эта панель знает только про сам триггер/пункты. ---
    _FILTER_TRIGGER = (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("AO3 filter")')

    def open_filter_dropdown(self, timeout: int | None = None) -> None:
        contexts.to_native(self.driver)
        self.tap(self._FILTER_TRIGGER, timeout=timeout)

    def filter_dropdown_has_option(self, name: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text(name), timeout=timeout if timeout is not None else 5)

    def select_filter_option(self, name: str, timeout: int | None = None) -> None:
        """Тап по пункту `name` в РАСКРЫТОЙ выпадашке (`AppDropdownMenu` —
        `.clickable { onSelect(option); onDismissRequest() }`, BottomBar.kt) — сама
        закрывается после выбора, отдельного закрытия не требуется. TC-041."""
        contexts.to_native(self.driver)
        self.tap(self.by_text(name), timeout=timeout)

    # --- Save filter dialog (MainActivity.kt AlertDialog "Save filter") — TC-040 ---
    _FILTER_NAME_FIELD = (AppiumBy.ANDROID_UIAUTOMATOR,
                          'new UiSelector().className("android.widget.EditText")')

    def save_filter_dialog_visible(self, timeout: int | None = None) -> bool:
        contexts.to_native(self.driver)
        return self.is_present(self.by_text("Save filter"), timeout=timeout if timeout is not None else 10)

    def enter_filter_profile_name(self, name: str) -> None:
        """Поле предзаполнено авто-сгенерированным именем (`pendingSaveFilterName`,
        `generateProfileName` в BrowserViewModel.kt) — `.clear()` обязателен перед
        вводом своего имени, иначе оно допишется к сгенерированному."""
        contexts.to_native(self.driver)
        field = self.find(self._FILTER_NAME_FIELD)
        field.clear()
        field.send_keys(name)

    def confirm_save_filter(self) -> None:
        contexts.to_native(self.driver)
        self.tap(self.by_text("Save"))

    # --- TabStrip управление вкладками (TabStrip.kt, MainActivity.kt) — TC-022/023/
    # 024/025/026. "New tab"/"Close tab" content-desc уже используются выше
    # (`is_tab_strip_visible`/`_CLOSE_TAB_LOCATOR`); методы ниже добавляют навигацию
    # по КОНКРЕТНОЙ вкладке и диалог лимита.
    #
    # ВАЖНО (разведка TC-023/024/025/026, 2026-07-18): при >1 одновременно живых
    # `android.webkit.WebView` (background-вкладки НЕ уничтожаются, просто отсоединены
    # от FrameLayout — см. BrowserScreen.kt activeContainer-свап) Appium/chromedriver
    # экспонирует РОВНО ОДИН контекст `WEBVIEW_<pkg>` вне зависимости от числа вкладок
    # и он ПРИЛИПАЕТ к вкладке-0 (первый когда-либо созданный WebView) — ни
    # переключение активной вкладки в UI, ни повторный `switch_to.context()` не
    # переключают его на другую вкладку, пока вкладка-0 жива (эмпирически проверено:
    # `driver.current_url`/`driver.get()`/`execute_script` внутри `contexts.in_webview`
    # ВСЕГДА бьют по вкладке-0). Единственный способ читать/писать WebView-контент
    # НЕ-нулевой вкладки — временно свести число вкладок к одной (закрыть остальные):
    # уничтожение текущей ПРИЛИПШЕЙ цели форсирует chromedriver переподключиться к
    # единственной оставшейся (тоже подтверждено эмпирически). НАТИВНЫЕ жесты (тап,
    # свайп) этому классу не подвержены — они бьют по физически видимому View
    # (activeContainer), поэтому переключение вкладок/скролл активной вкладки надёжны
    # нативными жестами; для контента НЕ-активной/НЕ-нулевой вкладки — только через
    # НАТИВНО видимый заголовок чипа (`TabInfo.title`, TabStrip.kt Text) — WebChromeClient.
    # onReceivedTitle отражается в аксессибилити-дереве без похода в WEBVIEW-контекст.
    NEW_TAB_DESC = "New tab"
    CLOSE_TAB_DESC = "Close tab"
    TAB_LIMIT_TITLE = "Tab limit reached"

    def tap_new_tab(self) -> None:
        self.tap(self.by_desc(self.NEW_TAB_DESC))

    def tab_chip_locator(self, position: int):
        """Локатор родительского Row чипа по 0-based document-order позиции среди
        ТЕКУЩЕ СКОМПОНОВАННЫХ (не виртуализированных LazyRow за пределами вьюпорта)
        чипов — надёжно для малого числа вкладок (в этой кодовой базе — до ~7,
        см. заметки TC-024.md); родитель через `/..` — тот же паттерн, что
        `side_panel.py::_button_container` (клик должен попасть в тело чипа, не в
        14dp иконку закрытия, которая сама кликабельна и переопределяет тап по себе)."""
        return (AppiumBy.XPATH, f'(//*[@content-desc="{self.CLOSE_TAB_DESC}"])[{position + 1}]/..')

    def tap_tab_chip(self, position: int, timeout: int | None = None) -> None:
        self.tap(self.tab_chip_locator(position), timeout=timeout)

    def tab_chip_title_at(self, position: int, timeout: int | None = None) -> str:
        """Текст Text-узла чипа на 0-based document-order позиции — Compose кладёт
        Text ПЕРЕД Icon(desc="Close tab") в том же Row (TabStrip.kt `TabChip`),
        поэтому `preceding-sibling::*[1]` от иконки закрытия — сам заголовок этого
        чипа. Используется для позиционной проверки (TC-023: восстановленная Undo
        вкладка должна оказаться РОВНО на позиции 1, между исходными соседями) без
        похода в WEBVIEW-контекст (см. докстринг класса выше)."""
        locator = (AppiumBy.XPATH,
                   f'(//*[@content-desc="{self.CLOSE_TAB_DESC}"])[{position + 1}]/preceding-sibling::*[1]')
        return self.text_of(locator, timeout=timeout)

    def close_tab_icon_count(self) -> int:
        return len(self.driver.find_elements(*self.by_desc(self.CLOSE_TAB_DESC)))

    def swipe_close_tab(self, position: int) -> None:
        """Swipe-up по чипу (TabStrip.kt `TabChip` swipeModifier: `totalDrag < -60f`
        триггерит `onClose`) — жест по конкретному элементу, амплитуда с запасом
        над порогом."""
        chip = self.find(self.tab_chip_locator(position))
        rect = chip.rect
        x = rect["x"] + rect["width"] // 2
        y = rect["y"] + rect["height"] // 2
        self.driver.swipe(x, y, x, max(0, y - 300), 300)

    def tab_limit_dialog_visible(self, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text(self.TAB_LIMIT_TITLE), timeout=timeout if timeout is not None else 5)

    def tab_limit_dialog_message(self, timeout: int | None = None) -> str:
        return self.text_of(self.by_text_contains("tabs open"), timeout)

    def dismiss_tab_limit_dialog(self) -> None:
        self.tap(self.by_text("OK"))

    TAB_CLOSED_SNACKBAR_TEXT = "Tab closed"

    def undo_snackbar_visible(self, timeout: int = 5) -> bool:
        return self.is_present(self.by_text_contains("Undo"), timeout=timeout)

    def tap_undo_snackbar(self, timeout: int | None = None) -> None:
        self.tap(self.by_text_contains("Undo"), timeout=timeout)

    def swipe_dismiss_snackbar(self, timeout: int | None = None) -> None:
        """Смахивает snackbar «Tab closed» горизонтально (Material3 `SnackbarHost`
        поддерживает swipe-to-dismiss) — используется, когда СЛЕДУЮЩЕЕ закрытие
        вкладки должно случиться СРАЗУ, не дожидаясь `SnackbarDuration.Short`
        (~4с): `SnackbarHostState.showSnackbar` (MainActivity.kt `onCloseTab`)
        сериализует показы через `Mutex` — 6 закрытий подряд БЕЗ явного
        закрытия/смахивания snackbar'а каждого предыдущего закрытия оставляют
        часть snackbar'ов недостижимыми в разумное время автотеста (TC-024,
        разведка 2026-07-18)."""
        el = self.find(self.by_text(self.TAB_CLOSED_SNACKBAR_TEXT), timeout)
        rect = el.rect
        y = rect["y"] + rect["height"] // 2
        x1 = rect["x"] + rect["width"] - 20
        x2 = rect["x"] + 5
        self.driver.swipe(x1, y, x2, y, 250)

    def tab_title_visible(self, title_substring: str, timeout: int | None = None) -> bool:
        return self.is_present(self.by_text_contains(title_substring), timeout=timeout if timeout is not None else 5)

    def swipe_scroll_active_tab_down(self, distance_px: int = 1400) -> None:
        """Нативный свайп вверх по видимой WebView-области — реальный физический
        скролл активной вкладки (в отличие от JS `scrollTo`, не подвержен
        прилипанию chromedriver к вкладке-0, см. докстринг выше): бьёт по физически
        отображаемому View, а не по WEBVIEW-контексту."""
        contexts.to_native(self.driver)
        wv = self.driver.find_element(AppiumBy.CLASS_NAME, "android.webkit.WebView")
        rect = wv.rect
        x = rect["x"] + rect["width"] // 2
        y_start = rect["y"] + int(rect["height"] * 0.75)
        y_end = max(rect["y"] + 50, y_start - distance_px)
        self.driver.swipe(x, y_start, x, y_end, 400)

    def webview_avg_luma(self) -> float:
        """Средняя яркость (0..255) области экрана, занятой нативным WebView-элементом —
        изолирует WebView-контент (страница AO3) от Compose-хрома вокруг (top bar/bottom
        nav), который красится отдельно и мгновенно (см. TC-047). Прокси для
        алгоритмического затемнения страницы (ALGORITHMIC_DARKENING/FORCE_DARK, см.
        TC-048 — только наблюдаемый визуальный результат, не internal API applyDarkMode()).

        Почему `find_element` (первый WebView) здесь безопасен, хотя WebView'ов больше
        одного. Эмпирически (TC-048 на emulator-5554) в дереве UiAutomator даже при
        ОДНОЙ логической вкладке присутствуют ДВА `android.webkit.WebView`, оба
        `displayed=True`, со стекнутыми почти идентичными полноэкранными bounds
        (x=0, y=128, 1080x~2094, разница ~2px). Метод не читает контент элемента, а
        КРОПАЕТ полноэкранный скриншот по его rect — а раз оба кандидата делят один
        экранный прямоугольник, кроп захватывает одни и те же композитно отрисованные
        (верхний = активный) пиксели, какой бы из двух ни вернул `find_element`. Поэтому
        замер luma инвариантен к тому, какой WebView выбран.

        Граница применимости (НЕ путать с TC-034/AT-BUG-004). Тот недетерминизм — про
        WEBVIEW-контекст: chromedriver видит все live web-страницы одного
        webview-процесса и подключается к недетерминированной, из-за чего
        `driver.current_url`/DOM читают чужую вкладку. ЗДЕСЬ контекст НАТИВНЫЙ и мерятся
        экранные пиксели по rect — этот класс отказа сюда не переносится, ПОКА кандидаты
        делят экранный прямоугольник. Если будущий сценарий даст WebView'ы с РАЗНЫМИ
        bounds (реально фоновая/оффскрин вкладка, split-view, превью), «первый» может
        закропать не тот регион — тогда выбирать топовый по z-order / по id активной
        вкладки. Сегодня такого сценария нет, поэтому спец-логика не вводится."""
        contexts.to_native(self.driver)
        el = self.driver.find_element(AppiumBy.CLASS_NAME, "android.webkit.WebView")
        rect = el.rect
        png = self.driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("L")
        box = (rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])
        cropped = img.crop(box)
        hist = cropped.histogram()
        total = sum(hist)
        return sum(i * c for i, c in enumerate(hist)) / total

    # --- Long-press ссылки ВНУТРИ WebView (TC-026, bugs/AT-BUG-018.md, Fixed) ---
    # 5 независимых механизмов синтетической long-press-инъекции ПО КООРДИНАТАМ
    # (голые x/y, elementId контейнера `android.webkit.WebView` + офсет, сырые
    # W3C Actions с/без micro-jitter, `adb shell input swipe` с идентичными
    # start/end) дали 1/20 успехов (<10%) — системная ненадёжность touch-инъекции
    # Appium/UiAutomator2 НАД WebView-контентом, не проблема локатора/координаты.
    # Разбор AT-BUG-019 (латентный риск `navigation.py::_find_pill`) вскрыл ключевой
    # факт: интерактивные элементы ВНУТРИ живого WebView (ссылки/кнопки/чекбоксы
    # страницы) экспонируются UiAutomator2 как ОТДЕЛЬНЫЕ NATIVE a11y-узлы
    # (`android.view.View`, `clickable=true`, `content-desc` = видимый текст
    # элемента) — НЕ как часть самого контейнера `android.webkit.WebView`. Долгий
    # тап через `mobile: longClickGesture` по `elementId` ИМЕННО ЭТОГО узла — тот
    # же паттерн, что уже стабильно работает на native Compose-элементах (см.
    # `library_screen.py::long_press_work`) — даёт устойчивую инъекцию (разведка:
    # 5/5 успехов на ПЕРВОЙ попытке свежей сессии, ~4-5/6 при повторных попытках в
    # одной сессии подряд — на порядок надёжнее координатных механизмов).
    def find_link_a11y_node_by_text(self, text: str, timeout: int | None = None):
        """Опрашивает НАТИВНОЕ a11y-дерево, а не читает один раз: проекция
        WebView-контента DOM->a11y отстаёт от готовности самого DOM (`open_listing`
        ждёт лишь JS/DOM-условие) — разведка наблюдала окна с всего 2-3 нативными
        clickable-узлами (нижний scroll-индикатор/футер, без единого блёрба) сразу
        после навигации. Сам WebView-контейнер исключается явно по className (тот
        же класс риска, что `navigation.py::_find_pill`, AT-BUG-019) — матчинг
        только по content-desc потомков, не по геометрии/координатам."""
        contexts.to_native(self.driver)

        def _find(d):
            for el in d.find_elements(AppiumBy.XPATH, '//*[@clickable="true"]'):
                cls = el.get_attribute("className") or ""
                if "WebView" in cls:
                    continue
                if el.get_attribute("contentDescription") == text:
                    return el
            return False

        return wait_until(
            self.driver, _find, timeout=timeout,
            message=f"native a11y-узел ссылки {text!r} не найден в дереве (проекция "
                    f"WebView->a11y не успела или ссылка с таким текстом отсутствует)",
        )

    def long_press_link_by_text(self, text: str, timeout: int | None = None) -> None:
        """Настоящий Android long-press по НАТИВНОМУ a11y-узлу ссылки внутри
        WebView (не по координатам/офсету контейнера) — см. докстринг
        `find_link_a11y_node_by_text` и `bugs/AT-BUG-018.md` за полным обоснованием."""
        node = self.find_link_a11y_node_by_text(text, timeout)
        self.driver.execute_script(
            "mobile: longClickGesture", {"elementId": node.id, "duration": 1200})
