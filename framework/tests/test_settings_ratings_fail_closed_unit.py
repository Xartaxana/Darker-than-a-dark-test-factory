"""Device-free матрица веток AT-BUG-045 — трёх Then-хелперов `work_ratings`
(`settings_steps.assert_ratings_present`/`assert_no_ratings`/
`assert_rating_rows_empty`), мокает `framework.core.adb.run_as` НА УРОВНЕ
МОДУЛЯ (не подмена самих хелперов) — тест ловит регресс в РЕАЛЬНОМ коде
трёх функций, как `test_seed_db_schema_race_unit.py::
test_schema_ready_fail_closed_on_recorded_outputs` (тот же приём, тот же
класс дефекта: fail-open на неотличимости "легитимная деградация" vs
"транспорт/иная ошибка").

Attempt 1 (коммит `3805010`) закрыл ТОЛЬКО отказ транспорта: заменил
`2>/dev/null || echo NOSQLITE` на `2>&1 && echo OK || echo NOSQLITE`. Но
`|| echo NOSQLITE` в attempt 1 ловил ЛЮБОЙ ненулевой exit `sqlite3` — не
только «бинаря нет». Живой зонд критика на `emulator-5554` (бинарь
`sqlite3` РЕАЛЬНО есть): SELECT из несуществующей таблицы дал
`'Error: in prepare, no such table: work_ratings\nNOSQLITE\n'` — все три
хелпера молча делали `return` (ложный зелёный Then на состоянии гонки
AT-BUG-044).

Attempt 2 (этот файл): remote-команда получила ОТДЕЛЬНЫЙ `command -v
sqlite3` гейт ПЕРЕД самим SELECT — `NOSQLITE` теперь печатается ТОЛЬКО
если бинаря реально нет; любая ошибка самого SELECT (нет таблицы / БД
заблокирована / файла нет) остаётся сырым текстом БЕЗ маркера и попадает
в ветку `RuntimeError`. Ветки `*-sqlite-error-no-marker` ниже — прямой
регресс-тест на закрытие этого блокера (ДО фикса ожидание было бы
`"pass"`, см. `bugs/AT-BUG-045.md` §Обсуждение attempt 2)."""
from __future__ import annotations

import allure
import pytest

from framework.core import adb
from framework.steps import settings_steps as ss


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


FUNCS = {
    "assert_ratings_present": ss.assert_ratings_present,
    "assert_no_ratings": ss.assert_no_ratings,
    "assert_rating_rows_empty": ss.assert_rating_rows_empty,
}


def _outcome(fn_name: str, recorded_output: str, monkeypatch) -> tuple[str, str]:
    captured_cmd: list[str] = []

    def _fake_run_as(cmd: str) -> str:
        captured_cmd.append(cmd)
        return recorded_output

    monkeypatch.setattr(adb, "run_as", _fake_run_as)
    try:
        FUNCS[fn_name]()
    except AssertionError as e:
        return "assert", str(e)
    except RuntimeError as e:
        return "runtime", str(e)
    finally:
        # Блокер 1 фикс: NOSQLITE-ветка обязана жить ЗА отдельным `command -v`
        # гейтом, не за `|| echo NOSQLITE` после самого SELECT.
        assert "command -v sqlite3" in captured_cmd[0]
    return "pass", ""


