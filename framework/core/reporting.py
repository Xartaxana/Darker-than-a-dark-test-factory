"""Артефакты падений. При провале теста автоматически прикрепляет к Allure:
скриншот, page source активного контекста, logcat и текущий контекст/URL.
Вызывается из хука pytest в conftest.
"""
from __future__ import annotations

from pathlib import Path

import allure

from framework.config import settings
from framework.core import adb


def attach_failure_artifacts(driver, test_name: str) -> None:
    if driver is None:
        return
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in test_name)[:80]

    # Скриншот
    try:
        allure.attach(driver.get_screenshot_as_png(), name="screenshot",
                      attachment_type=allure.attachment_type.PNG)
    except Exception:  # noqa: BLE001
        pass

    # Контекст + (для WebView) URL
    try:
        ctx = driver.current_context
        info = f"context={ctx}"
        if "WEBVIEW" in str(ctx):
            info += f"\nurl={driver.current_url}"
        allure.attach(info, name="context", attachment_type=allure.attachment_type.TEXT)
    except Exception:  # noqa: BLE001
        pass

    # Page source
    try:
        allure.attach(driver.page_source, name="page_source",
                      attachment_type=allure.attachment_type.XML)
    except Exception:  # noqa: BLE001
        pass

    # Logcat
    try:
        dest = Path(settings.ALLURE_RESULTS) / f"{safe}_logcat.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        adb.logcat_dump(dest)
        allure.attach(dest.read_text(encoding="utf-8", errors="replace"),
                      name="logcat", attachment_type=allure.attachment_type.TEXT)
    except Exception:  # noqa: BLE001
        pass
