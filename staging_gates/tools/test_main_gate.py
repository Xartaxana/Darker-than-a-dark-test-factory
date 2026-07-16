"""Юнит-смоки tools/main_gate.py (t-159, очередь v5 п.1, штабной порт) --
покрывает все ветки, перечисленные спекой: main-only фильтрация по
agent_id, блок при main-правке-без-прогона, пропуск при прогоне-после-
правки, пропуск без main-правок (в т.ч. когда есть ТОЛЬКО subagent-
правки), предохранитель 2 блоков (СВОЙ счётчик, независимый от
dod_gate.py), предупреждение о пустом журнале внутри block-сообщения --
kit-кейсы перенесены как есть, ПЛЮС штабные doc-only кейсы (см. ниже).

ШТАБНОЕ ОТЛИЧИЕ ОТ КИТА: то же правило doc-only (.md/.json/.jsonl), что
tools/dod_gate.py, применённое к MAIN-ONLY подмножеству edits/runs --
правки ТОЛЬКО .md/.json/.jsonl координатором (main-thread) освобождают
от инварианта; file_path=None -- fail-closed; смешанная правка --
инвариант в силе; .jsonl (правка logs/routing-log.jsonl -- штатная
операция Lead'а при приёмке) обязательный кейс спеки."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main_gate  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "main_gate.py"


def _run_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _stop_payload(cwd: str, session_id: str = "sess-x") -> dict:
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }


# ---------------------------------------------------------------------
# evaluate() -- pure logic, main-only filtering (перенесено из кита).
# ---------------------------------------------------------------------


def test_evaluate_no_edits_no_violation():
    violation, reason = main_gate.evaluate({"edits": [], "runs": []})
    assert violation is False
    assert reason == "no-main-edits"


def test_evaluate_ignores_subagent_only_edits():
    # Только subagent-правки (agent_id присутствует) -- main-ход не
    # трогал файлы, гейт не должен блокировать завершение координатора.
    track = {
        "edits": [{"ts": "t1", "agent_id": "agent-1"}],
        "runs": [],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is False
    assert reason == "no-main-edits"


def test_evaluate_main_edit_without_any_run_is_violation():
    track = {"edits": [{"ts": "2026-07-16T10:00:00.000000", "agent_id": None}], "runs": []}
    violation, reason = main_gate.evaluate(track)
    assert violation is True
    assert reason == "no-green-run"


def test_evaluate_main_edit_ignores_subagent_green_run():
    # Зелёный прогон СУБАГЕНТА не засчитывается за main-only прогон --
    # main-ход обязан иметь СВОЙ зелёный после своей последней правки.
    track = {
        "edits": [{"ts": "2026-07-16T10:00:05.000000", "agent_id": None}],
        "runs": [{"ts": "2026-07-16T10:00:06.000000", "outcome": "green", "agent_id": "agent-1"}],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is True
    assert reason == "no-green-run"


def test_evaluate_green_run_before_main_edit_is_violation():
    track = {
        "edits": [{"ts": "2026-07-16T10:00:05.000000", "agent_id": None}],
        "runs": [{"ts": "2026-07-16T10:00:00.000000", "outcome": "green", "agent_id": None}],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is True
    assert reason == "green-before-last-edit"


def test_evaluate_green_run_after_main_edit_is_not_violation():
    track = {
        "edits": [{"ts": "2026-07-16T10:00:00.000000", "agent_id": None}],
        "runs": [{"ts": "2026-07-16T10:00:05.000000", "outcome": "green", "agent_id": None}],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is False
    assert reason == "green-after-last-edit"


def test_evaluate_mixed_main_and_subagent_entries_filters_correctly():
    track = {
        "edits": [
            {"ts": "2026-07-16T10:00:00.000000", "agent_id": None},
            {"ts": "2026-07-16T10:00:10.000000", "agent_id": "agent-2"},
        ],
        "runs": [
            {"ts": "2026-07-16T10:00:05.000000", "outcome": "green", "agent_id": None},
            {"ts": "2026-07-16T10:00:20.000000", "outcome": "green", "agent_id": "agent-2"},
        ],
    }
    # Последняя main-only правка (10:00:00) раньше main-only зелёного
    # (10:00:05) -- НЕ нарушение, хотя subagent-правка (10:00:10)
    # позже обоих (subagent-записи не участвуют в main-only сравнении).
    violation, reason = main_gate.evaluate(track)
    assert violation is False
    assert reason == "green-after-last-edit"


# ---------------------------------------------------------------------
# STAGING_HQ: правило doc-only (.md/.json/.jsonl), main-only подмножество.
# ---------------------------------------------------------------------


def test_evaluate_doc_only_md_main_edits_no_violation():
    track = {
        "edits": [{"ts": "t1", "agent_id": None, "file_path": "docs/NOTES.md"}],
        "runs": [],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is False
    assert reason == "doc-only-edits-exempt"


def test_evaluate_doc_only_jsonl_routing_log_main_edit_no_violation():
    # Обязательный кейс: правка ТОЛЬКО logs/routing-log.jsonl координатором
    # (main-thread, agent_id=None) -- штатная операция при приёмке, не
    # должна блокировать завершение main-хода.
    track = {
        "edits": [{"ts": "t1", "agent_id": None, "file_path": "logs/routing-log.jsonl"}],
        "runs": [],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is False
    assert reason == "doc-only-edits-exempt"


def test_evaluate_doc_only_ignores_subagent_non_doc_edits():
    # Main-only правки -- ТОЛЬКО doc-only; subagent тем временем правил
    # .py -- main_gate фильтрует на agent_id ДО doc-only проверки,
    # subagent-правка не должна ломать исключение координатора.
    track = {
        "edits": [
            {"ts": "t1", "agent_id": None, "file_path": "docs/NOTES.md"},
            {"ts": "t2", "agent_id": "agent-1", "file_path": "tools/x.py"},
        ],
        "runs": [],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is False
    assert reason == "doc-only-edits-exempt"


def test_evaluate_unknown_file_path_main_fail_closed():
    track = {"edits": [{"ts": "t1", "agent_id": None, "file_path": None}], "runs": []}
    violation, reason = main_gate.evaluate(track)
    assert violation is True
    assert reason == "no-green-run"


def test_evaluate_missing_file_path_key_main_fail_closed():
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    violation, reason = main_gate.evaluate(track)
    assert violation is True
    assert reason == "no-green-run"


def test_evaluate_mixed_extensions_main_invariant_applies():
    track = {
        "edits": [
            {"ts": "t1", "agent_id": None, "file_path": "README.md"},
            {"ts": "t2", "agent_id": None, "file_path": "tools/x.py"},
        ],
        "runs": [],
    }
    violation, reason = main_gate.evaluate(track)
    assert violation is True
    assert reason == "no-green-run"


# ---------------------------------------------------------------------
# _journal_empty_warning_applies() -- проверка (б) (перенесено из кита).
# ---------------------------------------------------------------------


def test_journal_warning_false_when_journal_missing(tmp_path):
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    assert main_gate._journal_empty_warning_applies(str(tmp_path), track) is False


def test_journal_warning_false_when_journal_nonempty(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text('{"event":"delegated"}\n', encoding="utf-8")
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    assert main_gate._journal_empty_warning_applies(str(tmp_path), track) is False


def test_journal_warning_false_when_track_empty(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text("", encoding="utf-8")
    assert main_gate._journal_empty_warning_applies(str(tmp_path), {"edits": [], "runs": []}) is False


def test_journal_warning_true_when_journal_empty_and_track_nonempty(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text("", encoding="utf-8")
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    assert main_gate._journal_empty_warning_applies(str(tmp_path), track) is True


def test_journal_warning_ignores_subagent_only_track(tmp_path):
    # Пустой журнал, но трек содержит ТОЛЬКО subagent-записи -- по
    # буквальному тексту спеки ("непустом dod_track") предупреждение
    # смотрит на main-only подмножество, тем же критерием, что (а).
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text("", encoding="utf-8")
    track = {"edits": [{"ts": "t1", "agent_id": "agent-1"}], "runs": []}
    assert main_gate._journal_empty_warning_applies(str(tmp_path), track) is False


# ---------------------------------------------------------------------
# decide() -- gate_state / предохранитель / встроенное предупреждение
# (перенесено из кита) + штабные doc-only сценарии.
# ---------------------------------------------------------------------


def test_decide_blocks_on_first_violation(tmp_path):
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    exit_code, message, updated = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 2
    assert "заблокирована" in message
    assert updated["main_gate_state"]["consecutive_blocks"] == 1
    assert updated["gate_log"][-1] == {"action": "blocked", "reason": "no-green-run", "gate": "main"}


def test_decide_block_message_includes_journal_warning_when_applicable(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text("", encoding="utf-8")
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    exit_code, message, _ = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 2
    assert "заблокирована" in message
    assert "ПРЕДУПРЕЖДЕНИЕ" in message
    assert "routing-log.jsonl" in message


def test_decide_no_journal_warning_when_journal_has_content(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text('{"event":"delegated"}\n', encoding="utf-8")
    track = {"edits": [{"ts": "t1", "agent_id": None}], "runs": []}
    exit_code, message, _ = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 2
    assert "ПРЕДУПРЕЖДЕНИЕ" not in message


def test_decide_no_warning_when_no_violation_even_if_journal_empty(tmp_path):
    # (б) буквально живёт ВНУТРИ block-сообщения (а) -- нет нарушения
    # (а) -> нет отдельного предупреждения, даже если журнал пуст.
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text("", encoding="utf-8")
    track = {
        "edits": [{"ts": "2026-07-16T10:00:00.000000", "agent_id": None}],
        "runs": [{"ts": "2026-07-16T10:00:05.000000", "outcome": "green", "agent_id": None}],
    }
    exit_code, message, _ = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 0
    assert message == ""


def test_decide_blocks_again_on_second_consecutive_violation(tmp_path):
    track = {
        "edits": [{"ts": "t1", "agent_id": None}],
        "runs": [],
        "main_gate_state": {"consecutive_blocks": 1},
    }
    exit_code, message, updated = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 2
    assert updated["main_gate_state"]["consecutive_blocks"] == 2


def test_decide_skips_on_third_consecutive_violation_safety_valve(tmp_path):
    track = {
        "edits": [{"ts": "t1", "agent_id": None}],
        "runs": [],
        "main_gate_state": {"consecutive_blocks": 2},
    }
    exit_code, message, updated = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 0
    assert "предохранитель" in message
    assert updated["main_gate_state"]["consecutive_blocks"] == 0
    assert updated["gate_log"][-1]["action"] == "skipped_after_2_blocks"


def test_decide_resets_counter_on_success(tmp_path):
    track = {
        "edits": [{"ts": "t1", "agent_id": None}],
        "runs": [{"ts": "t2", "outcome": "green", "agent_id": None}],
        "main_gate_state": {"consecutive_blocks": 1},
    }
    exit_code, message, updated = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 0
    assert message == ""
    assert updated["main_gate_state"]["consecutive_blocks"] == 0


def test_decide_counter_independent_from_dod_gate_gate_state(tmp_path):
    # gate_state (dod_gate.py) уже "исчерпан" (2 блока) -- main_gate.py
    # использует СВОЙ ключ main_gate_state и должен блокировать (не
    # срабатывать предохранитель чужого счётчика).
    track = {
        "edits": [{"ts": "t1", "agent_id": None}],
        "runs": [],
        "gate_state": {"consecutive_blocks": 2},
        "main_gate_state": {"consecutive_blocks": 0},
    }
    exit_code, message, updated = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 2
    assert updated["gate_state"]["consecutive_blocks"] == 2  # чужой ключ не тронут
    assert updated["main_gate_state"]["consecutive_blocks"] == 1


def test_decide_doc_only_main_edits_pass_without_touching_counter(tmp_path):
    track = {
        "edits": [{"ts": "t1", "agent_id": None, "file_path": "logs/routing-log.jsonl"}],
        "runs": [],
        "main_gate_state": {"consecutive_blocks": 1},
    }
    exit_code, message, updated = main_gate.decide(track, cwd=str(tmp_path))
    assert exit_code == 0
    assert message == ""
    assert updated["main_gate_state"]["consecutive_blocks"] == 0


# ---------------------------------------------------------------------
# echo-JSON смок подпроцессом -- полный сценарий блок -> прогон -> пропуск
# (перенесено из кита) + штабные doc-only сценарии.
# ---------------------------------------------------------------------


def _write_track(tmp_path: Path, session_id: str, data: dict) -> Path:
    path = tmp_path / ".claude" / "dod_track" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_echo_json_no_track_file_passes(tmp_path):
    result = _run_hook(_stop_payload(str(tmp_path), "sess-none"), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".claude" / "dod_track" / "sess-none.json").exists()


def test_echo_json_blocks_when_main_edit_without_run(tmp_path):
    session_id = "sess-block"
    _write_track(
        tmp_path,
        session_id,
        {"edits": [{"ts": "t1", "tool_name": "Edit", "agent_id": None}], "runs": []},
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 2
    assert "заблокирована" in result.stderr

    track = json.loads((tmp_path / ".claude" / "dod_track" / f"{session_id}.json").read_text())
    assert track["main_gate_state"]["consecutive_blocks"] == 1


def test_echo_json_passes_when_only_subagent_edits(tmp_path):
    # Только SUBAGENT-правки в треке (agent_id заполнен) -- main-ход
    # ничего не трогал сам, Stop не блокируется.
    session_id = "sess-subagent-only"
    _write_track(
        tmp_path,
        session_id,
        {"edits": [{"ts": "t1", "tool_name": "Edit", "agent_id": "agent-1"}], "runs": []},
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_echo_json_passes_when_green_run_after_main_edit(tmp_path):
    session_id = "sess-green"
    _write_track(
        tmp_path,
        session_id,
        {
            "edits": [{"ts": "2026-07-16T10:00:00.000000", "tool_name": "Edit", "agent_id": None}],
            "runs": [
                {
                    "ts": "2026-07-16T10:00:05.000000",
                    "tool_name": "Bash",
                    "command": "python -m pytest tools/ -q",
                    "outcome": "green",
                    "agent_id": None,
                }
            ],
        },
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_echo_json_includes_journal_warning_in_block_message(tmp_path):
    session_id = "sess-warn"
    _write_track(
        tmp_path,
        session_id,
        {"edits": [{"ts": "t1", "tool_name": "Edit", "agent_id": None}], "runs": []},
    )
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "routing-log.jsonl").write_text("", encoding="utf-8")

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 2
    assert "заблокирована" in result.stderr
    assert "ПРЕДУПРЕЖДЕНИЕ" in result.stderr


def test_echo_json_safety_valve_after_two_consecutive_blocks(tmp_path):
    session_id = "sess-valve"
    _write_track(tmp_path, session_id, {"edits": [{"ts": "t1", "agent_id": None}], "runs": []})

    r1 = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert r1.returncode == 2

    r2 = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert r2.returncode == 2

    r3 = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert r3.returncode == 0
    assert "предохранитель" in r3.stderr

    track = json.loads((tmp_path / ".claude" / "dod_track" / f"{session_id}.json").read_text())
    assert track["main_gate_state"]["consecutive_blocks"] == 0
    actions = [g["action"] for g in track["gate_log"]]
    assert actions == ["blocked", "blocked", "skipped_after_2_blocks"]


def test_echo_json_doc_only_jsonl_routing_log_main_edit_passes(tmp_path):
    # Обязательный кейс спеки: правка ТОЛЬКО logs/routing-log.jsonl
    # координатором (main-thread) -- НЕ блокирует Stop, даже без прогона.
    session_id = "sess-doc-only-jsonl"
    _write_track(
        tmp_path,
        session_id,
        {
            "edits": [
                {"ts": "t1", "tool_name": "Edit", "agent_id": None, "file_path": "logs/routing-log.jsonl"}
            ],
            "runs": [],
        },
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_echo_json_doc_only_md_main_edit_passes(tmp_path):
    session_id = "sess-doc-only-md"
    _write_track(
        tmp_path,
        session_id,
        {
            "edits": [{"ts": "t1", "tool_name": "Edit", "agent_id": None, "file_path": "README.md"}],
            "runs": [],
        },
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_echo_json_unknown_file_path_main_still_blocks(tmp_path):
    session_id = "sess-unknown-path"
    _write_track(
        tmp_path,
        session_id,
        {"edits": [{"ts": "t1", "tool_name": "Edit", "agent_id": None, "file_path": None}], "runs": []},
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 2
    assert "заблокирована" in result.stderr


def test_echo_json_mixed_extensions_main_still_blocks(tmp_path):
    session_id = "sess-mixed"
    _write_track(
        tmp_path,
        session_id,
        {
            "edits": [
                {"ts": "t1", "tool_name": "Edit", "agent_id": None, "file_path": "README.md"},
                {"ts": "t2", "tool_name": "Edit", "agent_id": None, "file_path": "tools/x.py"},
            ],
            "runs": [],
        },
    )

    result = _run_hook(_stop_payload(str(tmp_path), session_id), cwd=tmp_path)
    assert result.returncode == 2
    assert "заблокирована" in result.stderr


def test_echo_json_malformed_json_fails_open():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="{not valid json",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_echo_json_raw_utf8_bytes_stdin_no_crash(tmp_path):
    # t-159 п.3-стиль сверка: main_gate.py -- НОВЫЙ файл, пишем сразу
    # с байтовым stdin-чтением; сырые UTF-8 байты не должны падать.
    payload = _stop_payload(str(tmp_path), "sess-utf8")
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw,
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0
