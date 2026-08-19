"""Канарейка нулевого layout (B4, `docs/tasks/p2-pyramid-bridge.md` Р3): jsdom
НЕ считает layout — `getBoundingClientRect()`/`scrollHeight`/`scrollY` любого
узла остаются 0 независимо от реальной разметки/CSS.

**Инверсия формулировки (Б2, критик-раунд 2, `p2-n5-bridge-harness` accepted
2026-08-19T11:42:52 — живой зонд критика подтвердил: 1 scroll -> `fetch
?page=2`):** layout-гейтированные ветки bridge устроены как GUARD РАННЕГО
ВЫХОДА («геометрия ещё не достигла порога -> `return`, не действуй») —
infinite-scroll append-триггер `if (ol.getBoundingClientRect().bottom >
window.innerHeight + SCROLL_MARGIN) return;` (`ao3_bridge.js:607`) и auto-READ
`if (lastContent.getBoundingClientRect().bottom > window.innerHeight)
return;` (`ao3_bridge.js:1220`) — в ОБОИХ случаях левая часть в jsdom
всегда 0, правая — положительное число, значит `0 > число` = `false` ВСЕГДА:
guard НИКОГДА не берёт ветку `return`. Это делает ЗАЩИЩЁННЫЙ вызов
(`fetchAndAppend()` / `onWorkFinished`) FAIL-OPEN — ДОСТИЖИМЫМ на ЛЮБОМ
scroll-событии в jsdom, а НЕ недостижимым, как утверждала предыдущая
формулировка этого файла («append-гейт недостижим») — это было ровно
наоборот: guard недостижим (никогда не возвращает раньше времени), а
защищаемая им ветка, напротив, ВСЕГДА проходима. Поэтому такие ветки
остаются L3 и НЕ ассертятся НИ ОДНИМ тестом этого пакета (запрет — Р3
«Fail-open границы», проверяется чеком B10 F1 на уровне test-reviewer, вне
скоупа этого харнесса): assert «ветка НЕ сработала» здесь был бы тавтологией
среды (jsdom всегда её пропускает), а не проверкой продукта.

Если jsdom ОДНАЖДЫ начнёт считать реальный layout (обновление версии,
`pretendToBeVisual` меняет поведение) — тесты НИЖЕ упадут первыми, и границу
B4 нужно будет пересмотреть осознанно (не тихий дрейф)."""
from __future__ import annotations

import json
import re

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data.works import LOVED


