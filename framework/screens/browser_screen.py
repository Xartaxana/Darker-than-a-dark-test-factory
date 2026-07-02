"""Экран Browser (главный). Контейнер WebView с AO3 + нативные оверлеи.
Знание о переключении контекстов делегировано core/contexts.
"""
from __future__ import annotations

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
