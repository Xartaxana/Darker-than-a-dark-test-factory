"""Тесты scripts/hygiene_gate.py -- PreToolUse warn-хук командной
гигиены (скоуп v1: только класс "запись в журнал мимо
python scripts/log_append.py"). Покрывает DoD задачи: позитивы для
обоих журналов (routing-log/orchestrator-log) x индикаторов записи
(редирект, printf/echo, PowerShell Add-Content/Set-Content/Out-File),
негативы (канонический вызов, отсутствие журнальной подстроки,
чтение/поиск без записи-токена), регресс permissionDecision,
fail-open (пустой/битый stdin) и адверсариальная батарея (длинная
команда, вложенные кавычки, кириллица, многострочная команда).

v2 (task_id hygiene-gate-v2) добавляет: два живых false-positive
(FP-1 -- commit-сообщение с "orchestrator-log" и `>` в тексте; FP-2 --
git add путём + commit-сообщение со стрелками и witness) дословно как
в evidence задачи -> None; регресс на известный v1-обход (комментарий
"# log_append.py" гасил детект) -> ТЕПЕРЬ warn; канон -- форма
префикса (не голая подстрока) -- позитив и негатив; границы нового
_strip_commit_messages (незакрытая кавычка, here-string, два -m,
крамола внутри/вне сообщения)."""

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


# ---------------------------------------------------------------------
# v2 -- живые false-positive (evidence задачи hygiene-gate-v2), дословно
# ---------------------------------------------------------------------


def test_v2_fp1_commit_message_mentions_orchestrator_log_and_arrow_no_warn():
    # FP-1 (2026-07-19): git commit, чьё СООБЩЕНИЕ упоминает
    # "orchestrator-log" и содержит `>` в тексте. Журнал никто не писал.
    command = (
        'git commit -m "Update orchestrator-log format: '
        'old-field -> new-field mapping documented"'
    )
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_fp2_commit_message_with_arrows_and_witness_no_warn():
    # FP-2 (2026-07-20), дословно: git add путём к logs/routing-log.jsonl
    # && git commit -m с многострочным сообщением (heredoc-форма, как
    # реально формируются коммиты этой сессией), стрелками '->' и словом
    # witness. Подстрока routing-log приходит из git add (путь-аргумент,
    # НЕ вырезается по спеке), '>' -- из стрелок ВНУТРИ сообщения
    # (вырезается) -- после вырезания индикатора записи не остаётся.
    command = (
        "git add scripts/board_sync.py state/rules.yaml logs/routing-log.jsonl "
        "&& git commit -m \"$(cat <<'EOF'\n"
        "fix: severity-дропдаун в board_sync.py -> корректный маппинг статусов\n"
        "witness: python -m pytest scripts/tests -q все зелёные\n"
        "EOF\n"
        ')"'
    )
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


# ---------------------------------------------------------------------
# v2 -- истинные срабатывания живы (не поломаны вырезателем/новым каноном)
# ---------------------------------------------------------------------


def test_v2_echo_redirect_routing_log_still_triggers():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("echo x > logs/routing-log.jsonl")
    )
    assert exit_code == 0
    assert output is not None
    assert hygiene_gate.MSG_JOURNAL_BYPASS in output["hookSpecificOutput"]["additionalContext"]


def test_v2_printf_append_routing_log_still_triggers():
    exit_code, output = hygiene_gate.decide(
        _bash_payload('printf "%s" "{}" >> logs/routing-log.jsonl')
    )
    assert exit_code == 0
    assert output is not None


def test_v2_add_content_orchestrator_log_still_triggers():
    exit_code, output = hygiene_gate.decide(
        _ps_payload('Add-Content state/orchestrator-log.md "| row |"')
    )
    assert exit_code == 0
    assert output is not None


# ---------------------------------------------------------------------
# v2 -- регресс на известный обход v1 (critic-находка): комментарий,
# упоминающий log_append.py БЕЗ префикс-формы вызова, больше НЕ гасит
# срабатывание.
# ---------------------------------------------------------------------


