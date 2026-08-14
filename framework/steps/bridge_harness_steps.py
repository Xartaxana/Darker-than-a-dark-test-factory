"""Харнесс управляемого JS-состояния WebView для сценариев «ранний onPageFinished»
(AT-BUG-067, docs/01-test-strategy.md §9 «bridge/canary: инициализация bridge
при РАННЕМ onPageFinished», TC-195/TC-196).

Провоцировать САМУ нативную гонку Android WebView (`onPageFinished` срабатывает
раньше, чем парсер долетел до `<head>`/`<body>`) недоступно детерминированно
через mitm-replay content-дизайн — задержка сетевой доставки не гарантирует
конкретную точку, в которой Android вызовет `onPageFinished` относительно
состояния JS-парсера. Единственный практичный путь — прямой JS-харнесс,
воспроизводящий ТОЧНО ТЕ ЖЕ входные условия, которые проверяет guard
(`document.head`/`document.body` == `null`, `document.readyState`), не пытаясь
спровоцировать нативный тайминг.

Локаторы/JS-строки инкапсулированы здесь (docs/08 §4 C1, `arch_check.py`) —
`framework/tests/` вызывает только именованные шаги ниже, не строит
`execute_script` сама.
"""
from __future__ import annotations

import json

import allure

from framework.config import settings
from framework.core import contexts
from framework.web import selectors

# Точный путь из критерия готовности AT-BUG-067, п.1.
BRIDGE_JS_PATH = (
    settings.REPO_ROOT / "app-under-test" / "app" / "src" / "main" / "assets" / "ao3_bridge.js"
)


def _read_bridge_js_text() -> str:
    """Читает СЫРОЙ текст bridge-скрипта побайтово с диска — БЕЗ ручного
    копирования/пересказа логики в Python (AT-BUG-067, критерий готовности
    п.1): побайтовая идентичность с тем, что реально шлёт приложение —
    иначе харнесс тестирует не тот код, который реально поставляется.
    Читается заново на каждый вызов (не кэшируется), чтобы модуль-уровневый
    monkeypatch (красная проба) мог подменить источник без правки этого
    файла или `app-under-test/`."""
    return BRIDGE_JS_PATH.read_text(encoding="utf-8")


@allure.step("Given/When JS-контекст WebView приведён в состояние «ранний onPageFinished» (readyState={ready_state}, харнесс AT-BUG-067)")
def simulate_early_bridge_injection(driver, ready_state: str) -> None:
    """AT-BUG-067, критерий готовности п.2 — ОДИН `execute_script`, порядок
    ОБЯЗАТЕЛЕН:

    (а) ПЕРВЫМ действием удаляет ВСЕ уже существующие враппers
        (`document.querySelectorAll('[data-ao3-btn-wrap]').forEach(el =>
        el.remove())`) — приложение уже инжектировало bridge на СВОЁМ
        `onPageFinished` (`BrowserScreen.kt:613`), поэтому на открытой
        replay-странице враппers существуют ДО старта харнесса; без этого шага
        якорь `count === 0` в TC-195/TC-196 недостижим, а per-element guard
        (`ao3_bridge.js:872`) делает форсированное переисполнение
        наблюдательно no-op'ом (`[data-ao3-note-btn]`/`[data-ao3-tag-btn]` —
        дети враппера, удаляются вместе с ним);
    (б)/(в) затеняет `document.head`/`document.body` как `null` и
        `document.readyState` значением `ready_state` через
        `Object.defineProperty(document, ..., {get, configurable: true})`
        (`configurable: true` обязателен — иначе снятие тени в
        `restore_shadow_and_dispatch_dcl` невозможно);
    (г) сбрасывает `window.__ao3Bridge` (`delete window.__ao3Bridge`) — та же
        ось, что удаление враппers: снимаются ОБА следа уже состоявшейся
        инжекции (модуль-уровневый флаг `:5`/`:19` И per-element след `:872`) —
        снятие только одного из них оставляет харнесс наблюдательно
        бессильным;
    (д) выполняет прочитанный текст скрипта — эквивалент `evaluateJavascript`
        на раннем `onPageFinished`.
    """
    bridge_text = _read_bridge_js_text()
    setup = (
        f"document.querySelectorAll({json.dumps(selectors.BTN_WRAP)})"
        ".forEach(function (el) { el.remove(); });\n"
        "Object.defineProperty(document, 'head', "
        "{ get: function () { return null; }, configurable: true });\n"
        "Object.defineProperty(document, 'body', "
        "{ get: function () { return null; }, configurable: true });\n"
        "Object.defineProperty(document, 'readyState', "
        f"{{ get: function () {{ return {json.dumps(ready_state)}; }}, "
        "configurable: true });\n"
        "delete window.__ao3Bridge;\n"
    )
    script = setup + bridge_text
    with contexts.in_webview(driver):
        driver.execute_script(script)