def _extract_scroll_margin(bridge_js_text: str) -> int:
    """Читает `SCROLL_MARGIN` ИЗ ИСХОДНИКА бриджа, а не перепечатывает его
    литералом в тест (не-блокер 4, критик-раунд 2): перепечатанный литерал
    молча рассинхронизируется с `ao3_bridge.js` при правке константы —
    regex-экстракция вместо этого падает ЯВНО, если константа переименована
    или удалена, вместо того чтобы молча сверять гейт со СТАРЫМ значением."""
    match = re.search(r"var\s+SCROLL_MARGIN\s*=\s*(\d+)", bridge_js_text)
    if not match:
        raise AssertionError(
            "SCROLL_MARGIN не найден в ao3_bridge.js -- константа переименована "
            "или удалена, красная проба B4 больше не сверяет РЕАЛЬНОЕ выражение "
            "гейта (docs/tasks/p2-pyramid-bridge.md, не-блокер 4 критик-раунда 2)"
        )
    return int(match.group(1))


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-layout-canary-bounding-client-rect-is-all-zero")
@allure.title("L2 bridge, канарейка B4: getBoundingClientRect() любого узла — нулевой")
def test_bounding_client_rect_is_all_zero(bridge_call):
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "rect",
                "type": "eval",
                "code": "JSON.stringify(document.querySelector('li[id^=\"work_\"]').getBoundingClientRect())",
            },
        ],
    })
    rect = json.loads(response["results"]["rect"])
    assert rect == {"x": 0, "y": 0, "top": 0, "left": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-layout-canary-document-scroll-height-is-zero")
@allure.title("L2 bridge, канарейка B4: scrollHeight document/body — нулевой")
def test_document_scroll_height_is_zero(bridge_call):
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {"id": "scrollHeight", "type": "eval", "code": "document.documentElement.scrollHeight"},
            {"id": "bodyScrollHeight", "type": "eval", "code": "document.body.scrollHeight"},
        ],
    })
    assert response["results"]["scrollHeight"] == 0
    assert response["results"]["bodyScrollHeight"] == 0


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-layout-canary-infinite-scroll-guard-is-fail-open-not-vacuous")
@allure.title(
    "L2 bridge, красная проба B4: scroll-гейт всегда false => append-ветка ВСЕГДА "
    "проходима (fail-open), проверка не тавтологична"
)
def test_infinite_scroll_append_guard_is_always_false_making_append_branch_fail_open(bridge_call, bridge_js_path):
    """Красная проба границы B4 (формулировка инвертирована Б2, критик-раунд
    2 — прежнее имя/id/title утверждали «append-гейт недостижим», что было
    ЛОЖНО наоборот, см. докстринг модуля): доказывает, что guard РАННЕГО
    ВЫХОДА `ol.getBoundingClientRect().bottom > window.innerHeight +
    SCROLL_MARGIN` (`ao3_bridge.js:607`, `SCROLL_MARGIN` извлекается ИЗ
    ИСХОДНИКА бриджа через `_extract_scroll_margin`, не перепечатывается
    литералом — не-блокер 4) читается КАК ЕСТЬ (не тавтологично `false`) —
    сначала на РЕАЛЬНОМ jsdom-нулевом `getBoundingClientRect()` guard `false`
    (значит: `return` НЕ берётся, `fetchAndAppend()` ДОСТИЖИМ на scroll —
    fail-open), ЗАТЕМ ТА ЖЕ строка выражения (не переписанная копия) с
    подменённым `Element.prototype.getBoundingClientRect`, возвращающим
    заведомо большой `bottom`, — `true` (guard СРАБОТАЛ бы, `return`,
    `fetchAndAppend()` НЕ вызван бы). Переключение результата мутацией
    доказывает: `gateBeforeMutation=False` — следствие РЕАЛЬНОГО поведения
    jsdom (fail-open граница B4), не случайность формы assert'а. Ассерт на
    самой защищённой ветке (`fetchAndAppend()` — реальный `fetch`/DOM-append)
    остаётся ЗАПРЕЩЁН (см. докстринг модуля) — эта проба ограничена
    ВЫРАЖЕНИЕМ guard'а, не результатом append."""
    bridge_js_text = bridge_js_path.read_text(encoding="utf-8")
    scroll_margin = _extract_scroll_margin(bridge_js_text)
    response = bridge_call({
        "html": rb.render_listing_html([LOVED]),
        "url": "https://archiveofourown.org/works",
        "actions": [
            {
                "id": "gateBeforeMutation",
                "type": "eval",
                "code": (
                    "var ol = document.querySelector('ol.work.index.group'); "
                    f"ol.getBoundingClientRect().bottom > (window.innerHeight + {scroll_margin})"
                ),
            },
            {
                "id": "gateAfterMutation",
                "type": "eval",
                "code": (
                    "window.Element.prototype.getBoundingClientRect = function () "
                    "{ return { bottom: 999999, top: 0, left: 0, right: 0, height: 999999, width: 0, x: 0, y: 0 }; }; "
                    "var ol = document.querySelector('ol.work.index.group'); "
                    f"ol.getBoundingClientRect().bottom > (window.innerHeight + {scroll_margin})"
                ),
            },
        ],
    })
    assert response["results"]["gateBeforeMutation"] is False, (
        "guard должен быть false в jsdom (fail-open) -- append-ветка достижима на scroll"
    )
    assert response["results"]["gateAfterMutation"] is True, (
        "guard должен переключаться в true при реальной геометрии -- иначе проверка "
        "тавтологична и не зависит от РЕАЛЬНОГО выражения гейта"
    )
