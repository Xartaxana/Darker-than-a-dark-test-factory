"""Device-free различающий юнит-тест AT-BUG-086 — `settings_steps.
assert_theme_mode_pref`/`assert_auto_apply_filter_pref`/
`assert_font_size_step_pref` читали `ao3_settings.xml` через ОДИН
`adb.run_as` СРАЗУ после UI-действия, гонясь с асинхронным
`SharedPreferences.Editor.apply()` (см. `bugs/AT-BUG-086.md`, докстринг
`settings_steps._poll_settings_prefs`). Тот же приём, что
`test_settings_ratings_fail_closed_unit.py` (AT-BUG-081) — мокает
`framework.core.adb.run_as_file_or_raise` НА УРОВНЕ МОДУЛЯ
последовательностью снимков, проверяет РЕАЛЬНЫЙ код трёх хелперов, не
подмену самих хелперов.

AT-BUG-088: `_poll_settings_prefs` переведён с голого `adb.run_as` на
`adb.run_as_file_or_raise` (по образцу `app_steps._read_tabs_prefs_raw`,
AT-BUG-055) — мок ниже переехал вместе с ним (`_fake_run_as_file_or_raise_
sequence`, мокает `adb.run_as_file_or_raise`, игнорирует `path`/`timeout`
аргументы). `_fake_run_as_sequence` (мокает СТАРЫЙ `adb.run_as`) остаётся
ТОЛЬКО для красной пробы ниже — та воспроизводит байтовую копию pre-fix
кода, который вызывал именно `adb.run_as` напрямую, и не имеет отношения к
текущей реализации `_poll_settings_prefs`.

Красная проба (пункт 3 чек-листа AT-BUG-086): `test_pre_fix_single_read_
would_have_failed_on_recorded_race` воспроизводит РЕАЛЬНЫЙ pre-fix код
(`out = adb.run_as(...); assert needle in out`, байтовая копия того, что
было в `settings_steps.py` строки 609-611/620-624/629-631 ДО этого фикса) на
ТОЙ ЖЕ записанной последовательности снимков, что различающий тест ниже
использует для доказательства, что поллинг реально чинит гонку — pre-fix
код падает на первом (устаревшем) снимке, fix проходит, опросив дальше.

`test_assert_theme_mode_pref_adb_failure_raises_distinct_runtime_error`
(AT-BUG-088): различающий тест для ВТОРОГО класса гонки — отказ adb-
транспорта (rc!=0/exception) обязан дать `RuntimeError`, ОТДЕЛЬНЫЙ от
`AssertionError` settle-таймаута по значению (см. `bugs/AT-BUG-088.md`).

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
    """Мокает СТАРЫЙ `adb.run_as` — используется ТОЛЬКО красной пробой ниже
    (`_pre_fix_assert_theme_mode_pref`, байтовая копия pre-fix кода, которая
    вызывает именно `adb.run_as` напрямую); текущая реализация
    `_poll_settings_prefs` (AT-BUG-088) через эту функцию НЕ проходит."""
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


def _fake_run_as_file_or_raise_sequence(monkeypatch, outputs: list) -> list[str]:
    """AT-BUG-088: мокает `adb.run_as_file_or_raise` (текущий читатель
    `_poll_settings_prefs`) — элемент списка либо строка (успешное чтение),
    либо `Exception`-инстанс (поднимается вместо возврата, симулирует
    отвалившийся adb/run-as — `run_as_file_or_raise` сам кидает `RuntimeError`
    на неоднозначном исходе, см. `framework/core/adb.py`)."""
    calls: list[str] = []
    it = iter(outputs)

    def _fake(path: str, timeout: float = 0) -> str:
        calls.append(path)
        try:
            item = next(it)
        except StopIteration:
            item = outputs[-1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(adb, "run_as_file_or_raise", _fake)
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
    calls = _fake_run_as_file_or_raise_sequence(monkeypatch, [_STALE_LIGHT, _STALE_LIGHT, _SETTLED_SYSTEM])
    ss.assert_theme_mode_pref("SYSTEM")  # НЕ должно поднять AssertionError
    assert len(calls) == 3, f"ожидали ровно 3 попытки чтения (2 «в процессе» + 1 settled), реально {len(calls)}"


@pytest.mark.p1
@allure.id("AT-BUG-086-theme-mode-pref-timeout-still-raises")
@allure.title("assert_theme_mode_pref всё ещё падает, если theme_mode НЕ сошёлся до конца бюджета (не бесконечный retry)")
def test_assert_theme_mode_pref_raises_after_budget_exhausted(monkeypatch):
    """Гонка — не оправдание бесконечно молчать при РЕАЛЬНОМ дефекте (значение
    так и не стало ожидаемым за весь бюджет) — опрос обязан завершиться
    честным `AssertionError` с последним фактическим значением, не тихим pass."""
    _fake_run_as_file_or_raise_sequence(monkeypatch, [_STALE_LIGHT])
    with pytest.raises(AssertionError, match="LIGHT"):
        ss.assert_theme_mode_pref("SYSTEM")


@pytest.mark.p1
@allure.id("AT-BUG-086-auto-apply-filter-pref-polls-until-settled")
@allure.title("assert_auto_apply_filter_pref (D-0043 сиблинг) ОПРАШИВАЕТ до совпадения, не падает на первом устаревшем снимке")
def test_assert_auto_apply_filter_pref_polls_until_settled(monkeypatch):
    calls = _fake_run_as_file_or_raise_sequence(
        monkeypatch, [_STALE_AUTO_APPLY_TRUE, _STALE_AUTO_APPLY_TRUE, _SETTLED_AUTO_APPLY_FALSE]
    )
    ss.assert_auto_apply_filter_pref(False)
    assert len(calls) == 3, f"ожидали ровно 3 попытки чтения, реально {len(calls)}"


@pytest.mark.p1
@allure.id("AT-BUG-086-font-size-step-pref-polls-until-settled")
@allure.title("assert_font_size_step_pref (D-0043 сиблинг) ОПРАШИВАЕТ до совпадения, не падает на первом устаревшем снимке")
def test_assert_font_size_step_pref_polls_until_settled(monkeypatch):
    calls = _fake_run_as_file_or_raise_sequence(
        monkeypatch, [_STALE_FONT_STEP_0, _STALE_FONT_STEP_0, _SETTLED_FONT_STEP_1]
    )
    ss.assert_font_size_step_pref(1)
    assert len(calls) == 3, f"ожидали ровно 3 попытки чтения, реально {len(calls)}"


@pytest.mark.p1
@allure.id("AT-BUG-088-adb-transport-failure-distinct-from-settle-timeout")
@allure.title("assert_theme_mode_pref: отказ adb-транспорта (RuntimeError) НЕ маскируется под settle-таймаут по значению")
def test_assert_theme_mode_pref_adb_failure_raises_distinct_runtime_error(monkeypatch):
    """AT-BUG-088: до фикса `_poll_settings_prefs` читал через голый
    `adb.run_as("cat ...")` — `returncode`/`stderr` отбрасываются (см.
    `adb.shell`), поэтому отвалившийся adb-транспорт (rc!=0, вывод пустой/
    ошибочный НЕ из-за легитимного отсутствия значения) неотличимо совпадал
    с «apply() ещё не отфлашил», и 3-секундный settle-полл
    (`SETTINGS_PREFS_POLL_TIMEOUT`) крутился до конца бюджета, чтобы упасть
    обычным `AssertionError` про несовпадение значения («theme_mode !=
    SYSTEM в SharedPreferences: ''») — отказ ИНСТРУМЕНТА выдавал себя за
    дефект ПРОДУКТА под видом settle-таймаута.

    Фикс переводит чтение на `adb.run_as_file_or_raise` (по образцу
    `app_steps._read_tabs_prefs_raw`, AT-BUG-055), которая сама кидает
    `RuntimeError` на неоднозначном исходе (rc не распознан/непустой вывод
    при ненулевом rc/sentinel отсутствует вовсе) — здесь мокаем ИМЕННО этот
    исход (адб/run-as отвалился на самом первом чтении) и проверяем, что
    наружу всплывает `RuntimeError` СРАЗУ, а не `AssertionError` settle-
    таймаута: два разных отказа (инструмент vs продукт) дают структурно
    РАЗНЫЕ типы исключений и разный текст — их больше нельзя перепутать по
    сообщению об ошибке."""
    calls = _fake_run_as_file_or_raise_sequence(
        monkeypatch,
        [
            RuntimeError(
                "run-as com.example.ao3_wrapper cat shared_prefs/ao3_settings.xml "
                "не завершился однозначно успешно (rc=None, сырой вывод='') — "
                "похоже на отвалившийся/неоднозначный adb или run-as"
            )
        ],
    )
    with pytest.raises(RuntimeError, match="не завершился однозначно успешно") as excinfo:
        ss.assert_theme_mode_pref("SYSTEM")
    # Регресс-замок: это НЕ AssertionError settle-таймаута про несовпадение
    # значения — структурно другой класс исключения и другой текст.
    assert not isinstance(excinfo.value, AssertionError)
    assert "theme_mode !=" not in str(excinfo.value)
    # Критик-гейт round1 (N1): пин на "СРАЗУ, без прокрутки бюджета" — не
    # только текст ошибки. Реализация вида "поймать/накопить/перевыбросить
    # после deadline" тоже прошла бы предыдущие два assert'а, оставаясь
    # ровно тем дефектом, который называет AT-BUG-088 (3с холостого кручения
    # перед бесполезной ошибкой).
    assert len(calls) == 1, (
        f"ожидали РОВНО одно чтение (без ретрая внутри полла на adb-отказе), "
        f"реально {len(calls)}"
    )


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
