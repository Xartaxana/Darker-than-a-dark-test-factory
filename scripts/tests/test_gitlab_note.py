"""Тесты scripts/gitlab_note.py — границы CLI, [qa]-префикс, гейт эхо-класса."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gitlab_note as gn  # noqa: E402
import gitlab_sync as gs  # noqa: E402


# --- build_note_body ---

def test_body_gets_qa_prefix():
    assert gn.build_note_body("вопрос про стори").startswith("[qa] ")


def test_body_existing_prefix_not_doubled():
    body = gn.build_note_body("[qa] уже помечено")
    assert body == "[qa] уже помечено"


@pytest.mark.parametrize("bad", ["", "   ", "\n\t", None])
def test_body_empty_rejected(bad):
    with pytest.raises(ValueError):
        gn.build_note_body(bad)


def test_body_cyrillic_and_size_survive():
    text = "кириллица Ё → длинный текст " * 200
    body = gn.build_note_body(text)
    assert "кириллица Ё" in body and len(body) > 4000


# --- CLI границы (офлайн, до сети) ---

def test_cli_iid_zero_rejected(capsys):
    assert gn.main(["0", "--text", "x"]) == 1
    assert "iid" in capsys.readouterr().err


def test_cli_iid_non_numeric_rejected():
    with pytest.raises(SystemExit):
        gn.main(["abc", "--text", "x"])


def test_cli_text_and_file_mutually_exclusive(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("текст", encoding="utf-8")
    with pytest.raises(SystemExit):
        gn.main(["5", "--text", "x", "--text-file", str(f)])


def test_cli_missing_text_file(capsys):
    assert gn.main(["5", "--text-file", "нет-такого-файла.txt"]) == 1
    assert "не найден" in capsys.readouterr().err


def test_cli_empty_text_rejected(capsys):
    assert gn.main(["5", "--text", "   "]) == 1


# --- гейт эхо-класса + dry-run ---

def test_bug_iid_gated_before_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(gn, "bug_owning_iid", lambda iid: "BUG-019")
    assert gn.main(["10", "--text", "нота", "--dry-run"]) == 1
    assert "BUG-019" in capsys.readouterr().err


def test_dry_run_prints_payload_without_token(monkeypatch, capsys):
    monkeypatch.setattr(gn, "bug_owning_iid", lambda iid: None)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert gn.main(["42", "--text", "вопрос про стори", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "/issues/42/notes" in out and "[qa] вопрос про стори" in out


def test_no_token_exit_2(monkeypatch, capsys):
    monkeypatch.setattr(gn, "bug_owning_iid", lambda iid: None)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    assert gn.main(["42", "--text", "нота"]) == 2
    assert "GITLAB_TOKEN" in capsys.readouterr().err


# --- bug_owning_iid против реального bugs/ ---

def test_bug_owning_iid_finds_known_bug():
    # BUG-019 несёт gitlab_issue: 10 (живой факт репозитория; при переезде
    # номера тест чинится вместе с багом)
    assert gn.bug_owning_iid(10) == "BUG-019"


def test_bug_owning_iid_free_iid_is_none():
    taken = set()
    for path in gs.discover_bugs():
        try:
            meta, _ = gs.load_bug(path)
            taken.add(int(str(meta.get("gitlab_issue", "")).strip() or 0))
        except (gs.BugSyncError, ValueError):
            continue
    free = max(taken) + 1000
    assert gn.bug_owning_iid(free) is None


# --- post_note payload ---

class _FakeClient:
    """Повторяет контракт GitLabClient.post: кортеж (status, parsed)."""

    def __init__(self):
        self.calls = []

    def post(self, path, json_body):
        self.calls.append((path, json_body))
        return 201, {"id": 777}


def test_post_note_path_and_body():
    c = _FakeClient()
    note = gn.post_note(c, 42, "[qa] тело")
    assert c.calls == [("/issues/42/notes", {"body": "[qa] тело"})]
    assert note["id"] == 777
