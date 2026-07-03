"""Фикстуры для юнит-тестов обвязки борды (board_inbound).

Тесты работают в изолированном tmp_path-репо: мини-артефакты (bugs/, test-cases/,
runs/) + мини-board/ + state/board-cursor.json. НИКОГДА не трогают реальные bugs/.
Достигается монкипатчем модульных путей board_sync (bs.REPO/bs.BOARD) и board_inbound
(bi.BOARD/bi.CURSOR_PATH/bi.ESCALATIONS_PATH) на tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# scripts/ на sys.path — там board_sync/board_inbound (import board_sync as bs).
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import board_sync as bs          # noqa: E402
import board_inbound as bi       # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Repo:
    """Управляемое мини-репо в tmp_path. Позволяет складывать артефакты, борду,
    курсор и комментарии, потом запускать board_inbound.reconcile()."""

    def __init__(self, root: Path):
        self.root = root
        (root / "state").mkdir(parents=True, exist_ok=True)

    # --- артефакты (источник правды) ---
    def bug(self, key: str, status: str, *, extra: str = "", discussion: str | None = None) -> Path:
        body = "\n## Обсуждение\n\n" + discussion if discussion is not None else ""
        text = (
            f"---\n"
            f"id: {key}\n"
            f"title: Тестовый баг {key}\n"
            f"severity: major\n"
            f"status: {status}\n"
            f"{extra}"
            f"updated: \"2026-07-01T00:00:00Z\"\n"
            f"lock: \"\"\n"
            f"---\n\n# {key}\n\nтело{body}\n"
        )
        p = self.root / "bugs" / f"{key}.md"
        _write(p, text)
        return p

    def test_case(self, key: str, status: str) -> Path:
        text = (
            f"---\nid: {key}\ntitle: TC {key}\npriority: P1\nstatus: {status}\n"
            f"updated: \"2026-07-01T00:00:00Z\"\n---\n\n# {key}\n\nтело\n"
        )
        p = self.root / "test-cases" / f"{key}.md"
        _write(p, text)
        return p

    # --- board/<KEY>/main.md (status = id TrackState) ---
    def board_card(self, key: str, itype: str, our_status: str) -> Path:
        status_id = bs.STATUS_MAP[itype][our_status]
        text = (
            f"---\nkey: \"{key}\"\nissueType: \"{itype}\"\nstatus: \"{status_id}\"\n---\n\n# {key}\n"
        )
        p = self.root / "board" / key / "main.md"
        _write(p, text)
        return p

    def board_comment(self, key: str, cid: str, author: str, created: str, body: str) -> Path:
        text = f"---\nauthor: \"{author}\"\ncreated: {created}\nupdated: {created}\n---\n\n{body}\n"
        p = self.root / "board" / key / "comments" / f"{cid}.md"
        _write(p, text)
        return p

    # --- курсор (третья точка отсчёта) ---
    def cursor(self, mapping: dict[str, dict]) -> None:
        _write(self.root / "state" / "board-cursor.json",
               json.dumps(mapping, ensure_ascii=False, indent=2))

    def read_artifact(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Repo:
    """Изолированное мини-репо + перенаправление всех модульных путей на tmp_path."""
    root = tmp_path
    monkeypatch.setattr(bs, "REPO", root, raising=True)
    monkeypatch.setattr(bs, "BOARD", root / "board", raising=True)
    monkeypatch.setattr(bi, "REPO", root, raising=True)
    monkeypatch.setattr(bi, "BOARD", root / "board", raising=True)
    monkeypatch.setattr(bi, "CURSOR_PATH", root / "state" / "board-cursor.json", raising=True)
    monkeypatch.setattr(bi, "ESCALATIONS_PATH", root / "state" / "escalations.md", raising=True)
    return Repo(root)
