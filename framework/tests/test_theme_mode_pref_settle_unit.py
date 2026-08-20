"""Device-free различающий юнит-тест AT-BUG-086 — `settings_steps.
assert_theme_mode_pref`/`assert_auto_apply_filter_pref`/
`assert_font_size_step_pref` читали `ao3_settings.xml` через ОДИН
`adb.run_as` СРАЗУ после UI-действия, гонясь с асинхронным
`SharedPreferences.Editor.apply()` (см. `bugs/AT-BUG-086.md`, докстринг
`settings_steps._poll_settings_prefs`). Тот же приём, что
`test_settings_ratings_fail_closed_unit.py` (AT-BUG-081) — мокает
`framework.core.adb.run_as` НА УРОВНЕ МОДУЛЯ последовательностью снимков,
проверяет РЕАЛЬНЫЙ код трёх хелперов, не подмену самих хелперов.

Красная проба (пункт 3 чек-листа AT-BUG-086): `test_pre_fix_single_read_
would_have_failed_on_recorded_race` воспроизводит РЕАЛЬНЫЙ pre-fix код
(`out = adb.run_as(...); assert needle in out`, байтовая копия того, что
было в `settings_steps.py` строки 609-611/620-624/629-631 ДО этого фикса) на
ТОЙ ЖЕ записанной последовательности снимков, что различающий тест ниже
использует для доказательства, что поллинг реально чинит гонку — pre-fix
код падает на первом (устаревшем) снимке, fix проходит, опросив дальше.

Не требует устройства/эмулятора — переопределяет session-scoped autouse
`_ensure_app_installed` (conftest.py), тот же приём, что
`test_settings_ratings_fail_closed_unit.py`."""
from __future__ import annotations

import allure
import pytest

from framework.core import adb
from framework.steps import settings_steps as ss


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


@pytest.fixture(autouse=True)
def _fast_settings_prefs_poll(monkeypatch):
    """AT-BUG-086: укорачивает поллинг-бюджет (та же логика, другая скорость
    ЭТОГО device-free юнит-теста) — не связано с фиксом самим по себе."""
    monkeypatch.setattr(ss.settings, "SETTINGS_PREFS_POLL_TIMEOUT", 0.05)
    monkeypatch.setattr(ss.settings, "SETTINGS_PREFS_POLL_INTERVAL", 0.01)


def _fake_run_as_sequence(monkeypatch, outputs: list[str]) -> list[str]:
    calls: list[str] = []
    it = iter(outputs)

    def _fake_run_as(cmd: str) -> str:
        calls.append(cmd)
        try:
            return next(it)
        except StopIteration:
            return outputs[-1]

    monkeypatch.setattr(adb, "run_as", _fake_run_as)
    return calls


_STALE_LIGHT = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <string name="theme_mode">LIGHT</string>\n</map>\n'
)
_SETTLED_SYSTEM = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <string name="theme_mode">SYSTEM</string>\n</map>\n'
)
_STALE_AUTO_APPLY_TRUE = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <boolean name="auto_apply_filter" value="true" />\n</map>\n'
)
_SETTLED_AUTO_APPLY_FALSE = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <boolean name="auto_apply_filter" value="false" />\n</map>\n'
)
_STALE_FONT_STEP_0 = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <int name="font_size_step" value="0" />\n</map>\n'
)
_SETTLED_FONT_STEP_1 = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <int name="font_size_step" value="1" />\n</map>\n'
)


@pytest.mark.p1
@allure.id("AT-BUG-086-theme-mode-pref-polls-until-settled")
@allure.title("assert_theme_mode_pref ОПРАШИВАЕТ до совпадения theme_mode, не падает на первом устаревшем снимке")
def test_assert_theme_mode_pref_polls_until_settled(monkeypatch):
    """Симулирует РЕАЛЬНУЮ гонку: первые 2 чтения ещё видят стухшее LIGHT
    (`SharedPreferences.apply()` ещё не отфлашил SYSTEM-запись), 3-е чтение
    видит SYSTEM. Pre-fix код (`adb.run_as(...)`, ОДИН вызов) получил бы
    ПЕРВЫЙ элемент и упал бы немедленно, ни разу не увидев settled-снимок —
    этот тест проходит СЕЙЧАС (поллинг реально повторяет чтение), но упал бы,
    вернись код к одноразовому чтению."""
    calls = _fake_run_as_sequence(monkeypatch, [_STALE_LIGHT, _STALE_LIGHT, _SETTLED_SYSTEM])
    ss.assert_theme_mode_pref("SYSTEM")  # НЕ должно поднять AssertionError
    assert len(calls) == 3, f"ожидали ровно 3 попытки чтения (2 «в процессе» + 1 settled), реально {len(calls)}"


