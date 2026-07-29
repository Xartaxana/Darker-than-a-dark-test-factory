"""Device-free перезамер регрессии B1 (критик-вход misc-batch-lead-queue-0729,
attempt 2): `assert_tab_strip_hidden` (`framework/steps/browser_steps.py`)
опрашивает `BrowserScreen.is_tab_strip_visible(timeout=0)` внутри
`assert_holds_for` (budget_s=timeout/interval_s=poll_interval), рассчитывая на
МГНОВЕННЫЙ снимок на каждом опросе. До фикса `framework/core/waits.py:25/33`
(`timeout = timeout or settings.DEFAULT_TIMEOUT`) схлопывал falsy `timeout=0`
в `DEFAULT_TIMEOUT` (20s по умолчанию, `framework/config/settings.py`) — критик
замерил РОВНО ОДИН внешний опрос длиной 20.02s вместо цепочки опросов за весь
бюджет; budget_s/interval_s примитива были мёртвыми параметрами. Фикс:
`timeout if timeout is not None else DEFAULT_TIMEOUT` в обеих точках
`waits.py`.

Два независимых замка (доработка по критик-кругу 2, F1-a/F1-b; редакция 3 —
без импорта screens в tests/, C1 arch_check поймал редакцию 2):

1. **Временной:** `assert_tab_strip_hidden(timeout=2)` укладывается в 6с
   (фикс: ~2.5s; регрессия: ~DEFAULT_TIMEOUT одним внешним опросом).
2. **Структурный (счётчик ВНУТРЕННИХ поллов, направление «мало»):** при
   фиксе каждый внешний опрос несёт `timeout=0` → `WebDriverWait` делает
   1-2 вызова `find_element` и тут же возвращается: суммарно ~8 вызовов за
   бюджет. При регрессии единственный внешний опрос поллит `find_element`
   каждые ~0.4s весь `DEFAULT_TIMEOUT`: >=38 вызовов при DEFAULT>=15
   (замер критик-круга 2: регрессия при дефолте 20 — 51 вызов, при
   AO3_TIMEOUT=5 — 14). Ассерт `<= 12` разделяет надёжно ПОД precondition
   ниже. ВАЖНО: направление «больше одного» (редакция 1) было ЛОЖНЫМ
   разделителем — при регрессии внутренних поллов тоже >1 (51), пойман
   критик-кругом 2 (F1-a).

Оба замка держатся на precondition `DEFAULT_TIMEOUT >= 15` (F1-b):
`DEFAULT_TIMEOUT` регулируется env `AO3_TIMEOUT`; при AO3_TIMEOUT=5
регрессия давала бы 5.2s < 6.0 и 14 поллов — оба ассерта слепнут
(замер критик-круга 2), поэтому предпосылка закреплена явно.

Fake driver — тот же приём, что `test_top_chrome_wait_unit.py`
(`current_context = contexts.NATIVE`, `BaseScreen.__init__` не переключает
контекст) — `find_element` считает вызовы и всегда поднимает
`NoSuchElementException` (TabStrip физически отсутствует — сценарий
`assert_tab_strip_hidden`, полоса скрыта весь бюджет)."""
from __future__ import annotations

import time

import allure
import pytest
from selenium.common.exceptions import NoSuchElementException

from framework.config import settings
from framework.core import contexts
from framework.steps import browser_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто локальная,
    устройство не трогаем (тот же приём, что test_top_chrome_wait_unit.py)."""
    yield


class _FakeDriverNoTabStrip:
    """TabStrip физически отсутствует: `find_element` для ЛЮБОГО локатора
    считает вызов и поднимает `NoSuchElementException` — `is_present`
    (через `wait_until`/`WebDriverWait`, ignored_exceptions включает
    `NoSuchElementException`) добросовестно вернёт `False`."""

    current_context = contexts.NATIVE

    def __init__(self) -> None:
        self.find_element_calls = 0

    def find_element(self, *args, **kwargs):
        self.find_element_calls += 1
        raise NoSuchElementException("TabStrip not present (fake driver)")


@pytest.mark.p2
@allure.id("B1-tab-strip-hidden-timeout0-not-20s-regression")
@allure.title("Регрессия B1: assert_tab_strip_hidden(timeout=2) — единицы секунд и МАЛО внутренних поллов")
def test_assert_tab_strip_hidden_does_not_regress_to_default_timeout():
    # Precondition обоих замков (F1-b): пороги 6.0s и 12 поллов различают
    # фикс от регрессии только пока DEFAULT_TIMEOUT заметно выше бюджета.
    assert settings.DEFAULT_TIMEOUT >= 15, (
        f"DEFAULT_TIMEOUT={settings.DEFAULT_TIMEOUT} (env AO3_TIMEOUT?) ниже 15 — "
        "оба ассерта этой пробы теряют разделяющую силу; подними AO3_TIMEOUT "
        "или пересмотри пороги вместе с этой precondition"
    )

    driver = _FakeDriverNoTabStrip()

    start = time.time()
    # When/Then — TabStrip отсутствует ВСЕГДА -> негатив держится весь бюджет,
    # функция обязана вернуться МОЛЧА (без AssertionError).
    browser_steps.assert_tab_strip_hidden(driver, timeout=2, poll_interval=0.3)
    elapsed = time.time() - start

    assert elapsed < 6.0, (
        f"assert_tab_strip_hidden(timeout=2) заняла {elapsed:.2f}s — похоже на "
        "регрессию B1 (falsy timeout=0 схлопывается в DEFAULT_TIMEOUT одним "
        "внешним опросом вместо контроля всего бюджета)"
    )
    assert driver.find_element_calls <= 12, (
        f"find_element вызван {driver.find_element_calls} раз за budget_s=2 — "
        "похоже на регрессию B1: единственный внешний опрос поллит WebDriverWait "
        "весь DEFAULT_TIMEOUT (замер: фикс=8, регрессия при дефолте 20 = 51; "
        "порог 12 валиден под precondition DEFAULT_TIMEOUT >= 15, где регрессия "
        "даёт >= ~38)"
    )
