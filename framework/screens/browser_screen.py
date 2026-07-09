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

    def webview_avg_luma(self) -> float:
        """Средняя яркость (0..255) области экрана, занятой именно нативным WebView-
        элементом — изолирует WebView-контент (страница AO3) от Compose-хрома вокруг
        (top bar/bottom nav), который красится отдельно и мгновенно (см. TC-047).
        Прокси для алгоритмического затемнения страницы (ALGORITHMIC_DARKENING/
        FORCE_DARK, см. TC-048 — только наблюдаемый визуальный результат, не internal
        API applyDarkMode())."""
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
