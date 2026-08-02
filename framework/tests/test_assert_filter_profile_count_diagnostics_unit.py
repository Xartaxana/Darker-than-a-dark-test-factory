"""Device-free юнит-проба диагностики `settings_steps.assert_filter_profile_count`
— AT-BUG-037 (N2: образец, откуда приём `except TimeoutError: pass` был
скопирован в `app_steps.wait_persisted_tab_count` при attempt 1 AT-BUG-036;
сам `settings_steps` не был исправлен фиксом AT-BUG-036 attempt 2).

Проверяет ОБЕ ветки, как `test_wait_persisted_tab_count_diagnostics_unit.py`
(образец диагностики, AT-BUG-036 attempt 2):
1. Предикат читает счётчик успешно на каждом опросе, но значение никогда не
   совпадает с ожидаемым — падение обязано быть `AssertionError` с
   ФАКТИЧЕСКИМ последним наблюдением (не `None`).
2. Предикат падает на КАЖДОМ опросе (имитация зависшего driver-вызова) —
   наблюдения нет вообще (`last["value"]` остался `None`), падение обязано
   остаться исходным `TimeoutError` С контекстом `wait_for`
   (`; last error: ...`), не потерянным голым `AssertionError`/`None`.

Не требует устройства/эмулятора: `SettingsScreen` монкипатчится фейком (в духе
`test_navigate_timeout_unit.py`, AT-BUG-025). Переопределяет session-scoped
autouse-фикстуру `_ensure_app_installed` из `conftest.py` — та иначе дёрнула бы
`adb pm list packages` при сборе тестов.
"""
from __future__ import annotations

import allure
import pytest

from framework.steps import settings_steps


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py (см. докстринг модуля) — эта
    проба чисто локальная, устройство не трогаем."""
    yield


class _FakeSettingsScreenReadable:
    """Фейк SettingsScreen, читающий счётчик успешно на каждом опросе, но
    всегда возвращающий одно и то же (недостижимое ожидаемому) значение."""

    def __init__(self, driver):
        del driver

    def count_filter_profile_occurrences(self, name: str) -> int:
        del name
        return 1


class _FakeSettingsScreenHung:
    """Фейк SettingsScreen: КАЖДЫЙ опрос падает (имитация зависшего
    driver-вызова, класс AT-BUG-009)."""

    def __init__(self, driver):
        del driver

    def count_filter_profile_occurrences(self, name: str) -> int:
        del name
        raise TimeoutError("driver ... не ответил за 10s (AT-BUG-009)")


@pytest.mark.p2
@allure.id("AT-BUG-037-assert-filter-profile-count-shows-last-observation")
@allure.title("Проба: assert_filter_profile_count(readable, недостижимый count) падает AssertionError с реальным последним наблюдением (device-free)")
def test_assert_filter_profile_count_shows_last_observation_on_readable_timeout(monkeypatch):
    # Given счётчик читается успешно на каждом опросе (реально 1 строка), но
    # ожидаем заведомо недостижимое значение
    monkeypatch.setattr(settings_steps, "SettingsScreen", _FakeSettingsScreenReadable)

    # When ждём недостижимый count с коротким таймаутом
    # Then падение — честный AssertionError с ФАКТИЧЕСКИМ последним
    # наблюдением (1), не None
    with pytest.raises(AssertionError) as exc_info:
        settings_steps.assert_filter_profile_count(driver=object(), name="Profile A", expected=999, timeout=1)

    message = str(exc_info.value)
    assert "реально 1" in message, (
        f"диагностика обязана нести реальное последнее наблюдение (1), "
        f"получили: {message!r}"
    )
    assert "None" not in message, (
        f"мёртвая диагностика (класс AT-BUG-036/N2) регрессировала — 'None' "
        f"снова в тексте падения: {message!r}"
    )


@pytest.mark.p2
@allure.id("AT-BUG-037-assert-filter-profile-count-preserves-timeout-context-on-failing-predicate")
@allure.title("Проба: assert_filter_profile_count(падающий предикат) пробрасывает исходный TimeoutError с контекстом wait_for, не голый AssertionError/None (device-free)")
def test_assert_filter_profile_count_preserves_timeout_context_on_failing_predicate(monkeypatch):
    # Given КАЖДЫЙ опрос предиката падает (имитация зависшего driver-вызова,
    # AT-BUG-009) — наблюдения не будет вообще
    monkeypatch.setattr(settings_steps, "SettingsScreen", _FakeSettingsScreenHung)

    # When ожидаем любой count с коротким таймаутом
    # Then наружу вылетает ИСХОДНЫЙ TimeoutError (не AssertionError) — тип
    # исключения нужен зарегистрированному fail-fast-детектору среды
    with pytest.raises(TimeoutError) as exc_info:
        settings_steps.assert_filter_profile_count(driver=object(), name="Profile A", expected=1, timeout=1)

    message = str(exc_info.value)
    # Контекст wait_for сохранён целиком: и общий message=, и "; last error:
    # ..." с текстом исходного сбоя (AT-BUG-009 сигнатура), не потерян except-ом
    assert "last error" in message, (
        f"причина падения (контекст wait_for) потеряна — 'last error' нет в "
        f"тексте: {message!r}"
    )
    assert "AT-BUG-009" in message, (
        f"env-сигнатура исходного TimeoutError потеряна: {message!r}"
    )
    assert message != "None", "диагностика деградировала до голого None"
