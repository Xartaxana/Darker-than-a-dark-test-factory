"""Device-free юнит-проба диагностики `wait_persisted_tab_count` — AT-BUG-036,
attempt 2 (critic REJECT на attempt 1: `except TimeoutError: pass` глотал
исходное исключение целиком, вместе с ним — контекст `wait_for`
(`; last error: ...`), на который матчит зарегистрированный fail-fast-
детектор среды, класс AT-BUG-009).

Проверяет ОБЕ ветки:
1. Предикат читает prefs успешно на каждом опросе, но счёт никогда не
   совпадает с ожидаемым (`_read_tabs_prefs_raw` возвращает валидный XML) —
   падение обязано быть `AssertionError` с ФАКТИЧЕСКИМ последним
   наблюдением (не `None`).
2. Предикат падает на КАЖДОМ опросе (`_read_tabs_prefs_raw` кидает
   `TimeoutError` — имитация зависшего adb, AT-BUG-009) — наблюдения нет
   вообще (`holder` пуст), падение обязано остаться `TimeoutError` С
   исходным контекстом `wait_for` (`; last error: ...`), не потерянным
   голым `AssertionError`/None.

Не требует устройства/эмулятора: `_read_tabs_prefs_raw` монкипатчится
напрямую (в духе `test_navigate_timeout_unit.py`, AT-BUG-025). Переопределяет
session-scoped autouse-фикстуру `_ensure_app_installed` из `conftest.py` —
та иначе дёрнула бы `adb pm list packages` при сборе тестов.
"""
from __future__ import annotations

import allure
import pytest

from framework.steps import app_steps

_ONE_TAB_PREFS_XML = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n"
    "<map>\n"
    '    <int name="active_tab_index" value="0" />\n'
    '    <string name="open_tabs_urls">[{&quot;historyEntries&quot;:'
    '[{&quot;scrollY&quot;:0,&quot;url&quot;:&quot;https://archiveofourown.org/&quot;}],'
    '&quot;historyIndex&quot;:0,&quot;scrollY&quot;:0,'
    '&quot;url&quot;:&quot;https://archiveofourown.org/&quot;}]</string>\n'
    "</map>\n"
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


@pytest.mark.p2
@allure.id("AT-BUG-036-wait-persisted-tab-count-shows-last-observation")
@allure.title("Проба: wait_persisted_tab_count(readable prefs, недостижимый count) падает AssertionError с реальным последним наблюдением (device-free)")
def test_wait_persisted_tab_count_shows_last_observation_on_readable_timeout(monkeypatch):
    # Given prefs читаются успешно на каждом опросе (реально 1 вкладка)
    monkeypatch.setattr(app_steps, "_read_tabs_prefs_raw", lambda: _ONE_TAB_PREFS_XML)

    # When ожидаем заведомо недостижимый счёт (999999) с коротким таймаутом
    # Then падение — честный AssertionError с ФАКТИЧЕСКИМ последним
    # наблюдением (1), не None
    with pytest.raises(AssertionError) as exc_info:
        app_steps.wait_persisted_tab_count(999999, timeout=1)

    message = str(exc_info.value)
    assert "последнее наблюдение: 1" in message, (
        f"диагностика обязана нести реальное последнее наблюдение (1), "
        f"получили: {message!r}"
    )
    assert "None" not in message, (
        f"мёртвая диагностика AT-BUG-036 регрессировала — 'None' снова в "
        f"тексте падения: {message!r}"
    )


@pytest.mark.p2
@allure.id("AT-BUG-036-wait-persisted-tab-count-preserves-timeout-context-on-failing-predicate")
@allure.title("Проба: wait_persisted_tab_count(падающий предикат) пробрасывает исходный TimeoutError с контекстом wait_for, не голый AssertionError/None (device-free)")
def test_wait_persisted_tab_count_preserves_timeout_context_on_failing_predicate(monkeypatch):
    # Given КАЖДЫЙ опрос предиката падает (имитация зависшего adb, AT-BUG-009) —
    # наблюдения не будет вообще
    def _hung_adb() -> str:
        raise TimeoutError("adb ... не ответил за 10s (AT-BUG-009)")

    monkeypatch.setattr(app_steps, "_read_tabs_prefs_raw", _hung_adb)

    # When ожидаем любой счёт с коротким таймаутом
    # Then наружу вылетает ИСХОДНЫЙ TimeoutError (не AssertionError) — тип
    # исключения нужен зарегистрированному fail-fast-детектору среды
    # (.claude/agents/*.md, матч по имени TimeoutError/ReadTimeoutError)
    with pytest.raises(TimeoutError) as exc_info:
        app_steps.wait_persisted_tab_count(1, timeout=1)

    message = str(exc_info.value)
    # Контекст wait_for сохранён целиком: и общий message=, и "; last error: ..."
    # с текстом исходного сбоя (AT-BUG-009 сигнатура), не потерян except-ом
    assert "last error" in message, (
        f"причина падения (контекст wait_for) потеряна — 'last error' нет в "
        f"тексте: {message!r}"
    )
    assert "AT-BUG-009" in message, (
        f"env-сигнатура исходного TimeoutError потеряна: {message!r}"
    )
    assert message != "None", "диагностика деградировала до голого None"
