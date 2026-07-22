"""Тесты scripts/escape_check.py — кросс-репо escape-allowlist чекер
(порт tools/escape_check.py OS-репо, задача os-port-0722)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import escape_check as ec

SCRIPT_PATH = Path(ec.__file__).resolve()


def _write(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)


# ---------------------------------------------------------------------------
# section extraction / hashing (legs (b)/(c) machinery)
# ---------------------------------------------------------------------------

def test_extract_decision_section_basic_and_boundary():
    text = ("intro\n## D-0001\nbody line 1\nbody line 2\n\n## D-0002\nother\n")
    section, status = ec.extract_decision_section(text, "D-0001")
    assert status == "ok"
    assert section == "## D-0001\nbody line 1\nbody line 2"

    # boundary: D-00011 (extra digit) and D-0001b (extra letter) must NOT
    # match the D-0001 opener pattern.
    text2 = "## D-00011\nfoo\n## D-0001b\nbar\n"
    _, status2 = ec.extract_decision_section(text2, "D-0001")
    assert status2 == "not_found"


def test_extract_decision_section_not_found_and_duplicate():
    _, status = ec.extract_decision_section("no sections here\n", "D-0001")
    assert status == "not_found"

    dup_text = "## D-0001\na\n## D-0001\nb\n"
    _, status = ec.extract_decision_section(dup_text, "D-0001")
    assert status == "duplicate"


def test_extract_decision_section_trims_trailing_blank_lines_only():
    text = "## D-0001\nline1\n\n\n## D-0002\n"
    section, status = ec.extract_decision_section(text, "D-0001")
    assert status == "ok"
    assert section == "## D-0001\nline1"


def test_section_sha256_stable_across_crlf_and_lf():
    lf_text = "## D-0001\nfoo\nbar\n"
    crlf_text = "## D-0001\r\nfoo\r\nbar\r\n"
    digest_lf, status_lf = ec.section_sha256(lf_text, "D-0001")
    digest_crlf, status_crlf = ec.section_sha256(crlf_text, "D-0001")
    assert status_lf == status_crlf == "ok"
    assert digest_lf == digest_crlf


def test_fold_whitespace_bridges_a_line_wrap_inside_the_anchor():
    # F-30/N4 class: an anchor phrase reflowed across a line break in the
    # carrier must still be found by leg (a).
    carrier = "before text\nself-execution with a skip event\nis legal only here\nafter text\n"
    anchor = "self-execution with a skip event is legal only here"
    assert ec._fold_whitespace(anchor) in ec._fold_whitespace(carrier)


# ---------------------------------------------------------------------------
# entry schema validation
# ---------------------------------------------------------------------------

def _valid_entry(**overrides):
    entry = {
        "id": "sample-entry",
        "carrier_file": "CLAUDE.md",
        "carrier_anchor": "the concession phrase",
        "decision_id": "D-0001",
        "decision_file": "DECISIONS_FULL.md",
        "section_sha256": "a" * 64,
        "affirmed": "2026-07-22",
    }
    entry.update(overrides)
    return entry


def test_validate_entry_schema_missing_required_fields():
    errors = ec.validate_entry_schema({"id": "x"}, 0)
    assert any("carrier_file" in e for e in errors)
    assert any("decision_id" in e for e in errors)


def test_validate_entry_schema_decision_id_format():
    errors = ec.validate_entry_schema(_valid_entry(decision_id="D-58"), 0)
    assert any("decision_id" in e for e in errors)
    errors = ec.validate_entry_schema(_valid_entry(decision_id="D-0058"), 0)
    assert errors == []


def test_validate_entry_schema_sha256_format():
    errors = ec.validate_entry_schema(_valid_entry(section_sha256="not-hex"), 0)
    assert any("section_sha256" in e for e in errors)
    errors = ec.validate_entry_schema(_valid_entry(section_sha256="A" * 64), 0)
    # uppercase hex is rejected -- schema requires lowercase
    assert any("section_sha256" in e for e in errors)


def test_validate_entry_schema_affirmed_calendar_date():
    errors = ec.validate_entry_schema(_valid_entry(affirmed="2026-13-40"), 0)
    assert any("affirmed" in e for e in errors)
    errors = ec.validate_entry_schema(_valid_entry(affirmed="not-a-date"), 0)
    assert any("affirmed" in e for e in errors)


def test_validate_entry_schema_whitespace_only_anchor_rejected():
    errors = ec.validate_entry_schema(_valid_entry(carrier_anchor="   \n\t  "), 0)
    assert any("carrier_anchor" in e and "non-whitespace" in e for e in errors)


def test_validate_entry_schema_not_an_object():
    errors = ec.validate_entry_schema(["not", "a", "dict"], 2)
    assert any("entries[2]" in e for e in errors)


# ---------------------------------------------------------------------------
# check_entry_legs / run_validate -- the three legs against a live tree
# ---------------------------------------------------------------------------

def test_check_entry_legs_all_pass(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "prefix\nthe concession phrase\nsuffix\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    section_text = "## D-0001\nauthorizing text\n"
    _write(decision, "intro\n" + section_text)
    digest, status = ec.section_sha256(decision.read_text(encoding="utf-8"), "D-0001")
    assert status == "ok"

    entry = _valid_entry(section_sha256=digest)
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert errors == []
    assert warnings == []


def test_check_entry_legs_anchor_reflowed_across_lines_still_passes(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "before\nthe concession\nphrase\nafter\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\nauthorizing text\n")
    digest, _ = ec.section_sha256(decision.read_text(encoding="utf-8"), "D-0001")

    entry = _valid_entry(carrier_anchor="the concession phrase", section_sha256=digest)
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert errors == []


def test_check_entry_legs_dead_carrier_anchor_fails_closed(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "nothing relevant here\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\nauthorizing text\n")
    digest, _ = ec.section_sha256(decision.read_text(encoding="utf-8"), "D-0001")

    entry = _valid_entry(section_sha256=digest)
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert any("carrier leg failed" in e for e in errors)
    assert warnings == []


def test_check_entry_legs_missing_decision_file_is_warning_not_error(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    entry = _valid_entry(decision_file="does-not-exist.md")
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert errors == []
    assert len(warnings) == 1
    assert "ESCAPE WARNING: decision file unreachable" in warnings[0]


def test_check_entry_legs_missing_decision_file_absolute_path_is_also_warning(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    missing_abs = str(tmp_path / "nope" / "DECISIONS_FULL.md")
    entry = _valid_entry(decision_file=missing_abs)
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert errors == []
    assert len(warnings) == 1


def test_check_entry_legs_section_not_found_fails_closed(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-9999\nunrelated\n")
    entry = _valid_entry()
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert any("section D-0001 not found" in e for e in errors)
    assert warnings == []


def test_check_entry_legs_section_duplicate_fails_closed(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\na\n## D-0001\nb\n")
    entry = _valid_entry()
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert any("duplicated" in e for e in errors)


def test_check_entry_legs_hash_mismatch_fails_closed(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\nauthorizing text\n")
    entry = _valid_entry(section_sha256="f" * 64)
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert any("hash leg failed" in e for e in errors)


def test_check_entry_legs_non_utf8_carrier_fails_closed(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    carrier.write_bytes(b"\xff\xfe\x00broken")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\nauthorizing text\n")
    entry = _valid_entry()
    errors, warnings = ec.check_entry_legs(entry, str(tmp_path))
    assert any("not valid UTF-8" in e for e in errors)


# ---------------------------------------------------------------------------
# run_validate: whole-allowlist adversarial battery
# ---------------------------------------------------------------------------

def _seed_repo(tmp_path, entry_extra=None):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\nauthorizing text\n")
    digest, _ = ec.section_sha256(decision.read_text(encoding="utf-8"), "D-0001")
    entry = _valid_entry(section_sha256=digest)
    if entry_extra:
        entry.update(entry_extra)
    allowlist = tmp_path / "escape_allowlist.json"
    _write(allowlist, json.dumps({"entries": [entry]}, ensure_ascii=False))
    return allowlist


def test_run_validate_ok(tmp_path):
    allowlist = _seed_repo(tmp_path)
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is True
    assert errors == []
    assert warnings == []
    assert count == 1


def test_run_validate_empty_file_is_invalid_json(tmp_path):
    allowlist = tmp_path / "escape_allowlist.json"
    _write(allowlist, "")
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is False
    assert any("invalid JSON" in e for e in errors)


def test_run_validate_missing_allowlist_file(tmp_path):
    ok, errors, warnings, count = ec.run_validate(str(tmp_path / "nope.json"), str(tmp_path))
    assert ok is False
    assert any("cannot read file" in e for e in errors)


def test_run_validate_broken_json(tmp_path):
    allowlist = tmp_path / "escape_allowlist.json"
    _write(allowlist, "{not json")
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is False
    assert any("invalid JSON" in e for e in errors)


def test_run_validate_non_utf8_allowlist_bytes(tmp_path):
    allowlist = tmp_path / "escape_allowlist.json"
    allowlist.write_bytes(b"\xff\xfe{}")
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is False
    assert any("not valid UTF-8" in e for e in errors)


def test_run_validate_root_not_object(tmp_path):
    allowlist = tmp_path / "escape_allowlist.json"
    _write(allowlist, "[]")
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is False
    assert any("not an object" in e for e in errors)


def test_run_validate_entries_not_a_list(tmp_path):
    allowlist = tmp_path / "escape_allowlist.json"
    _write(allowlist, json.dumps({"entries": "nope"}))
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is False
    assert any("must be an array" in e for e in errors)


def test_run_validate_duplicate_entry_ids(tmp_path):
    carrier = tmp_path / "CLAUDE.md"
    _write(carrier, "the concession phrase\n")
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0001\nauthorizing text\n")
    digest, _ = ec.section_sha256(decision.read_text(encoding="utf-8"), "D-0001")
    e1 = _valid_entry(section_sha256=digest)
    e2 = _valid_entry(section_sha256=digest)
    allowlist = tmp_path / "escape_allowlist.json"
    _write(allowlist, json.dumps({"entries": [e1, e2]}, ensure_ascii=False))
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is False
    assert any("duplicate entry id" in e for e in errors)


def test_run_validate_cyrillic_note_and_anchor_do_not_break_ascii_diagnostics(tmp_path):
    # Cyrillic in a NON-blocking field (note) must not appear verbatim in
    # a diagnostic that references it via the entry id -- but the run
    # itself must not crash, and any interpolated dynamic value used as a
    # diagnostic parameter stays ASCII (ascii()-escaped).
    allowlist = _seed_repo(tmp_path, entry_extra={
        "id": "запись-с-кириллицей",
        "note": "кириллическая заметка",
    })
    ok, errors, warnings, count = ec.run_validate(str(allowlist), str(tmp_path))
    assert ok is True  # legs still pass; only the id changed
    for w in warnings:
        assert w.isascii()
    for e in errors:
        assert e.isascii()


# ---------------------------------------------------------------------------
# CLI surface (main): no-args validate mode, --hash mode, usage errors
# ---------------------------------------------------------------------------

def test_main_validate_mode_ok(tmp_path, monkeypatch, capsys):
    allowlist = _seed_repo(tmp_path)
    monkeypatch.setattr(ec, "ALLOWLIST_PATH", str(allowlist), raising=True)
    monkeypatch.setattr(ec, "REPO_ROOT", str(tmp_path), raising=True)
    code = ec.main(["escape_check.py"])
    out = capsys.readouterr().out
    assert code == 0
    assert "ESCAPE ALLOWLIST OK: 1 entries" in out


def test_main_validate_mode_fails_closed_on_hash_drift(tmp_path, monkeypatch, capsys):
    allowlist = _seed_repo(tmp_path, entry_extra={"section_sha256": "b" * 64})
    monkeypatch.setattr(ec, "ALLOWLIST_PATH", str(allowlist), raising=True)
    monkeypatch.setattr(ec, "REPO_ROOT", str(tmp_path), raising=True)
    code = ec.main(["escape_check.py"])
    err = capsys.readouterr().err
    assert code == 1
    assert "ESCAPE ALLOWLIST INVALID" in err


def test_main_validate_mode_prints_warning_for_unreachable_decision_and_still_exits_0(
    tmp_path, monkeypatch, capsys
):
    allowlist = _seed_repo(tmp_path, entry_extra={"decision_file": "gone.md"})
    monkeypatch.setattr(ec, "ALLOWLIST_PATH", str(allowlist), raising=True)
    monkeypatch.setattr(ec, "REPO_ROOT", str(tmp_path), raising=True)
    code = ec.main(["escape_check.py"])
    out = capsys.readouterr().out
    assert code == 0
    assert "ESCAPE WARNING: decision file unreachable" in out
    assert "ESCAPE ALLOWLIST OK: 1 entries" in out


def test_main_hash_mode_ok_and_matches_section_sha256(tmp_path, capsys):
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0007\nsome text\n")
    code = ec.main(["escape_check.py", "--hash", "D-0007", "--file", str(decision)])
    out = capsys.readouterr().out.strip()
    assert code == 0
    expected, _ = ec.section_sha256(decision.read_text(encoding="utf-8"), "D-0007")
    assert out == expected


def test_main_hash_mode_not_found_and_duplicate(tmp_path, capsys):
    decision = tmp_path / "DECISIONS_FULL.md"
    _write(decision, "## D-0007\ntext\n")
    code = ec.main(["escape_check.py", "--hash", "D-9999", "--file", str(decision)])
    assert code == 1
    assert "not found" in capsys.readouterr().err

    _write(decision, "## D-0007\na\n## D-0007\nb\n")
    code = ec.main(["escape_check.py", "--hash", "D-0007", "--file", str(decision)])
    assert code == 1
    assert "duplicated" in capsys.readouterr().err


def test_main_hash_mode_unreadable_file(tmp_path, capsys):
    code = ec.main(["escape_check.py", "--hash", "D-0007", "--file", str(tmp_path / "nope.md")])
    assert code == 1
    assert "ESCAPE HASH FAILED" in capsys.readouterr().err


def test_main_usage_errors():
    assert ec.main(["escape_check.py", "--bogus"]) == 2
    assert ec.main(["escape_check.py", "--hash", "D-0001"]) == 2
    assert ec.main(["escape_check.py", "--hash", "D-0001", "--file"]) == 2


# ---------------------------------------------------------------------------
# real seed: the checked-in scripts/escape_allowlist.json against the live
# tree (positive run + a witness that the CLI subprocess itself is green)
# ---------------------------------------------------------------------------

def test_real_seed_allowlist_validates_against_the_live_tree():
    ok, errors, warnings, count = ec.run_validate(
        str(SCRIPT_PATH.parent / "escape_allowlist.json"),
        str(SCRIPT_PATH.parent.parent),
    )
    assert ok is True, errors
    assert count >= 1


def test_cli_subprocess_smoke():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(SCRIPT_PATH.parent.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0
    assert "ESCAPE ALLOWLIST OK" in proc.stdout