CASES = [
    # --- легитимная деградация "нет бинаря sqlite3" ---
    pytest.param("assert_ratings_present", "NOSQLITE\n", "pass", id="nosqlite|assert_ratings_present"),
    pytest.param("assert_no_ratings", "NOSQLITE\n", "pass", id="nosqlite|assert_no_ratings"),
    pytest.param("assert_rating_rows_empty", "NOSQLITE\n", "pass", id="nosqlite|assert_rating_rows_empty"),
    # --- реальные данные, SELECT реально исполнился (суффикс OK) ---
    pytest.param("assert_ratings_present", "3\nOK\n", "pass", id="count3-ok|assert_ratings_present"),
    pytest.param("assert_no_ratings", "3\nOK\n", "assert", id="count3-ok|assert_no_ratings"),
    pytest.param("assert_ratings_present", "0\nOK\n", "assert", id="count0-ok|assert_ratings_present"),
    pytest.param("assert_no_ratings", "0\nOK\n", "pass", id="count0-ok|assert_no_ratings"),
    # --- пустая таблица, маркер OK без тела (граница парсинга) ---
    pytest.param("assert_rating_rows_empty", "OK\n", "pass", id="marker-only-ok|assert_rating_rows_empty"),
    pytest.param("assert_ratings_present", "OK\n", "assert", id="marker-only-ok|assert_ratings_present"),
    pytest.param("assert_no_ratings", "OK\n", "assert", id="marker-only-ok|assert_no_ratings"),
    # --- непустые строки после Clear all (BUG-012/BUG-022 различающий замер) ---
    pytest.param(
        "assert_rating_rows_empty", "12345|SAVE|1690000000\nOK\n", "assert",
        id="rows-ok|assert_rating_rows_empty",
    ),
    # --- CRLF на живом устройстве (Windows adb.exe транспорт) ---
    pytest.param("assert_ratings_present", "1\r\nOK\r\n", "pass", id="crlf-count|assert_ratings_present"),
    pytest.param("assert_rating_rows_empty", "OK\r\n", "pass", id="crlf-marker-only|assert_rating_rows_empty"),
    # --- САМ БЛОКЕР 1 (attempt 1): sqlite3 ЕСТЬ, но SELECT упал — БЕЗ маркера.
    # ДО фикса (attempt 1 remote-команда) этот вход давал 'Error: in prepare,
    # no such table: work_ratings\nNOSQLITE\n' -> "pass" (ложный skip). ПОСЛЕ
    # фикса (attempt 2, `command -v` гейт ПЕРЕД SELECT) — вход просто не
    # печатает NOSQLITE (гейт его не ставил), тело содержит текст ошибки,
    # без OK -> RuntimeError.
    pytest.param(
        "assert_ratings_present", "Error: in prepare, no such table: work_ratings\n", "runtime",
        id="sqlite-error-no-marker|assert_ratings_present",
    ),
    pytest.param(
        "assert_no_ratings", "Error: in prepare, no such table: work_ratings\n", "runtime",
        id="sqlite-error-no-marker|assert_no_ratings",
    ),
    pytest.param(
        "assert_rating_rows_empty", "Error: in prepare, no such table: work_ratings\n", "runtime",
        id="sqlite-error-no-marker|assert_rating_rows_empty",
    ),
    pytest.param(
        "assert_ratings_present", "Error: database is locked\n", "runtime",
        id="sqlite-locked-no-marker|assert_ratings_present",
    ),
    # --- отказ ТРАНСПОРТА (устройство offline/adb упал) — пустой/мусорный out ---
    pytest.param("assert_ratings_present", "", "runtime", id="transport-empty|assert_ratings_present"),
    pytest.param("assert_no_ratings", "", "runtime", id="transport-empty|assert_no_ratings"),
    pytest.param("assert_rating_rows_empty", "", "runtime", id="transport-empty|assert_rating_rows_empty"),
    pytest.param("assert_ratings_present", "   \n\n", "runtime", id="transport-whitespace|assert_ratings_present"),
    pytest.param(
        "assert_ratings_present", "error: device 'emulator-5554' not found\n", "runtime",
        id="adb-error-no-marker|assert_ratings_present",
    ),
]


@pytest.mark.p1
@allure.id("AT-BUG-045-fail-closed-branch-matrix-attempt2")
@allure.title("settings_steps ratings Then-хелперы — fail-closed матрица (attempt 2: command -v гейт, не `|| echo NOSQLITE`)")
@pytest.mark.parametrize("fn_name,recorded_output,expected", CASES)
def test_branch(fn_name, recorded_output, expected, monkeypatch):
    got, msg = _outcome(fn_name, recorded_output, monkeypatch)
    assert got == expected, f"{fn_name} на {recorded_output!r}: ожидали {expected}, получили {got} ({msg})"


@pytest.mark.p1
@allure.id("AT-BUG-045-remote-command-has-command-v-gate-not-bare-or-echo")
@allure.title("Регресс-замок: remote-команда всех трёх хелперов несёт `command -v sqlite3` гейт (не `|| echo NOSQLITE` после SELECT)")
def test_remote_command_uses_command_v_gate(monkeypatch):
    """Дословная проверка ТЕКСТА remote-команды — блокер 1 (attempt 1) был
    именно в том, что `NOSQLITE` печатался через `|| echo NOSQLITE` СРАЗУ
    после SELECT (ловит любой ненулевой exit sqlite3). Attempt 2 обязан
    ставить `command -v sqlite3` гейт ДО SELECT и НЕ иметь безусловного
    `|| echo NOSQLITE` в хвосте команды."""
    # per-функции безопасный ("pass") вывод — важен только ТЕКСТ команды,
    # не исход ассерта
    pass_output = {
        "assert_ratings_present": "3\nOK\n",
        "assert_no_ratings": "0\nOK\n",
        "assert_rating_rows_empty": "OK\n",
    }
    for fn_name in FUNCS:
        captured_cmd: list[str] = []

        def _fake_run_as(cmd: str) -> str:
            captured_cmd.append(cmd)
            return pass_output[fn_name]

        monkeypatch.setattr(adb, "run_as", _fake_run_as)
        FUNCS[fn_name]()
        cmd = captured_cmd[0]
        assert "command -v sqlite3" in cmd, f"{fn_name}: нет command -v гейта в {cmd!r}"
        assert not cmd.rstrip("'\"").endswith("echo NOSQLITE"), (
            f"{fn_name}: хвост команды всё ещё безусловный `|| echo NOSQLITE` после SELECT: {cmd!r}"
        )
