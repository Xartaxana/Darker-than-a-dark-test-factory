"""Тесты scripts/tier_measure.py -- замер фактической модели воркера по
jsonl-транскрипту (порт D-0083 OS-репо, tools/tier_echo.py)."""
from __future__ import annotations

import json

import tier_measure as tm


def _write_transcript(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _assistant(model):
    return {"type": "assistant", "message": {"model": model}}


def test_iter_transcript_models_single_model(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_transcript(path, [_assistant("opus"), _assistant("opus")])
    assert list(tm.iter_transcript_models(str(path))) == ["opus", "opus"]


def test_iter_transcript_models_multiple_models_preserves_order(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_transcript(path, [_assistant("fable"), _assistant("sonnet"),
                              _assistant("fable")])
    models = list(tm.iter_transcript_models(str(path)))
    assert models == ["fable", "sonnet", "fable"]


def test_iter_transcript_models_skips_synthetic(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_transcript(path, [_assistant("<synthetic>"), _assistant("opus")])
    assert list(tm.iter_transcript_models(str(path))) == ["opus"]


def test_iter_transcript_models_skips_non_assistant_and_missing_model(tmp_path):
    path = tmp_path / "t.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"model": "opus"}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {}}) + "\n")
        f.write(json.dumps({"type": "assistant"}) + "\n")
        f.write(json.dumps(_assistant("opus")) + "\n")
    assert list(tm.iter_transcript_models(str(path))) == ["opus"]


def test_iter_transcript_models_skips_broken_json_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write("{not valid json\n")
        f.write(json.dumps(_assistant("opus")) + "\n")
        f.write("\n")  # пустая строка
        f.write(json.dumps(_assistant("sonnet")) + "\n")
    assert list(tm.iter_transcript_models(str(path))) == ["opus", "sonnet"]


def test_count_models_preserves_first_appearance_order(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_transcript(path, [_assistant("fable"), _assistant("opus"),
                              _assistant("fable"), _assistant("opus"),
                              _assistant("opus")])
    counts = tm.count_models(tm.iter_transcript_models(str(path)))
    assert list(counts.items()) == [("fable", 2), ("opus", 3)]


def test_count_models_empty_iterable():
    assert tm.count_models([]) == {}


# find_worker_transcript ------------------------------------------------

def _make_fixture_transcript(tmp_path, agent_id):
    path = (tmp_path / "proj-a" / "session-1" / "subagents"
             / f"agent-{agent_id}.jsonl")
    _write_transcript(path, [_assistant("opus")])
    return path


def test_find_worker_transcript_async_prefix_finds_fixture(tmp_path, monkeypatch):
    agent_id = "a01d9bf5189387b76"
    expected = _make_fixture_transcript(tmp_path, agent_id)
    monkeypatch.setattr(tm, "_projects_dir", lambda: tmp_path, raising=True)
    found = tm.find_worker_transcript(f"async:{agent_id}")
    assert found == expected


def test_find_worker_transcript_agent_prefix_finds_fixture(tmp_path, monkeypatch):
    agent_id = "b02e8cf6290498c87"
    expected = _make_fixture_transcript(tmp_path, agent_id)
    monkeypatch.setattr(tm, "_projects_dir", lambda: tmp_path, raising=True)
    found = tm.find_worker_transcript(f"agent:{agent_id}")
    assert found == expected


def test_find_worker_transcript_other_prefixes_return_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "_projects_dir", lambda: tmp_path, raising=True)
    for ref in ("cli:2026-07-19T12:00:00", "lock:abc", "job:bg-4471",
                "retro:manual", "wr", "wr-A", ""):
        assert tm.find_worker_transcript(ref) is None


def test_find_worker_transcript_missing_id_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "_projects_dir", lambda: tmp_path, raising=True)
    assert tm.find_worker_transcript("agent:doesnotexist") is None


def test_find_worker_transcript_non_string_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "_projects_dir", lambda: tmp_path, raising=True)
    assert tm.find_worker_transcript(None) is None
    assert tm.find_worker_transcript(123) is None