@pytest.mark.p1
@allure.id("AT-BUG-086-theme-mode-pref-timeout-still-raises")
@allure.title("assert_theme_mode_pref всё ещё падает, если theme_mode НЕ сошёлся до конца бюджета (не бесконечный retry)")
def test_assert_theme_mode_pref_raises_after_budget_exhausted(monkeypatch):
    """Гонка — не оправдание бесконечно молчать при РЕАЛЬНОМ дефекте (значение
    так и не стало ожидаемым за весь бюджет) — опрос обязан завершиться
    честным `AssertionError` с последним фактическим значением, не тихим pass."""
    monkeypatch.setattr(adb, "run_as", lambda cmd: _STALE_LIGHT)
    with pytest.raises(AssertionError, match="LIGHT"):
        ss.assert_theme_mode_pref("SYSTEM")


@pytest.mark.p1
@allure.id("AT-BUG-086-auto-apply-filter-pref-polls-until-settled")
@allure.title("assert_auto_apply_filter_pref (D-0043 сиблинг) ОПРАШИВАЕТ до совпадения, не падает на первом устаревшем снимке")
def test_assert_auto_apply_filter_pref_polls_until_settled(monkeypatch):
    calls = _fake_run_as_sequence(
        monkeypatch, [_STALE_AUTO_APPLY_TRUE, _STALE_AUTO_APPLY_TRUE, _SETTLED_AUTO_APPLY_FALSE]
    )
    ss.assert_auto_apply_filter_pref(False)
    assert len(calls) == 3, f"ожидали ровно 3 попытки чтения, реально {len(calls)}"


@pytest.mark.p1
@allure.id("AT-BUG-086-font-size-step-pref-polls-until-settled")
@allure.title("assert_font_size_step_pref (D-0043 сиблинг) ОПРАШИВАЕТ до совпадения, не падает на первом устаревшем снимке")
def test_assert_font_size_step_pref_polls_until_settled(monkeypatch):
    calls = _fake_run_as_sequence(monkeypatch, [_STALE_FONT_STEP_0, _STALE_FONT_STEP_0, _SETTLED_FONT_STEP_1])
    ss.assert_font_size_step_pref(1)
    assert len(calls) == 3, f"ожидали ровно 3 попытки чтения, реально {len(calls)}"


def _pre_fix_assert_theme_mode_pref(mode: str) -> None:
    """Байтовая копия РЕАЛЬНОГО pre-fix кода `assert_theme_mode_pref`
    (`settings_steps.py:609-611` ДО AT-BUG-086, сверено `git show
    HEAD:framework/steps/settings_steps.py`) — единственное отличие от
    исходника: не завёрнута в `@allure.step`, что не влияет на логику."""
    out = adb.run_as("cat shared_prefs/ao3_settings.xml")
    assert f'name="theme_mode">{mode}<' in out, f"theme_mode != {mode} в SharedPreferences: {out}"


@pytest.mark.p1
@allure.id("AT-BUG-086-red-probe-pre-fix-code-fails-on-recorded-race")
@allure.title("Красная проба: pre-fix однократное чтение падает на ТОЙ ЖЕ записанной гонке, где fix-поллинг проходит")
def test_pre_fix_single_read_would_have_failed_on_recorded_race(monkeypatch):
    """Доказывает, что мок-сценарий `test_assert_theme_mode_pref_polls_until_
    settled` реально различает старый/новый код (не тривиален, симметрично
    `test_library_tab_settle_unit.py`'s red-probe): та же последовательность
    снимков (`_STALE_LIGHT, _STALE_LIGHT, _SETTLED_SYSTEM`), что fix-тест выше
    проходит, здесь скармливается РЕАЛЬНОМУ pre-fix коду — который читает
    ОДИН РАЗ, получает `_STALE_LIGHT` (первый элемент) и падает."""
    _fake_run_as_sequence(monkeypatch, [_STALE_LIGHT, _STALE_LIGHT, _SETTLED_SYSTEM])
    with pytest.raises(AssertionError, match="LIGHT"):
        _pre_fix_assert_theme_mode_pref("SYSTEM")
