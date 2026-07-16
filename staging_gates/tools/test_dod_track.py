"""Юнит-смоки tools/dod_track.py (штабной вариант, t-159 п.7 порт) --
прямые вызовы чистых функций (build_fact/determine_outcome/
is_verification_command) плюс echo-JSON смок подпроцессом.

ШТАБНЫЕ ОТЛИЧИЯ ОТ КИТА (exam_fullgates_kit/tools/test_dod_track.py),
покрытые ДОПОЛНИТЕЛЬНО к перенесённым kit-кейсам (см. докстринг
tools/dod_track.py, раздел "STAGING_HQ ВАРИАНТ"):

 1. Исключения item-2а ("не признавать самотесты гейтовой инфры
    зелёным прогоном") в штабной версии НЕТ -- функции
    _targets_only_gate_infra_tests не существует. Kit-тесты,
    проверяющие ОБРАТНОЕ (что такие команды НЕ считаются
    verification), сюда НЕ перенесены -- они бы падали на штабной
    версии. Вместо них -- позитивные тесты: и канонический
    "python -m pytest tools/ gateway/ -q", и узкий
    "pytest tools/test_dispatch_gate.py -q" ОБА признаются
    verification-командой без исключений.
 2. build_fact() для edit-записей несёт "file_path" (str из
    tool_input.file_path, либо None) -- новое поле против кит-версии.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dod_track  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "dod_track.py"


def _run_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------
# build_fact -- pure logic.
# ---------------------------------------------------------------------


def test_build_fact_edit_tool_logged():
    for tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        kind, entry = dod_track.build_fact({"tool_name": tool_name})
        assert kind == "edit"
        assert entry["tool_name"] == tool_name
        assert "ts" in entry
        # Без tool_input вовсе -- file_path неизвестен -> None.
        assert entry["file_path"] is None


def test_build_fact_irrelevant_tool_ignored():
    assert dod_track.build_fact({"tool_name": "Read"}) is None
    assert dod_track.build_fact({"tool_name": "Grep"}) is None


def test_build_fact_bash_non_verification_command_ignored():
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
        "tool_response": {"stdout": "ok", "stderr": ""},
    }
    assert dod_track.build_fact(payload) is None


def test_build_fact_bash_verification_command_green():
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest tools/ -q"},
        "tool_response": {"stdout": "5 passed in 0.12s", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "run"
    assert entry["outcome"] == "green"
    assert entry["command"] == "python -m pytest tools/ -q"


def test_build_fact_powershell_verification_command_green():
    # STAGING_HQ 2026-07-16: штабные Windows-сессии гоняют команды
    # PowerShell-тулом (kit-среда -- Bash); без этой ветки прогоны
    # штаба невидимы треку (форензика первой живой сессии: runs=[]
    # при фактических зелёных прогонах, три no-green-run блока).
    payload = {
        "tool_name": "PowerShell",
        "tool_input": {"command": "python -m pytest tools/ -q"},
        "tool_response": {"stdout": "131 passed in 2.64s", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "run"
    assert entry["outcome"] == "green"
    assert entry["tool_name"] == "PowerShell"


def test_build_fact_powershell_non_verification_command_ignored():
    payload = {
        "tool_name": "PowerShell",
        "tool_input": {"command": "Get-ChildItem tools"},
        "tool_response": {"stdout": "ok", "stderr": ""},
    }
    assert dod_track.build_fact(payload) is None


def test_build_fact_bash_verification_command_red_on_failure_text():
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tools/"},
        "tool_response": {
            "stdout": "",
            "stderr": "Traceback (most recent call last):\n1 failed, 0 passed",
        },
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "run"
    assert entry["outcome"] == "red"


def test_build_fact_bash_verification_command_red_on_ambiguous_output():
    # Ни признаков провала, ни признаков успеха -- защитный дефолт "red"
    # (задокументированное самостоятельное решение: неопознанный
    # вывод не считается подтверждённым зелёным прогоном).
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest --collect-only"},
        "tool_response": {"stdout": "no tests ran", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "run"
    assert entry["outcome"] == "red"


def test_build_fact_rc_field_overrides_text_when_present():
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest tools/"},
        "tool_response": {"stdout": "something failed", "rc": 0},
    }
    kind, entry = dod_track.build_fact(payload)
    assert entry["outcome"] == "green"

    payload2 = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest tools/"},
        "tool_response": {"stdout": "5 passed", "exit_code": 1},
    }
    _, entry2 = dod_track.build_fact(payload2)
    assert entry2["outcome"] == "red"


def test_is_verification_command_matches_spec_forms():
    assert dod_track.is_verification_command("pytest")
    assert dod_track.is_verification_command("python -m pytest tools/ -q")
    assert dod_track.is_verification_command("python test_something.py")
    assert not dod_track.is_verification_command("ls -la")
    assert not dod_track.is_verification_command("git status")


# ---------------------------------------------------------------------
# STAGING_HQ п.1: НЕТ исключения "самотесты гейтовой инфры" -- И
# канонический, И узкий таргет ОБА признаются verification-командой.
# ---------------------------------------------------------------------


def test_gate_infra_self_tests_are_verification_commands_staging_hq():
    # В ките эти же команды считались бы "только самотесты гейтовой
    # инфры" и исключались; в штабе такого исключения нет -- сессия
    # может реально разрабатывать сами гейты, и прогон их тестов --
    # законный witness ИМЕННО для такой правки.
    for cmd in [
        "pytest tools/test_dod_gate.py",
        "python -m pytest tools/test_dispatch_gate.py -q",
        "pytest tools/test_dod_track.py",
        "python -m pytest tools/test_main_gate.py -q",
    ]:
        assert dod_track.is_verification_command(cmd), cmd


def test_gate_infra_self_test_build_fact_produces_run_not_none_staging_hq():
    # STAGING_HQ: в отличие от кита (где build_fact вернул бы None для
    # такой команды), штабная версия кладёт "run"-факт.
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tools/test_dod_gate.py -q"},
        "tool_response": {"stdout": "5 passed in 0.01s", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "run"
    assert entry["outcome"] == "green"
    assert entry["command"] == "pytest tools/test_dod_gate.py -q"


def test_canonical_command_recognized_as_verification():
    assert dod_track.is_verification_command("python -m pytest tools/ gateway/ -q")


def test_narrow_target_command_recognized_as_verification():
    assert dod_track.is_verification_command("pytest tools/test_dispatch_gate.py -q")


def test_both_canonical_and_narrow_forms_produce_run_facts():
    canonical_payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest tools/ gateway/ -q"},
        "tool_response": {"stdout": "381 passed in 4.20s", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(canonical_payload)
    assert kind == "run"
    assert entry["outcome"] == "green"

    narrow_payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tools/test_dispatch_gate.py -q"},
        "tool_response": {"stdout": "30 passed in 0.50s", "stderr": ""},
    }
    kind2, entry2 = dod_track.build_fact(narrow_payload)
    assert kind2 == "run"
    assert entry2["outcome"] == "green"


# ---------------------------------------------------------------------
# t-159 п.2б: witness-формы -- node-скрипт, UI-скриншот-прогон.
# (Логика не менялась против кита -- перенесено как есть.)
# ---------------------------------------------------------------------


def test_node_script_recognized_as_verification_command():
    assert dod_track.is_verification_command("node run_check.js")
    assert dod_track.is_verification_command("node scripts/verify.mjs")
    assert not dod_track.is_verification_command("node --version")


def test_ui_screenshot_command_recognized_as_verification_command():
    assert dod_track.is_verification_command("node take_screenshot.js")
    assert dod_track.is_verification_command("python run_playwright_check.py --screenshot")
    assert dod_track.is_verification_command("python capture_ui.py --puppeteer")


def test_node_script_outcome_uses_same_text_heuristics():
    green_payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "node run_check.js"},
        "tool_response": {"stdout": "All checks passed", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(green_payload)
    assert kind == "run"
    assert entry["outcome"] == "green"

    red_payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "node run_check.js"},
        "tool_response": {"stdout": "", "stderr": "Error: check failed"},
    }
    kind2, entry2 = dod_track.build_fact(red_payload)
    assert entry2["outcome"] == "red"


def test_ui_witness_command_silent_output_defaults_red():
    # Задокументированное ограничение: скрипт без текстового
    # подтверждения (ни passed/ok, ни failed/error/traceback) -- всё
    # ещё попадает в защитный дефолт "red", хоть команда теперь
    # РАСПОЗНАНА (видима в треке) -- раньше была невидима целиком.
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "node take_screenshot.js"},
        "tool_response": {"stdout": "screenshot.png saved", "stderr": ""},
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "run"
    assert entry["outcome"] == "red"


# ---------------------------------------------------------------------
# STAGING_HQ п.2: build_fact() edit-записи несут file_path.
# ---------------------------------------------------------------------


def test_build_fact_edit_includes_file_path_from_tool_input():
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "tools/dod_gate.py", "old_string": "a", "new_string": "b"},
    }
    kind, entry = dod_track.build_fact(payload)
    assert kind == "edit"
    assert entry["file_path"] == "tools/dod_gate.py"


def test_build_fact_edit_file_path_missing_key_defaults_to_none():
    payload = {"tool_name": "Write", "tool_input": {"content": "x"}}
    kind, entry = dod_track.build_fact(payload)
    assert kind == "edit"
    assert entry["file_path"] is None


def test_build_fact_edit_file_path_non_string_defaults_to_none():
    # Защитная ветка -- если file_path пришёл НЕ строкой (искажённый
    # payload), поле в записи -- None, не мусорное значение.
    payload = {"tool_name": "MultiEdit", "tool_input": {"file_path": 12345}}
    kind, entry = dod_track.build_fact(payload)
    assert kind == "edit"
    assert entry["file_path"] is None


def test_build_fact_edit_file_path_for_each_edit_tool_name():
    for tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        payload = {"tool_name": tool_name, "tool_input": {"file_path": f"docs/{tool_name}.md"}}
        kind, entry = dod_track.build_fact(payload)
        assert kind == "edit"
        assert entry["file_path"] == f"docs/{tool_name}.md"


# ---------------------------------------------------------------------
# echo-JSON смок подпроцессом.
# ---------------------------------------------------------------------


def test_echo_json_logs_edit(tmp_path):
    payload = {
        "session_id": "sess-1",
        "cwd": str(tmp_path),
        "tool_name": "Edit",
        "tool_input": {"file_path": "x.py"},
    }
    result = _run_hook(payload, cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    track_path = tmp_path / ".claude" / "dod_track" / "sess-1.json"
    assert track_path.exists()
    data = json.loads(track_path.read_text(encoding="utf-8"))
    assert len(data["edits"]) == 1
    assert data["edits"][0]["tool_name"] == "Edit"
    assert data["edits"][0]["file_path"] == "x.py"
    assert data["runs"] == []


def test_echo_json_logs_green_and_red_runs_distinctly(tmp_path):
    session_id = "sess-2"
    green_payload = {
        "session_id": session_id,
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest tools/ -q"},
        "tool_response": {"stdout": "3 passed in 0.05s", "stderr": ""},
    }
    red_payload = {
        "session_id": session_id,
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tools/"},
        "tool_response": {"stdout": "", "stderr": "1 failed, 2 passed"},
    }

    r1 = _run_hook(green_payload, cwd=tmp_path)
    assert r1.returncode == 0, r1.stderr
    r2 = _run_hook(red_payload, cwd=tmp_path)
    assert r2.returncode == 0, r2.stderr

    track_path = tmp_path / ".claude" / "dod_track" / f"{session_id}.json"
    data = json.loads(track_path.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2
    assert data["runs"][0]["outcome"] == "green"
    assert data["runs"][1]["outcome"] == "red"


def test_echo_json_logs_gate_infra_self_test_run_staging_hq(tmp_path):
    # STAGING_HQ: в ките эта команда была бы проигнорирована
    # (build_fact -> None); в штабе кладётся как обычный run-факт.
    payload = {
        "session_id": "sess-gate-infra",
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tools/test_dod_gate.py -q"},
        "tool_response": {"stdout": "12 passed in 0.30s", "stderr": ""},
    }
    result = _run_hook(payload, cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    track_path = tmp_path / ".claude" / "dod_track" / "sess-gate-infra.json"
    data = json.loads(track_path.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 1
    assert data["runs"][0]["outcome"] == "green"


def test_echo_json_ignores_unrelated_tool(tmp_path):
    payload = {
        "session_id": "sess-3",
        "cwd": str(tmp_path),
        "tool_name": "Read",
        "tool_input": {"file_path": "x.py"},
    }
    result = _run_hook(payload, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    # Никакой трек-файл не создаётся для нерелевантного тула.
    assert not (tmp_path / ".claude" / "dod_track" / "sess-3.json").exists()


def test_echo_json_preserves_unknown_keys_written_by_other_hook(tmp_path):
    """dod_gate.py/main_gate.py пишут в тот же файл ключи gate_state/
    main_gate_state/gate_log -- dod_track.py при своём read-modify-write
    не должен их стирать."""
    session_id = "sess-4"
    track_path = tmp_path / ".claude" / "dod_track" / f"{session_id}.json"
    track_path.parent.mkdir(parents=True)
    track_path.write_text(
        json.dumps(
            {
                "edits": [],
                "runs": [],
                "gate_state": {"consecutive_blocks": 1},
                "gate_log": [{"action": "blocked", "reason": "no-green-run"}],
            }
        ),
        encoding="utf-8",
    )

    payload = {
        "session_id": session_id,
        "cwd": str(tmp_path),
        "tool_name": "Write",
        "tool_input": {"file_path": "y.py"},
    }
    result = _run_hook(payload, cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    data = json.loads(track_path.read_text(encoding="utf-8"))
    assert len(data["edits"]) == 1
    assert data["gate_state"] == {"consecutive_blocks": 1}
    assert data["gate_log"] == [{"action": "blocked", "reason": "no-green-run"}]


# ---------------------------------------------------------------------
# Byte-safe stdin: субпроцесс-смок сырыми UTF-8 байтами (ensure_ascii=
# False, input=bytes, БЕЗ text=True/encoding на subprocess) -- по
# образцу kit test_dispatch_gate.py форма (2). Кириллический file_path
# в payload -- значимая проверка: если бы sys.stdin.buffer.read() +
# явный UTF-8-decode были сломаны/отсутствовали, платформенная
# кодировка (cp1251 на этой машине) исказила бы кириллицу в mojibake,
# и entry["file_path"] не совпал бы с исходной строкой.
# ---------------------------------------------------------------------


def test_echo_json_raw_utf8_bytes_stdin_preserves_cyrillic_file_path(tmp_path):
    session_id = "sess-utf8"
    payload = {
        "session_id": session_id,
        "cwd": str(tmp_path),
        "tool_name": "Edit",
        "tool_input": {"file_path": "докстринг/файл.py"},
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw,
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")

    track_path = tmp_path / ".claude" / "dod_track" / f"{session_id}.json"
    data = json.loads(track_path.read_text(encoding="utf-8"))
    assert data["edits"][0]["file_path"] == "докстринг/файл.py"
