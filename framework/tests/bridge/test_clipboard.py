"""Пилот L2 (docs/tasks/p2-pyramid-bridge.md N5): DEBUG copy-URL кнопка
(`ao3_bridge.js`, `window.__ao3DebugCopyUrl`) — `navigator.clipboard.writeText`
управляемый resolve/reject, `document.execCommand` фолбэк-путь.

**Оговорка (Р3, класс BUG-071):** этот пилот проверяет JS-ФОЛБЭК бриджа — какую
ветку `ao3_bridge.js` выбирает и что она РЕАЛЬНО пишет в стаб — а НЕ поведение
самого системного clipboard-провайдера Android/WebView. Device-покрытие
BUG-071 остаётся L3/L4 (`docs/01-test-strategy.md` §9), этот харнесс его не
снимает и не заменяет."""
from __future__ import annotations

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data.works import LOVED

_COPY_BUTTON_SELECTOR = "body > button"  # DEBUG_COPY_URL_BUTTON, framework/web/selectors.py
_LISTING_URL = "https://archiveofourown.org/works"


def _click_copy_action() -> dict:
    return {"id": "click", "type": "eval", "code": f"document.querySelector('{_COPY_BUTTON_SELECTOR}').click(); 'clicked'"}


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-clipboard-write-text-resolves-with-location-href")
@allure.title("L2 bridge (BUG-071 оговорка -- JS-фолбэк, не WebView): clipboard.writeText resolve пишет location.href")
def test_clipboard_write_text_resolves_with_location_href(bridge_call):
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": _LISTING_URL,
        "flags": {"ao3DebugCopyUrl": True},
        "actions": [_click_copy_action()],
    })
    assert response["clipboardWritten"] == _LISTING_URL
    assert response["execCommandCalled"] is False


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-clipboard-write-text-rejection-falls-back-to-exec-command")
@allure.title("L2 bridge (BUG-071 оговорка): clipboard.writeText reject -> execCommand-фолбэк")
def test_clipboard_write_text_rejection_falls_back_to_exec_command(bridge_call):
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": _LISTING_URL,
        "flags": {"ao3DebugCopyUrl": True},
        "clipboard": {"mode": "reject"},
        "execCommandResult": True,
        "actions": [_click_copy_action()],
    })
    assert response["clipboardWritten"] is None
    assert response["execCommandCalled"] is True


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-copy-button-hidden-but-click-handler-still-writes-when-debug-flag-off")
@allure.title(
    "L2 bridge, красная проба: DEBUG copy-URL кнопка скрыта (display=none) при выключенном флаге, "
    "но её click-обработчик всё ещё пишет location.href"
)
def test_copy_button_hidden_but_click_handler_still_writes_when_debug_flag_off(bridge_call):
    """Красная проба (Б3, критик-раунд 2, зонд C `p2-n5-bridge-harness`
    accepted 2026-08-19T11:42:52): ПРЕЖНЯЯ версия этого теста НЕ кликала по
    кнопке — `assert clipboardWritten is None` был вакуумен (истинен для
    ЛЮБОГО кода, который не пишет в стаб при отсутствии клика), а заголовок/
    докстринг/имя утверждали, что кнопка при выключенном флаге «inert»
    (клик не срабатывает) — это эмпирически ЛОЖНО: `window.__ao3DebugCopyUrl`
    (`ao3_bridge.js:1123`) гейтирует ТОЛЬКО `btn.style.display` — регистрация
    click-обработчика (`ao3_bridge.js:1124`) от флага НЕ зависит. Живой зонд
    критика подтвердил: клик по СКРЫТОЙ кнопке при выключенном флаге ВСЁ РАВНО
    пишет `location.href` в clipboard-стаб. Эта версия КЛИКАЕТ и ассертит
    ФАКТИЧЕСКОЕ поведение SUT: визуально скрыта (`display:none`), но
    функционально жива (клик пишет) — граница задокументирована честно, без
    слова "inert"."""
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": _LISTING_URL,
        "actions": [
            {
                "id": "displayStyle",
                "type": "eval",
                "code": f"document.querySelector('{_COPY_BUTTON_SELECTOR}').style.display",
            },
            _click_copy_action(),
        ],
    })
    assert response["results"]["displayStyle"] == "none"
    assert response["clipboardWritten"] == _LISTING_URL
