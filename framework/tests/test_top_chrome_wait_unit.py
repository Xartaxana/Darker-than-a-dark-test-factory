"""Device-free юнит-проба settle-поллинга `assert_top_chrome_darkened`/
`assert_top_chrome_restored` (TC-058, ревью test-reviewer 2026-07-18,
замечание «чек-лист п.5 — flake-устойчивость»).

До правки обе функции читали `top_chrome_avg_luma()` ОДНОРАЗОВО сразу после
`toggle_fullscreen` — устойчивость к анимированному reflow (hide/show
systemBars + resize WebView) держалась ПОБОЧНО на таймауте `is_present("GOT
IT", timeout=3)` чужого хелпера (`_dismiss_fullscreen_system_hint`). Эта проба
доказывает, что теперь обёртка РЕАЛЬНО ОПРАШИВАЕТ значение до пересечения
порога (не маскирует любой исход коротким `sleep`) — и падает явным
`TimeoutException`, когда порог не достигается никогда (красная проба).

Монки-патчит `BrowserScreen.top_chrome_avg_luma` ПО СТРОКОВОМУ пути (тот же
приём, что `test_subprocess_timeout_unit.py`/`test_replay_ca_check_unit.py`
патчат `subprocess.run`) — не требует устройства/эмулятора. Патч через строку,
а не статический `from framework.screens... import BrowserScreen`: слой
tests/ не имеет права импортировать `framework.screens.*` (docs/08 C1,
`scripts/arch_check.py::FORBIDDEN_IMPORT_PREFIXES`) — эта проба монки-патчит
локатор/пиксельный слой ИЗВНЕ, не читая его напрямую. Переопределяет
session-scoped autouse-фикстуру `_ensure_app_installed` из `conftest.py`, как
и остальные device-free пробы этого пакета.
"""
from __future__ import annotations

import allure
import pytest
from selenium.common.exceptions import TimeoutException

from framework.core import contexts
from framework.steps import browser_steps

_TOP_CHROME_LUMA_TARGET = "framework.screens.browser_screen.BrowserScreen.top_chrome_avg_luma"


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


class _FakeDriver:
    """Минимальный driver-дубль: `WebDriverWait` дёргает `condition(self._driver)`
    и передаёт его же в `BrowserScreen(d)` — сам объект внутри luma-заглушки не
    используется (только `BaseScreen.__init__` проверяет `current_context`, чтобы
    решить, переключаться ли в NATIVE_APP)."""

    current_context = contexts.NATIVE


@pytest.mark.p2
@allure.id("TC-058-top-chrome-darkened-polls-not-one-shot")
@allure.title("Проба: assert_top_chrome_darkened ОПРАШИВАЕТ luma до порога, не читает один раз (device-free)")
def test_assert_top_chrome_darkened_polls_until_threshold(monkeypatch):
    # Given первые два опроса luma ЕЩЁ выше порога потемнения (reflow не осел —
    # baseline=100, ratio=0.5 -> порог=50); одноразовое чтение сразу после toggle
    # поймало бы именно первое значение (90.0) и упало бы ложноотрицательно.
    # Третий опрос уже отражает осевшую тёмную полосу (40.0 < 50).
    values = iter([90.0, 85.0, 40.0])
    monkeypatch.setattr(_TOP_CHROME_LUMA_TARGET, lambda self: next(values))

    # When/Then обёртка не падает — дожидается порога за НЕСКОЛЬКО опросов
    # (одноразовая реализация упала бы здесь на первом же значении 90.0)
    browser_steps.assert_top_chrome_darkened(_FakeDriver(), baseline=100.0, timeout=3)


@pytest.mark.p2
@allure.id("TC-058-top-chrome-restored-polls-not-one-shot")
@allure.title("Проба: assert_top_chrome_restored ОПРАШИВАЕТ luma до порога, не читает один раз (device-free)")
def test_assert_top_chrome_restored_polls_until_threshold(monkeypatch):
    # Given первые два опроса ЕЩЁ ниже порога восстановления (baseline=200,
    # ratio=0.5 -> порог=100); третий опрос уже отражает осевшую светлую полосу.
    values = iter([70.0, 90.0, 150.0])
    monkeypatch.setattr(_TOP_CHROME_LUMA_TARGET, lambda self: next(values))

    browser_steps.assert_top_chrome_restored(_FakeDriver(), baseline=200.0, timeout=3)


@pytest.mark.p2
@allure.id("TC-058-top-chrome-darkened-times-out")
@allure.title("Красная проба: assert_top_chrome_darkened падает TimeoutException, если порог НИКОГДА не достигается (device-free)")
def test_assert_top_chrome_darkened_times_out_when_never_dark(monkeypatch):
    # Given luma всегда выше порога (симулирует зависший/не сработавший toggle) —
    # доказываем, что обёртка не маскирует ЛЮБОЙ исход коротким sleep, а реально
    # проверяет условие и падает явным таймаутом, когда оно не выполняется.
    monkeypatch.setattr(_TOP_CHROME_LUMA_TARGET, lambda self: 90.0)

    with pytest.raises(TimeoutException):
        browser_steps.assert_top_chrome_darkened(_FakeDriver(), baseline=100.0, timeout=1)


@pytest.mark.p2
@allure.id("TC-058-top-chrome-restored-times-out")
@allure.title("Красная проба: assert_top_chrome_restored падает TimeoutException, если порог НИКОГДА не достигается (device-free)")
def test_assert_top_chrome_restored_times_out_when_never_light(monkeypatch):
    # Given luma всегда ниже порога восстановления (TabStrip так и не вернулся)
    monkeypatch.setattr(_TOP_CHROME_LUMA_TARGET, lambda self: 10.0)

    with pytest.raises(TimeoutException):
        browser_steps.assert_top_chrome_restored(_FakeDriver(), baseline=200.0, timeout=1)
