"""spec-p3-second-emulator N1 (констрейнт 2): AO3_SYSTEM_PORT - безопасный парс,
мусор/вне-диапазона НЕ роняет импорт `framework/config/settings.py`. Пустой дефолт
-> capabilities.py НЕ выставляет `appium:systemPort` (авто-аллокация UiAutomator2
сохраняется).

`settings.py` не импортирует `appium` (проверено эмпирически, 2026-08-20: голый
`import framework.config.settings` работает системным python БЕЗ venv) - модуль
парсит `AO3_SYSTEM_PORT` НА ИМПОРТЕ (module-level присваивание), поэтому каждый
кейс батареи запускается В ОТДЕЛЬНОМ подпроцессе с нужным env (нельзя просто
monkeypatch после импорта - значение уже "запечено").
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_system_port(env_value: str | None) -> tuple[str, str, int]:
    """Возвращает (stdout, stderr, returncode) отдельного `python -c` процесса,
    который импортирует settings и печатает `SYSTEM_PORT` (или None)."""
    code = (
        "import sys; sys.path.insert(0, r'" + str(REPO_ROOT) + "'); "
        "from framework.config import settings; "
        "print('RESULT=' + repr(settings.SYSTEM_PORT))"
    )
    import os
    env = dict(os.environ)
    if env_value is None:
        env.pop("AO3_SYSTEM_PORT", None)
    else:
        env["AO3_SYSTEM_PORT"] = env_value
    cp = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env,
    )
    return cp.stdout, cp.stderr, cp.returncode


def _result_value(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("RESULT="):
            return line[len("RESULT="):]
    raise AssertionError(f"RESULT= не найден в stdout: {stdout!r}")


def test_unset_defaults_to_none():
    out, err, code = _import_system_port(None)
    assert code == 0, f"импорт упал: {err}"
    assert _result_value(out) == "None"


def test_empty_string_defaults_to_none():
    out, err, code = _import_system_port("")
    assert code == 0, f"импорт упал: {err}"
    assert _result_value(out) == "None"


def test_whitespace_only_defaults_to_none():
    out, err, code = _import_system_port("   ")
    assert code == 0, f"импорт упал: {err}"
    assert _result_value(out) == "None"


def test_garbage_does_not_crash_import():
    out, err, code = _import_system_port("abc")
    assert code == 0, f"мусорное значение уронило импорт: {err}"
    assert _result_value(out) == "None"
    assert "WARNING" in err


def test_valid_value_inside_auto_alloc_window_passes_through():
    out, err, code = _import_system_port("8250")
    assert code == 0
    assert _result_value(out) == "8250"


def test_valid_value_outside_auto_alloc_window_is_explicit_override_not_rejected():
    """Констрейнт 2: явное значение вне 8200-8299 - легитимная опция
    детерминизма/диагностики, НЕ отбрасывается."""
    out, err, code = _import_system_port("9999")
    assert code == 0
    assert _result_value(out) == "9999"


def test_boundary_min_valid_port_1():
    out, err, code = _import_system_port("1")
    assert code == 0
    assert _result_value(out) == "1"


def test_boundary_max_valid_port_65535():
    out, err, code = _import_system_port("65535")
    assert code == 0
    assert _result_value(out) == "65535"


def test_boundary_zero_rejected():
    out, err, code = _import_system_port("0")
    assert code == 0
    assert _result_value(out) == "None"
    assert "WARNING" in err


def test_negative_rejected():
    out, err, code = _import_system_port("-1")
    assert code == 0
    assert _result_value(out) == "None"
    assert "WARNING" in err


def test_beyond_65535_rejected_not_crashed():
    out, err, code = _import_system_port("65536")
    assert code == 0, f"импорт упал: {err}"
    assert _result_value(out) == "None"
    assert "WARNING" in err


def test_far_beyond_65535_rejected_not_crashed():
    out, err, code = _import_system_port("999999")
    assert code == 0, f"импорт упал: {err}"
    assert _result_value(out) == "None"