@allure.step("When атомарно сняты тени head/body/readyState, dispatch_dcl={dispatch_dcl}, замерены враппers ДО/ПОСЛЕ (харнесс AT-BUG-067)")
def restore_shadow_and_dispatch_dcl(driver, dispatch_dcl: bool = True) -> dict:
    """AT-BUG-067, критерий готовности п.3 — АТОМАРНО, ОДИН `execute_script`
    (rework-фикс B1, критик attempt 1 test-designer): раздельные вызовы
    Selenium для снятия тени и диспетча DCL оставляют щель, в которую
    физически может встрять тик самоперевзводящейся `setTimeout`-цепочки — её
    фаза задана моментом ПЕРВОГО вызова скрипта, не моментом снятия тени
    харнессом, и харнесс эту фазу не контролирует. Один синхронный скрипт
    делает подряд, без выхода в event loop:

    1. снимает ВСЕ тени (`delete document.head; delete document.body; delete
       document.readyState;`);
    2. СИНХРОННО замеряет `count_rate_button_wraps` (`before`);
    3. если `dispatch_dcl` — диспетчит `document.dispatchEvent(new
       Event('DOMContentLoaded', {bubbles: true, cancelable: true}))` —
       адресует событие зарегистрированному `{once: true}` листенеру напрямую
       (тот же приём, что уже использует `bridge-tap-zone-guard`,
       `browser_steps.dispatch_tap_zone_button_tap` и сиблинги);
    4. СИНХРОННО замеряет `count_rate_button_wraps` и `window.__ao3Bridge`
       (`after`, `bridgeFlag`).

    Возвращает `{"before": int, "after": int, "bridgeFlag": bool}` одним
    результатом. Для TC-196 (путь без DCL-листенера) вызывается с
    `dispatch_dcl=False` — нечего диспатчить, снятие тени + before-замер тем
    же способом."""
    dispatch_stmt = (
        "document.dispatchEvent(new Event('DOMContentLoaded', "
        "{ bubbles: true, cancelable: true }));\n"
        if dispatch_dcl
        else ""
    )
    wrap_selector = json.dumps(selectors.BTN_WRAP)
    script = (
        "delete document.head;\n"
        "delete document.body;\n"
        "delete document.readyState;\n"
        f"var before = document.querySelectorAll({wrap_selector}).length;\n"
        f"{dispatch_stmt}"
        f"var after = document.querySelectorAll({wrap_selector}).length;\n"
        "var bridgeFlag = !!window.__ao3Bridge;\n"
        "return { before: before, after: after, bridgeFlag: bridgeFlag };\n"
    )
    with contexts.in_webview(driver):
        result = driver.execute_script(script)
    return {
        "before": int(result["before"]),
        "after": int(result["after"]),
        "bridgeFlag": bool(result["bridgeFlag"]),
    }


@allure.step("Then прочитан флаг window.__ao3Bridge")
def read_bridge_flag(driver) -> bool:
    """Читает `window.__ao3Bridge` ОДНИМ синхронным `execute_script`, без
    ожидания/опроса — используется сразу ПОСЛЕ `simulate_early_bridge_injection`
    (AT-BUG-067, rework attempt 2, критик: обязательный пункт критерия
    готовности п.2 требует проверить, что флаг falsy СРАЗУ после инжекции
    харнесса, а не только ПОСЛЕ последующего DCL-диспетча, где он ожидается
    True). Возвращает `bool`, не `None`/`undefined` — как и `bridgeFlag` в
    `restore_shadow_and_dispatch_dcl`, приводит через `!!`."""
    with contexts.in_webview(driver):
        return bool(driver.execute_script("return !!window.__ao3Bridge;"))


@allure.step("Then подсчитаны враппers Rate-кнопок ([data-ao3-btn-wrap]) на листинге")
def count_rate_button_wraps(driver) -> int:
    """AT-BUG-067, критерий готовности п.4 — самостоятельный примитив,
    используется и как контрольная точка «ДО When» (до первого вызова
    скрипта), и для отложенного замера TC-195/TC-196 после `>=300мс` ожидания
    (позитивный якорь — урок AT-BUG-029/TC-118: без точки «ДО» негатив/повтор
    неотличим от харнесса, тихо провалившегося затенить состояние)."""
    with contexts.in_webview(driver):
        return int(
            driver.execute_script(
                f"return document.querySelectorAll({json.dumps(selectors.BTN_WRAP)}).length;"
            )
            or 0
        )
