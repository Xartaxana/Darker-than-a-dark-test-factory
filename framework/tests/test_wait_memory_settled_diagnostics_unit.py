"""Device-free юнит-проба диагностики `perf_steps.wait_memory_settled` —
AT-BUG-037 (N2а: строже N2/`settings_steps.assert_filter_profile_count` —
на предикате, падающем на КАЖДОМ опросе, `readings` остаётся пустым и
`except TimeoutError: pass` + `return readings[-1]` давали `IndexError`,
маскируя деградацию среды под баг фреймворка).

Проверяет ОБЕ ветки, как `test_wait_persisted_tab_count_diagnostics_unit.py`
(образец диагностики, AT-BUG-036 attempt 2):
1. Предикат (`adb.total_pss_kb`) читается успешно на каждом опросе, но
   значения никогда не стабилизируются (осциллируют) в пределах таймаута —
   функция обязана вернуть ФАКТИЧЕСКОЕ последнее прочитанное значение (не
   упасть), как и раньше (best-effort settle не регрессировал).
2. `adb.total_pss_kb` падает на КАЖДОМ опросе (имитация зависшего adb,
   AT-BUG-009) — `readings` пуст, падение обязано остаться исходным
   `TimeoutError` С контекстом `wait_for` (`; last error: ...`), не
   `IndexError` на `readings[-1]`.

Не требует устройства/эмулятора: `adb.total_pss_kb` монкипатчится напрямую (в
духе `test_navigate_timeout_unit.py`, AT-BUG-025). Переопределяет
session-scoped autouse-фикстуру `_ensure_app_installed` из `conftest.py` — та
иначе дёрнула бы `adb pm list packages` при сборе тестов.
"""
from __future__ import annotations

import allure
import pytest

from framework.core import adb
from framework.steps import perf_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


@pytest.mark.p2
@allure.id("AT-BUG-037-wait-memory-settled-returns-last-observation-on-non-settling-readings")
@allure.title("Проба: wait_memory_settled(читаемые, но не стабилизирующиеся замеры) возвращает реальное последнее наблюдение, не падает (device-free)")
def test_wait_memory_settled_returns_last_observation_when_never_settles(monkeypatch):
    # Given adb.total_pss_kb() читается успешно на каждом опросе, но значения
    # осциллируют (никогда не сойдутся в пределах stable_ratio) — заведомо
    # непроходимый предикат для короткого таймаута
    values = iter([100_000, 200_000, 100_000, 200_000, 100_000, 200_000, 100_000, 200_000])
    last_value = {"v": None}

    def _fake_total_pss_kb() -> int:
        try:
            last_value["v"] = next(values)
        except StopIteration:
            last_value["v"] = 200_000
        return last_value["v"]

    monkeypatch.setattr(adb, "total_pss_kb", _fake_total_pss_kb)

    # When ждём стабилизации с коротким таймаутом (значения никогда не сойдутся)
    # Then функция НЕ падает (ни AssertionError, ни IndexError) — возвращает
    # ФАКТИЧЕСКОЕ последнее прочитанное значение (best-effort settle сохранён)
    result = perf_steps.wait_memory_settled(timeout=1, stable_ratio=0.05)

    assert result == last_value["v"], (
        f"wait_memory_settled обязан вернуть реальное последнее наблюдение "
        f"({last_value['v']!r}), получили {result!r}"
    )


@pytest.mark.p2
@allure.id("AT-BUG-037-wait-memory-settled-preserves-timeout-context-on-failing-predicate")
@allure.title("Проба: wait_memory_settled(падающий predicate) пробрасывает исходный TimeoutError с контекстом wait_for, не IndexError (device-free)")
def test_wait_memory_settled_preserves_timeout_context_on_failing_predicate(monkeypatch):
    # Given КАЖДЫЙ опрос adb.total_pss_kb() падает (имитация зависшего adb,
    # AT-BUG-009) — наблюдения не будет вообще, readings остаётся пустым
    def _hung_adb() -> int:
        raise TimeoutError("adb ... не ответил за 10s (AT-BUG-009)")

    monkeypatch.setattr(adb, "total_pss_kb", _hung_adb)

    # When ждём стабилизации с коротким таймаутом
    # Then наружу вылетает ИСХОДНЫЙ TimeoutError (не IndexError на пустом
    # readings[-1]) — тип исключения нужен зарегистрированному fail-fast-
    # детектору среды
    with pytest.raises(TimeoutError) as exc_info:
        perf_steps.wait_memory_settled(timeout=1, stable_ratio=0.05)

    message = str(exc_info.value)
    assert "last error" in message, (
        f"причина падения (контекст wait_for) потеряна — 'last error' нет в "
        f"тексте: {message!r}"
    )
    assert "AT-BUG-009" in message, (
        f"env-сигнатура исходного TimeoutError потеряна: {message!r}"
    )
