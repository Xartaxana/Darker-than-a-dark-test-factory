"""Тесты scripts/critic_verdict_check.py — машиночитаемый вердикт критика
(порт tools/critic_verdict_check.py OS-репо, задача os-port-0722; enum
русский, дословно из .claude/agents/critic.md правило 6 — адаптация,
не отступление)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import critic_verdict_check as cvc

SCRIPT_PATH = Path(cvc.__file__).resolve()


def _fence(obj) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False) + "\n```"


def _valid_verdict(**overrides):
    obj = {
        "verdict": "ПРИНЯТЬ",
        "blockers": [],
        "class_completeness": "покрыта ось 6",
        "trail": {"read": ["scripts/foo.py"], "reruns": []},
    }
    obj.update(overrides)
    return obj


# ---------------------------------------------------------------------------
# fence extraction
# ---------------------------------------------------------------------------

def test_extract_last_json_block_none_when_absent():
    assert cvc.extract_last_json_block("just prose, no fences here") is None


def test_extract_last_json_block_single():
    text = "some text before\n" + _fence({"a": 1}) + "\nafter"
    block = cvc.extract_last_json_block(text)
    assert json.loads(block) == {"a": 1}


def test_extract_last_json_block_picks_the_last_of_two():
    text = _fence({"a": 1}) + "\nmiddle\n" + _fence({"a": 2})
    block = cvc.extract_last_json_block(text)
    assert json.loads(block) == {"a": 2}


def test_extract_last_json_block_not_last_element_still_found():
    # spec: "блок не последний (валидируется именно последний)" -- trailing
    # prose AFTER the fenced block must not prevent extraction of that block.
    text = _fence({"a": 1}) + "\nP.S. do not forget to deploy\n"
    block = cvc.extract_last_json_block(text)
    assert json.loads(block) == {"a": 1}


def test_extract_last_json_block_case_sensitive_label_not_recognized():
    text = "```JSON\n{\"a\": 1}\n```"
    assert cvc.extract_last_json_block(text) is None
    text2 = "```Json\n{\"a\": 1}\n```"
    assert cvc.extract_last_json_block(text2) is None


def test_extract_last_json_block_unclosed_fence_not_recognized():
    text = "```json\n{\"a\": 1}\nno closing fence"
    assert cvc.extract_last_json_block(text) is None


def test_extract_last_json_block_bare_fence_opener_not_recognized():
    text = "```\n{\"a\": 1}\n```"
    assert cvc.extract_last_json_block(text) is None


# ---------------------------------------------------------------------------
# validate_verdict -- schema rules, Russian enum adaptation
# ---------------------------------------------------------------------------

def test_validate_verdict_minimal_prinyat_ok():
    assert cvc.validate_verdict(_valid_verdict()) == []


def test_validate_verdict_root_not_object():
    errors = cvc.validate_verdict(["not", "an", "object"])
    assert any("not an object" in e for e in errors)


def test_validate_verdict_missing_required_top_fields():
    errors = cvc.validate_verdict({})
    for field in ("verdict", "blockers", "class_completeness", "trail"):
        assert any(field in e for e in errors)


def test_validate_verdict_english_enum_is_rejected():
    # adaptation guard: the OS original's English words must NOT validate --
    # a single dictionary, no silent backward-compat mapping.
    errors = cvc.validate_verdict(_valid_verdict(verdict="fit"))
    assert any("verdict" in e for e in errors)


def test_validate_verdict_prinyat_requires_empty_blockers():
    errors = cvc.validate_verdict(_valid_verdict(blockers=["something"]))
    assert any("blockers" in e and "PRINYAT" in e for e in errors)


def test_validate_verdict_otkloniti_requires_nonempty_blockers():
    errors = cvc.validate_verdict(_valid_verdict(verdict="ОТКЛОНИТЬ", blockers=[]))
    assert any("blockers" in e and "OTKLONIT" in e for e in errors)
    ok = cvc.validate_verdict(_valid_verdict(verdict="ОТКЛОНИТЬ", blockers=["reason"]))
    assert ok == []


def test_validate_verdict_dorabotat_requires_nonempty_fixes():
    errors = cvc.validate_verdict(_valid_verdict(verdict="ДОРАБОТАТЬ", blockers=[]))
    assert any("fixes" in e for e in errors)
    errors = cvc.validate_verdict(_valid_verdict(verdict="ДОРАБОТАТЬ", blockers=[], fixes=[]))
    assert any("fixes" in e and "non-empty" in e for e in errors)
    errors = cvc.validate_verdict(
        _valid_verdict(verdict="ДОРАБОТАТЬ", blockers=[], fixes="not-a-list"))
    assert any("fixes" in e for e in errors)
    ok = cvc.validate_verdict(_valid_verdict(verdict="ДОРАБОТАТЬ", blockers=[], fixes=["do X"]))
    assert ok == []


def test_validate_verdict_blockers_must_be_string_list():
    errors = cvc.validate_verdict(_valid_verdict(blockers=[1, 2]))
    assert any("blockers" in e for e in errors)
    errors = cvc.validate_verdict(_valid_verdict(blockers="not-a-list"))
    assert any("blockers" in e for e in errors)


def test_validate_verdict_class_completeness_must_be_string():
    errors = cvc.validate_verdict(_valid_verdict(class_completeness=123))
    assert any("class_completeness" in e for e in errors)


def test_validate_verdict_trail_must_be_object_with_read_and_reruns():
    errors = cvc.validate_verdict(_valid_verdict(trail="not-an-object"))
    assert any("trail" in e for e in errors)

    errors = cvc.validate_verdict(_valid_verdict(trail={"reruns": []}))
    assert any("trail.read" in e for e in errors)

    errors = cvc.validate_verdict(_valid_verdict(trail={"read": []}))
    assert any("trail.reruns" in e for e in errors)

    errors = cvc.validate_verdict(_valid_verdict(trail={"read": "not-a-list", "reruns": []}))
    assert any("trail.read" in e for e in errors)


def test_validate_verdict_trail_reruns_items_need_command_and_result():
    errors = cvc.validate_verdict(_valid_verdict(
        trail={"read": [], "reruns": [{"command": "pytest -q"}]}))
    assert any("reruns[0]" in e and "result" in e for e in errors)

    errors = cvc.validate_verdict(_valid_verdict(
        trail={"read": [], "reruns": ["not-a-dict"]}))
    assert any("reruns[0]" in e and "must be an object" in e for e in errors)

    ok = cvc.validate_verdict(_valid_verdict(
        trail={"read": [], "reruns": [{"command": "pytest -q", "result": "5 passed"}]}))
    assert ok == []


def test_validate_verdict_fixes_optional_field_type_checked_even_off_dorabotat():
    errors = cvc.validate_verdict(_valid_verdict(fixes="not-a-list"))
    assert any("fixes" in e for e in errors)
    ok = cvc.validate_verdict(_valid_verdict(fixes=["optional extra note"]))
    assert ok == []


# ---------------------------------------------------------------------------
# check_text: full pipeline
# ---------------------------------------------------------------------------

def test_check_text_no_block():
    ok, errors, obj = cvc.check_text("no fenced block anywhere")
    assert ok is False
    assert obj is None
    assert any("no fenced" in e for e in errors)


def test_check_text_invalid_json_in_block():
    ok, errors, obj = cvc.check_text("```json\n{not json\n```")
    assert ok is False
    assert obj is None
    assert any("invalid JSON" in e for e in errors)


def test_check_text_valid_full_message():
    text = ("Текстовый вердикт: ПРИНЯТЬ, находок нет.\n\n" +
             _fence(_valid_verdict()))
    ok, errors, obj = cvc.check_text(text)
    assert ok is True
    assert errors == []
    assert obj["verdict"] == "ПРИНЯТЬ"


def test_check_text_two_blocks_first_invalid_last_valid_uses_last():
    text = "```json\n{broken\n```\nmiddle text\n" + _fence(_valid_verdict())
    ok, errors, obj = cvc.check_text(text)
    assert ok is True
    assert obj["verdict"] == "ПРИНЯТЬ"


# ---------------------------------------------------------------------------
# CLI: files, stdin, adversarial battery
# ---------------------------------------------------------------------------

def test_main_usage_error_wrong_argc(capsys):
    assert cvc.main(["prog"]) == 1
    assert cvc.main(["prog", "a", "b"]) == 1
    assert "usage" in capsys.readouterr().err


def test_main_file_not_found(capsys):
    code = cvc.main(["prog", "/does/not/exist.txt"])
    assert code == 1
    assert "cannot read input file" in capsys.readouterr().err


def test_main_empty_file_no_block(tmp_path, capsys):
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    code = cvc.main(["prog", str(p)])
    assert code == 1
    assert "no fenced" in capsys.readouterr().err


def test_main_broken_json_in_file(tmp_path, capsys):
    p = tmp_path / "broken.txt"
    p.write_text("```json\n{oops\n```", encoding="utf-8")
    code = cvc.main(["prog", str(p)])
    assert code == 1
    assert "INVALID VERDICT" in capsys.readouterr().err


def test_main_non_utf8_bytes_in_file(tmp_path, capsys):
    p = tmp_path / "bin.txt"
    p.write_bytes(b"\xff\xfe" + _fence(_valid_verdict()).encode("utf-8"))
    code = cvc.main(["prog", str(p)])
    assert code == 1
    assert "not valid UTF-8" in capsys.readouterr().err


def test_main_valid_file_ok(tmp_path, capsys):
    p = tmp_path / "good.txt"
    p.write_text(_fence(_valid_verdict()), encoding="utf-8")
    code = cvc.main(["prog", str(p)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == "VERDICT OK: ПРИНЯТЬ, blockers: 0, fixes: 0"


def test_main_reads_stdin_dash(monkeypatch, capsys):
    text = _fence(_valid_verdict(verdict="ДОРАБОТАТЬ", blockers=[], fixes=["fix A"]))

    class _FakeBuffer:
        def read(self):
            return text.encode("utf-8")

    class _FakeStdin:
        buffer = _FakeBuffer()

    monkeypatch.setattr(cvc.sys, "stdin", _FakeStdin(), raising=True)
    code = cvc.main(["prog", "-"])
    out = capsys.readouterr().out
    assert code == 0
    assert "ДОРАБОТАТЬ" in out
    assert "fixes: 1" in out


def test_main_stdin_non_utf8_bytes(monkeypatch, capsys):
    class _FakeBuffer:
        def read(self):
            return b"\xff\xfe not utf8"

    class _FakeStdin:
        buffer = _FakeBuffer()

    monkeypatch.setattr(cvc.sys, "stdin", _FakeStdin(), raising=True)
    code = cvc.main(["prog", "-"])
    assert code == 1
    assert "not valid UTF-8" in capsys.readouterr().err


def test_main_dedupes_to_last_block_and_ignores_trailing_prose(tmp_path, capsys):
    text = (_fence(_valid_verdict(verdict="ОТКЛОНИТЬ", blockers=["bad thing"])) +
            "\n\nAppendix: this note comes after the block\n")
    p = tmp_path / "trailing.txt"
    p.write_text(text, encoding="utf-8")
    code = cvc.main(["prog", str(p)])
    out = capsys.readouterr().out
    assert code == 0
    assert "ОТКЛОНИТЬ" in out


def test_main_cyrillic_output_survives_narrow_console_codepage(tmp_path):
    # spec: "Вывод устойчив к кириллице на Windows-консоли" -- run as a
    # real subprocess with a narrow legacy codepage forced via env, and
    # confirm the process does not crash and the Cyrillic verdict word
    # makes it to stdout (main() reconfigures stdout to utf-8/replace
    # before writing, closing the class of UnicodeEncodeError risk that
    # scripts/log_append.py documents for its own equivalent print()).
    p = tmp_path / "good.txt"
    p.write_text(_fence(_valid_verdict()), encoding="utf-8")
    env = {"PYTHONIOENCODING": "cp1251:strict"}
    import os
    full_env = dict(os.environ)
    full_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(p)],
        capture_output=True, env=full_env,
    )
    assert proc.returncode == 0
    stdout_text = proc.stdout.decode("utf-8", errors="replace")
    assert "ПРИНЯТЬ" in stdout_text


# ---------------------------------------------------------------------------
# anti-drift: this file's hardcoded rules vs the reference JSON schema
# ---------------------------------------------------------------------------

def test_schema_file_enum_matches_hardcoded_verdict_enum():
    schema_path = SCRIPT_PATH.parent.parent / "schemas" / "critic-verdict.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert tuple(schema["properties"]["verdict"]["enum"]) == cvc.VERDICT_ENUM


def test_schema_file_required_top_fields_match_hardcoded_rules():
    schema_path = SCRIPT_PATH.parent.parent / "schemas" / "critic-verdict.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert set(schema["required"]) == {"verdict", "blockers", "class_completeness", "trail"}


def test_critic_agent_md_has_the_verdict_block_rule():
    agent_path = SCRIPT_PATH.parent.parent / ".claude" / "agents" / "critic.md"
    text = agent_path.read_text(encoding="utf-8")
    assert "```json" in text
    assert "verdict_check.py" in text
    # frontmatter model must be left untouched by this port (manifest owns
    # only the body; parity test S2 reads model: opus from frontmatter).
    assert text.splitlines()[0] == "---"
    assert "model: opus" in text.split("---")[1]


def test_cli_subprocess_smoke_positive_and_negative(tmp_path):
    good = tmp_path / "good.txt"
    good.write_text(_fence(_valid_verdict()), encoding="utf-8")
    proc_ok = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(good)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc_ok.returncode == 0
    assert "VERDICT OK" in proc_ok.stdout

    bad = tmp_path / "bad.txt"
    bad.write_text("no fenced block here at all", encoding="utf-8")
    proc_bad = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(bad)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc_bad.returncode == 1
    assert "INVALID VERDICT" in proc_bad.stderr
