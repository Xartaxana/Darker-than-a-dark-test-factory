"""Юнит-тесты аудита permission-запросов (scripts/permission_audit.py).

Ничего не читает из реального ~/.claude/projects или .claude/settings.json:
модульные константы REPO/CLAUDE_PROJECTS подменяются на tmp_path.
"""
from __future__ import annotations

import json
import os
import time

import pytest

import permission_audit as pa


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Изолированный REPO (для .claude/settings*.json) + CLAUDE_PROJECTS (для транскриптов)."""
    monkeypatch.setattr(pa, "REPO", tmp_path, raising=True)
    monkeypatch.setattr(pa, "CLAUDE_PROJECTS", tmp_path / "projects", raising=True)
    return tmp_path


def _write_settings(root, name, allow):
    p = root / ".claude" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"permissions": {"allow": allow}}, ensure_ascii=False), encoding="utf-8")
    return p


def _write_transcript(root, name, records, *, subagent=False, agent_type=None, mtime=None):
    """Пишет jsonl-транскрипт. records — список (timestamp_iso|None, tool, cmd)."""
    if subagent:
        p = root / "projects" / "SESSION1" / "subagents" / name
    else:
        p = root / "projects" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for ts, tool, cmd in records:
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": tool, "input": {"command": cmd}}
                ]
            },
        }
        if ts is not None:
            obj["timestamp"] = ts
        lines.append(json.dumps(obj, ensure_ascii=False))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if subagent and agent_type is not None:
        meta = p.with_name(p.name.replace(".jsonl", ".meta.json"))
        meta.write_text(json.dumps({"agentType": agent_type}), encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


# --- load_allow_patterns -----------------------------------------------------

def test_load_allow_patterns_tool_with_pattern(env):
    _write_settings(env, "settings.json", ["Bash(npm test *)"])

    patterns = pa.load_allow_patterns()

    assert ("Bash", "npm test *") in patterns


def test_load_allow_patterns_bare_tool_name(env):
    _write_settings(env, "settings.json", ["WebSearch"])

    patterns = pa.load_allow_patterns()

    assert ("WebSearch", "") in patterns


def test_load_allow_patterns_both_files_merged(env):
    _write_settings(env, "settings.json", ["Bash(git status)"])
    _write_settings(env, "settings.local.json", ["Bash(adb *)"])

    patterns = pa.load_allow_patterns()

    assert ("Bash", "git status") in patterns
    assert ("Bash", "adb *") in patterns


def test_load_allow_patterns_missing_files_returns_empty(env):
    assert pa.load_allow_patterns() == []


def test_load_allow_patterns_broken_json_warns_and_skips(env, capsys):
    p = env / ".claude" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ не json совсем", encoding="utf-8")
    _write_settings(env, "settings.local.json", ["Bash(ls *)"])

    patterns = pa.load_allow_patterns()

    assert patterns == [("Bash", "ls *")]           # битый файл пропущен, второй прочитан
    err = capsys.readouterr().err
    assert "[warn]" in err and "settings.json" in err


# --- matches_allow ------------------------------------------------------------

def test_matches_allow_exact_match():
    patterns = [("Bash", "git status")]
    assert pa.matches_allow("Bash", "git status", patterns)


def test_matches_allow_prefix_star():
    patterns = [("Bash", "npm run *")]
    assert pa.matches_allow("Bash", "npm run build", patterns)
    assert not pa.matches_allow("Bash", "npm test", patterns)


def test_matches_allow_wrong_tool_no_match():
    patterns = [("Bash", "git status")]
    assert not pa.matches_allow("PowerShell", "git status", patterns)


def test_matches_allow_bare_tool_matches_any_command():
    patterns = [("WebSearch", "")]
    assert pa.matches_allow("WebSearch", "что угодно", patterns)


def test_matches_allow_no_pattern_at_all():
    assert not pa.matches_allow("Bash", "ls", [])


def test_matches_allow_fnmatch_glob():
    patterns = [("Bash", "*.sh")]
    assert pa.matches_allow("Bash", "build.sh", patterns)
    assert not pa.matches_allow("Bash", "build.py", patterns)


# --- is_auto_allowed -----------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "cat foo.txt",
    "grep -n foo bar.py",
    "git status",
    "git log --oneline",
    "cat foo.txt && grep bar baz.txt",
])
def test_auto_allowed_commands(cmd):
    assert pa.is_auto_allowed(cmd)


@pytest.mark.parametrize("cmd", [
    "npm test",
    "git push origin main",
    "python scripts/doctor.py",
    "cat foo.txt && npm test",   # цепочка — один непокрытый элемент валит всё
    "echo hi\necho bye",         # многострочная — не считается auto-allowed
])
def test_not_auto_allowed_commands(cmd):
    assert not pa.is_auto_allowed(cmd)


# --- sandbox_flags --------------------------------------------------------------

def test_sandbox_flags_command_substitution():
    flags = pa.sandbox_flags("echo $(date)")
    assert any("подстановка" in f for f in flags)


def test_sandbox_flags_for_loop():
    flags = pa.sandbox_flags("for f in *.txt; do cat $f; done")
    assert any("for" in f for f in flags)


def test_sandbox_flags_while_loop():
    flags = pa.sandbox_flags("while true; do sleep 1; done")
    assert any("while" in f for f in flags)


def test_sandbox_flags_nohup_and_background():
    flags = pa.sandbox_flags("nohup long_task &")
    joined = "; ".join(flags)
    assert "nohup" in joined
    assert any("&" in f for f in flags)


def test_sandbox_flags_multiline():
    flags = pa.sandbox_flags("echo one\necho two")
    assert any("многострочная" in f for f in flags)


def test_sandbox_flags_plain_command_is_clean():
    assert pa.sandbox_flags("ls -la") == []


# --- iter_tool_calls / collect_suspects (разбор транскрипта) --------------------

def test_collect_suspects_uncovered_command_is_flagged(env):
    _write_settings(env, "settings.json", ["Bash(git status)"])
    _write_transcript(env, "sessA.jsonl", [
        (None, "Bash", "git status"),      # покрыта allowlist
        (None, "Bash", "npm run deploy"),  # НЕ покрыта
    ])

    suspects, total = pa.collect_suspects(minutes=None)

    assert total == 2
    cmds = [s[3] for s in suspects]
    assert "npm run deploy" in cmds
    assert "git status" not in cmds


def test_collect_suspects_auto_allowed_not_in_report(env):
    _write_settings(env, "settings.json", [])
    _write_transcript(env, "sessB.jsonl", [
        (None, "Bash", "cat readme.md"),   # auto-allow, allowlist пуст
    ])

    suspects, _total = pa.collect_suspects(minutes=None)

    assert suspects == []


def test_collect_suspects_sandbox_flag_reported_even_if_allowed(env):
    # "npm" не входит ни в один auto-allow список, поэтому is_auto_allowed=False
    # и решает именно sandbox-эвристика (подстановка $(...) флагуется несмотря на allowlist).
    _write_settings(env, "settings.json", ["Bash(npm run deploy $(cat token) *)"])
    _write_transcript(env, "sessC.jsonl", [
        (None, "Bash", "npm run deploy $(cat token) hello"),
    ])

    suspects, _total = pa.collect_suspects(minutes=None)

    assert len(suspects) == 1
    reason = suspects[0][4]
    assert any("подстановка" in r for r in reason)


def test_collect_suspects_subagent_agent_type_from_meta(env):
    _write_settings(env, "settings.json", [])
    _write_transcript(env, "agent-1.jsonl", [
        (None, "Bash", "npm test"),
    ], subagent=True, agent_type="test-automator")

    suspects, _total = pa.collect_suspects(minutes=None)

    assert len(suspects) == 1
    assert suspects[0][1] == "test-automator"


def test_collect_suspects_minutes_filter_excludes_old_file(env):
    _write_settings(env, "settings.json", [])
    old_ts = time.time() - 3600 * 5   # 5 часов назад
    _write_transcript(env, "old.jsonl", [
        (None, "Bash", "npm run deploy"),
    ], mtime=old_ts)

    suspects, total = pa.collect_suspects(minutes=60)  # окно 1 час — файл старше, пропущен целиком

    assert total == 0
    assert suspects == []


def test_collect_suspects_all_flag_ignores_time_window(env):
    _write_settings(env, "settings.json", [])
    old_ts = time.time() - 3600 * 5
    _write_transcript(env, "old.jsonl", [
        (None, "Bash", "npm run deploy"),
    ], mtime=old_ts)

    suspects, total = pa.collect_suspects(minutes=None)   # аналог --all

    assert total == 1
    assert any(s[3] == "npm run deploy" for s in suspects)


def test_collect_suspects_timestamp_cutoff_within_fresh_file(env):
    _write_settings(env, "settings.json", [])
    from datetime import datetime, timedelta, timezone
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    fresh_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_transcript(env, "mixed.jsonl", [
        (old_iso, "Bash", "npm run old-deploy"),
        (fresh_iso, "Bash", "npm run fresh-deploy"),
    ])

    suspects, total = pa.collect_suspects(minutes=60)

    cmds = [s[3] for s in suspects]
    assert "npm run fresh-deploy" in cmds
    assert "npm run old-deploy" not in cmds
    assert total == 1


def test_collect_suspects_session_filter(env):
    _write_settings(env, "settings.json", [])
    _write_transcript(env, "agent-1.jsonl", [
        (None, "Bash", "npm run deploy"),
    ], subagent=True)

    matched, _ = pa.collect_suspects(minutes=None, session="SESSION1")
    unmatched, _ = pa.collect_suspects(minutes=None, session="OTHER-SESSION")

    assert len(matched) == 1
    assert unmatched == []
