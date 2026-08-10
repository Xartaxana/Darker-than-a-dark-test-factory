"""Device-free матрица веток `adb.run_as_file_or_raise` (AT-BUG-055) — честное
чтение приватного файла приложения через `run-as cat`, закрывающее класс
«нечитаемый/отвалившийся ответ adb/run-as неотличим от легитимно пустого
состояния» (`framework/core/adb.py:37-42` отбрасывает `returncode`/`stderr`).

Мокает `framework.core.adb.shell` НА УРОВНЕ МОДУЛЯ (тот же приём, что
`test_settings_ratings_fail_closed_unit.py`/AT-BUG-045,
`test_seed_db_schema_race_unit.py`/AT-BUG-044) — тест ловит регресс в РЕАЛЬНОМ
коде `run_as_file_or_raise`, не в подменённой обёртке.

Три исхода: `rc==0` (файл реально прочитан, контент возвращён — может быть
пустым, ЭТО НЕ то же самое, что «не читался»); `rc!=0` БЕЗ содержимого
(легитимно «файла ещё нет», например до первой записи `SharedPreferences.
apply()`, — валидный пустой результат); всё остальное (sentinel-строка
отсутствует вовсе — `run-as`/remote shell не выполнились; код возврата не
распознан; ненулевой код С непустым содержимым — подозрительная смесь) —
`RuntimeError`, не молчаливая пустая строка."""
from __future__ import annotations

import allure
import pytest

from framework.core import adb

_SENTINEL = adb._RUN_AS_FILE_RC_SENTINEL


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    yield


def _run_with_output(recorded_output: str, monkeypatch) -> tuple[str, str]:
    captured_cmd: list[str] = []

    def _fake_shell(cmd: str, timeout: float = 0) -> str:
        captured_cmd.append(cmd)
        return recorded_output

    monkeypatch.setattr(adb, "shell", _fake_shell)
    try:
        result = adb.run_as_file_or_raise("shared_prefs/ao3_settings.xml")
    except RuntimeError as e:
        return "runtime", str(e)
    finally:
        assert "run-as" in captured_cmd[0] and "cat" in captured_cmd[0]
    return "ok", result


CASES = [
    # --- rc==0: файл реально прочитан ---
    pytest.param(f"<map>content</map>\n{_SENTINEL}0", "ok", "<map>content</map>", id="rc0-content"),
    pytest.param(f"{_SENTINEL}0", "ok", "", id="rc0-empty-content"),
    pytest.param(f"line1\nline2\n{_SENTINEL}0", "ok", "line1\nline2", id="rc0-multiline"),
    # --- rc!=0 БЕЗ содержимого: легитимно "файла ещё нет" (No such file or directory) ---
    pytest.param(f"{_SENTINEL}1", "ok", "", id="rc1-no-content-legit-missing"),
    pytest.param(f"{_SENTINEL}2", "ok", "", id="rc2-no-content-legit-missing"),
    pytest.param(f"   \n{_SENTINEL}1", "ok", "", id="rc1-whitespace-only-legit-missing"),
    # --- САМ БЛОКЕР AT-BUG-055: отвалившийся транспорт молча давал "" ДО фикса ---
    pytest.param("", "runtime", None, id="transport-empty-no-sentinel"),
    pytest.param("run-as: Package 'com.example' is unknown\n", "runtime", None,
                 id="run-as-failed-no-sentinel"),
    pytest.param("error: device 'emulator-5554' not found\n", "runtime", None,
                 id="adb-error-no-sentinel"),
    # --- код возврата не распознан (мусор после sentinel) ---
    pytest.param(f"{_SENTINEL}abc", "runtime", None, id="malformed-rc-not-numeric"),
    # --- ненулевой код с НЕПУСТЫМ содержимым — подозрительная смесь, fail-closed ---
    pytest.param(f"partial garbage\n{_SENTINEL}1", "runtime", None,
                 id="rc1-with-content-suspicious-mix"),
    # --- CRLF (Windows adb.exe транспорт) ---
    pytest.param(f"<map>x</map>\r\n{_SENTINEL}0\r\n", "ok", "<map>x</map>", id="crlf-rc0"),
    pytest.param(f"{_SENTINEL}1\r\n", "ok", "", id="crlf-rc1-legit-missing"),
]


@pytest.mark.p1
@allure.id("AT-BUG-055-run-as-file-or-raise-branch-matrix")
@allure.title("adb.run_as_file_or_raise — fail-closed матрица (прочитан/легитимно отсутствует/отвалившийся транспорт)")
@pytest.mark.parametrize("recorded_output,expected_kind,expected_value", CASES)
def test_branch(recorded_output, expected_kind, expected_value, monkeypatch):
    kind, value = _run_with_output(recorded_output, monkeypatch)
    assert kind == expected_kind, (
        f"на вход {recorded_output!r}: ожидали {expected_kind}, получили {kind} ({value})"
    )
    if expected_kind == "ok":
        assert value == expected_value, f"на вход {recorded_output!r}: контент {value!r} != {expected_value!r}"


@pytest.mark.p1
@allure.id("AT-BUG-055-run-as-file-or-raise-regression-lock-no-silent-empty")
@allure.title("Регресс-замок: отвалившийся транспорт НЕ возвращает молчаливую пустую строку (AT-BUG-055 сам блокер)")
def test_transport_failure_does_not_silently_return_empty_string(monkeypatch):
    """До фикса `_read_tabs_prefs_raw` (тонкая обёртка над `adb.run_as`) на этом
    входе молча возвращала `""`, что `_parse_persisted_tabs` штатно превращал в
    `[]` — «0 вкладок», неотличимое от реального пустого состояния. Явный
    регресс-замок: тот же вход теперь обязан кидать, не возвращать `""`."""
    monkeypatch.setattr(adb, "shell", lambda cmd, timeout=0: "")
    with pytest.raises(RuntimeError, match="AT-BUG-055"):
        adb.run_as_file_or_raise("shared_prefs/ao3_settings.xml")