def test_v2_bypass_via_trailing_comment_now_triggers():
    # v1: подстрока "log_append.py" где угодно в команде гасила детект
    # -- этот комментарий проходил незамеченным. v2: канон -- форма
    # префикса, комментарий её не образует -> ТЕПЕРЬ warn (v2-фикс,
    # не регресс).
    exit_code, output = hygiene_gate.decide(
        _bash_payload("echo x > logs/routing-log.jsonl  # via log_append.py")
    )
    assert exit_code == 0
    assert output is not None
    assert hygiene_gate.MSG_JOURNAL_BYPASS in output["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------------
# v2 -- канонические формы по-прежнему без warn (форма префикса)
# ---------------------------------------------------------------------


def test_v2_canonical_routing_event_still_silent():
    exit_code, output = hygiene_gate.decide(
        _bash_payload(
            "python scripts/log_append.py routing --event delegated "
            "--agent builder --model sonnet --task-id t-050 "
            "--worker-ref cli:2026-07-20"
        )
    )
    assert exit_code == 0
    assert output is None


def test_v2_canonical_open_dispatches_still_silent():
    exit_code, output = hygiene_gate.decide(
        _bash_payload("python scripts/log_append.py open-dispatches")
    )
    assert exit_code == 0
    assert output is None


def test_v2_canonical_chain_after_git_pull_still_silent():
    # Цепочка через && -- канон разрешён СРАЗУ ПОСЛЕ разделителя, не
    # только в самом начале команды. Журнальная подстрока и индикатор
    # записи присутствуют (в --notes), но вызов -- канонический
    # префикс сразу после "&&" -> подавлено.
    command = (
        "git pull && python scripts/log_append.py routing --event delegated "
        '--agent builder --model sonnet --task-id t-050 '
        '--worker-ref cli:2026-07-20 --notes "backup copy > routing-log.jsonl.bak"'
    )
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_canonical_windows_backslash_path_still_silent():
    exit_code, output = hygiene_gate.decide(
        _ps_payload(r"python scripts\log_append.py open-dispatches")
    )
    assert exit_code == 0
    assert output is None


# ---------------------------------------------------------------------
# v2 -- границы нового вырезателя _strip_commit_messages
# ---------------------------------------------------------------------


def test_v2_unclosed_quote_in_message_not_stripped_detect_still_works():
    # Незакрытая кавычка в -m -- НЕ вырезаем (fail-safe в сторону
    # детекта): regex не матчит незакрытую форму, вся команда остаётся
    # как есть, и журнальная подстрока + индикатор записи в ней сами
    # по себе триггерят warn.
    command = 'git commit -m "unterminated message mentions routing-log > oops'
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is not None


def test_v2_powershell_herestring_message_fully_stripped_no_warn():
    command = (
        "git commit -m @'\n"
        "Update orchestrator-log.md format: old -> new mapping\n"
        "'@"
    )
    exit_code, output = hygiene_gate.decide(_ps_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_two_message_arguments_both_stripped_no_warn():
    command = (
        'git commit -m "first paragraph, clean" '
        '-m "second paragraph mentions routing-log and > arrow"'
    )
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_all_crapola_inside_message_no_warn():
    command = 'git commit -m "echo > logs/routing-log.jsonl"'
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_crapola_outside_message_still_triggers():
    command = 'git commit -m "x" && echo y > logs/routing-log.jsonl'
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is not None
    assert hygiene_gate.MSG_JOURNAL_BYPASS in output["hookSpecificOutput"]["additionalContext"]


def test_v2_single_quoted_message_stripped_no_warn():
    command = "git commit -m 'notes about routing-log.jsonl -> archived'"
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_message_flag_long_form_equals_form_stripped_no_warn():
    command = '''git commit --message="orchestrator-log rewritten, old -> new"'''
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is None


def test_v2_non_commit_git_command_not_scrubbed_still_triggers():
    # Вырезание применяется ТОЛЬКО к git commit -- у прочих git-команд
    # (или произвольных команд с "-m" в другом смысле) ничего не
    # трогаем; убеждаемся, что это не сломало обычный позитив.
    command = "echo x > logs/routing-log.jsonl"
    assert not hygiene_gate.GIT_COMMIT_RE.search(command)
    exit_code, output = hygiene_gate.decide(_bash_payload(command))
    assert exit_code == 0
    assert output is not None


# --- subprocess-уровень smoke для FP-2 и истинного срабатывания (DoD) ---


def test_echo_json_v2_fp2_payload_exit0_no_stdout():
    command = (
        "git add scripts/board_sync.py state/rules.yaml logs/routing-log.jsonl "
        "&& git commit -m \"$(cat <<'EOF'\n"
        "fix: severity-дропдаун в board_sync.py -> корректный маппинг статусов\n"
        "witness: python -m pytest scripts/tests -q все зелёные\n"
        "EOF\n"
        ')"'
    )
    payload = _bash_payload(command)
    result = _run_hook(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    assert result.returncode == 0
    assert result.stdout.strip() == b""
    assert result.stderr == b""


def test_echo_json_v2_true_positive_exit0_with_stdout_json():
    payload = _bash_payload("echo done > logs/routing-log.jsonl")
    result = _run_hook(json.dumps(payload), text=True, encoding="utf-8")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    hso = data["hookSpecificOutput"]
    assert "permissionDecision" not in hso
    assert hygiene_gate.MSG_JOURNAL_BYPASS in hso["additionalContext"]
