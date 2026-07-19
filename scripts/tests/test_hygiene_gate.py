"""Тесты scripts/hygiene_gate.py -- PreToolUse warn-хук командной
гигиены (скоуп v1: только класс "запись в журнал мимо
python scripts/log_append.py"). Покрывает DoD задачи: позитивы для
обоих журналов (routing-log/orchestrator-log) x индикаторов записи
(редирект, printf/echo, PowerShell Add-Content/Set-Content/Out-File),
негативы (канонический вызов, отсутствие журнальной подстроки,
чтение/поиск без записи-токена), регресс permissionDecision,
fail-open (пустой/битый stdin) и адверсариальная батарея (длинная
команда, вложенные кавычки, кириллица, многострочная команда)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hygiene_gate

SCRIPT = Path(__file__).resolve().parents[1] / "hygiene_gate.py"


def _run_hook(raw_input, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw_input,
        capture_output=True,
        **kwargs,
    )


def _bash_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _ps_payload(command: str) -> dict:
    return {"tool_name": "PowerShell", "tool_input": {"command": command}}


# ---------------------------------------------------------------------
# decide() -- pure logic: позитивы
# ---------------------------------------------------------------------


def test_decide_echo_redirect_routing_log_triggers():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("echo done >> logs/routing-log.jsonl")
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_printf_orchestrator_log_triggers():
    exit_code, output = hygiene_gate.decide(
        _bash_payload('printf "| ts | r | a | art | out |" >> state/orchestrator-log.md')
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_powershell_add_content_triggers():
    exit_code, output = hygiene_gate.decide(
        _ps_payload('Add-Content -Path state/orchestrator-log.md -Value "| row |"')
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_powershell_set_content_triggers():
    exit_code, output = hygiene_gate.decide(
        _ps_payload('Set-Content -Path logs/routing-log.jsonl -Value "{}"')
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_powershell_out_file_triggers():
    exit_code, output = hygiene_gate.decide(
        _ps_payload('"{}" | Out-File -Append logs/routing-log.jsonl')
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_case_insensitive_journal_substring():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("echo x >> LOGS/ROUTING-LOG.JSONL")
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_case_insensitive_write_token():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("ECHO x >> logs/routing-log.jsonl")
    )
    assert exit_code == 0
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_decide_double_redirect_append_triggers():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("echo x >> logs/routing-log.jsonl")
    )
    assert exit_code == 0
    assert output is not None


# ---------------------------------------------------------------------
# decide() -- pure logic: негативы
# ---------------------------------------------------------------------


def test_decide_canonical_log_append_call_is_silent_pass():
    exit_code, output = hygiene_gate.decide(
        _bash_payload(
            'python scripts/log_append.py routing --event delegated '
            '--agent builder --model sonnet --task-id t-042 '
            '--worker-ref cli:2026-07-19'
        )
    )
    assert exit_code == 0
    assert output is None


def test_decide_no_journal_substring_is_silent_pass():
    exit_code, output = hygiene_gate.decide(_bash_payload("echo hi >> notes.txt"))
    assert exit_code == 0
    assert output is None


def test_decide_read_only_grep_with_journal_substring_is_silent_pass():
    # Чтение/поиск по содержимому с подстрокой routing-log, БЕЗ
    # редиректа и без токена записи -- не про запись в журнал.
    exit_code, output = hygiene_gate.decide(
        _bash_payload("grep routing-log logs/routing-log.jsonl")
    )
    assert exit_code == 0
    assert output is None


def test_decide_non_bash_tool_is_silent_pass():
    exit_code, output = hygiene_gate.decide(
        {"tool_name": "Edit", "tool_input": {"command": "echo x >> logs/routing-log.jsonl"}}
    )
    assert exit_code == 0
    assert output is None


def test_decide_clean_command_is_silent_pass():
    exit_code, output = hygiene_gate.decide(_bash_payload("python -m pytest scripts/tests -q"))
    assert exit_code == 0
    assert output is None


def test_decide_canonical_call_overrides_even_with_write_token_present():
    # Искусственный, но явно проверяемый спекой случай: команда несёт
    # И журнальную подстроку, И токен записи, И при этом канонический
    # вызов -- log_append.py присутствует -> НЕ триггерится (условие
    # (в) исключения проверяется независимо от (а)/(б), не полагаясь
    # на то, что комбинация никогда не встретится на практике).
    exit_code, output = hygiene_gate.decide(
        _bash_payload(
            'python scripts/log_append.py routing --event delegated '
            '--agent builder --model sonnet --task-id t-042 '
            '--worker-ref cli:2026-07-19 '
            '--notes "echo backup >> logs/routing-log.jsonl"'
        )
    )
    assert exit_code == 0
    assert output is None


def test_decide_missing_command_is_silent_pass():
    exit_code, output = hygiene_gate.decide({"tool_name": "Bash", "tool_input": {}})
    assert exit_code == 0
    assert output is None


def test_decide_non_string_command_is_silent_pass():
    exit_code, output = hygiene_gate.decide(
        {"tool_name": "Bash", "tool_input": {"command": 123}}
    )
    assert exit_code == 0
    assert output is None


def test_decide_non_dict_payload_is_silent_pass():
    exit_code, output = hygiene_gate.decide(["not", "a", "dict"])
    assert exit_code == 0
    assert output is None


def test_decide_non_dict_tool_input_is_silent_pass():
    exit_code, output = hygiene_gate.decide({"tool_name": "Bash", "tool_input": "oops"})
    assert exit_code == 0
    assert output is None


# ---------------------------------------------------------------------
# Регресс permissionDecision (B1-класс: warn не трогает permission-путь)
# ---------------------------------------------------------------------


def test_decide_hook_specific_output_never_carries_permission_decision():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("echo x >> logs/routing-log.jsonl")
    )
    assert exit_code == 0
    hso = output["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in hso
    assert isinstance(hso["additionalContext"], str) and hso["additionalContext"]


# ---------------------------------------------------------------------
# subprocess-уровень: exit code, stdout JSON, fail-open, смок
# ---------------------------------------------------------------------


def test_echo_json_clean_command_exit0_no_stdout():
    payload = _bash_payload("python -m pytest scripts/tests -q")
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr == ""


def test_echo_json_canonical_log_append_exit0_no_stdout():
    payload = _bash_payload(
        'python scripts/log_append.py routing --event delegated '
        '--agent builder --model sonnet --task-id t-042 --worker-ref cli:2026-07-19'
    )
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr == ""


def test_echo_json_dirty_command_exit0_with_stdout_json():
    payload = _bash_payload("echo done >> logs/routing-log.jsonl")
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    hso = data["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in hso
    assert hygiene_gate.MSG_JOURNAL_BYPASS in hso["additionalContext"]


def test_echo_json_non_bash_tool_exit0_no_stdout():
    payload = {"tool_name": "Task", "tool_input": {"subagent_type": "builder"}}
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- адверсариальная батарея (DoD п.1) ---


def test_adversarial_empty_stdin():
    result = _run_hook("", text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr == ""


def test_adversarial_malformed_json():
    result = _run_hook("{not valid json", text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr == ""


def test_adversarial_cyrillic_command_raw_utf8_bytes():
    # Сырые UTF-8-байты на stdin, БЕЗ text=True -- форма, которой
    # харнесс реально кормит дочерний процесс.
    payload = _bash_payload("echo проверка >> logs/routing-log.jsonl # кириллица")
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    result = _run_hook(raw)
    assert result.returncode == 0
    stdout_text = result.stdout.decode("utf-8")
    data = json.loads(stdout_text)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert hygiene_gate.MSG_JOURNAL_BYPASS in ctx


def test_adversarial_very_long_command_no_crash():
    long_command = "echo " + ("a" * 100_000) + " >> logs/routing-log.jsonl"
    payload = _bash_payload(long_command)
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert hygiene_gate.MSG_JOURNAL_BYPASS in data["hookSpecificOutput"]["additionalContext"]


def test_adversarial_nested_quotes_no_crash():
    command = """echo "he said \\"routing-log\\" here" >> logs/routing-log.jsonl"""
    payload = _bash_payload(command)
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert hygiene_gate.MSG_JOURNAL_BYPASS in data["hookSpecificOutput"]["additionalContext"]


def test_adversarial_multiline_command_no_crash():
    command = "echo start\necho x >> logs/routing-log.jsonl\necho end"
    payload = _bash_payload(command)
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert hygiene_gate.MSG_JOURNAL_BYPASS in data["hookSpecificOutput"]["additionalContext"]


def test_adversarial_null_bytes_in_json_string_no_crash():
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo x \x00 >> logs/routing-log.jsonl"},
    }
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    assert result.stderr == ""
