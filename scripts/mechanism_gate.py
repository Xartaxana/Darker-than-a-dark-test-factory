"""Гейт правила 10(б) — D-0055 OS-репо: механизмный коммит несёт осевой блок.

Твин tools/mechanism_gate.py OS-репо (парная строка оси 1 SIBLING_MAP;
правки — синхронно в обоих). Отличия твина: карта осей ОДНА и живёт в
OS-репо (D-0043), путь абсолютный, недоступна → fail-closed (F-7);
решений (DECISIONS_FULL) здесь нет, поэтому осевой блок ищется ТОЛЬКО
в сообщении коммита. Строка отказа «оси: не-механизм (<причина>)» —
тоже только из сообщения (F-A ревью critic: цитата синтаксиса в диффе
не должна обходить гейт). Merge-коммиты пропускаются (F-C).

Префиксы: политика, роли, скиллы + протокольные артефакты конвейера
(schemas/, state/rules.yaml — ось 6). scripts/ сознательно вне
триггера: правки кода обвязки покрываются тестами и ревью, а ложные
срабатывания гейта приучают к --no-verify (решение D-0055).
Исключение — самозащита цепочки (D-0065 OS-репо, F-25): сам гейт и
.githooks/ в неводе — правка гейта не должна обходить гейт (F-15).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MAP_PATH = Path(r"D:\Improving_AI\Operating-System-for-LLMs\docs\SIBLING_MAP.md")

MECHANISM_PREFIXES = (
    "CLAUDE.md",
    ".claude/agents/",
    ".claude/skills/",
    "schemas/",
    "state/rules.yaml",
    # D-0065 OS-репо: самозащита enforcement-цепочки
    "scripts/mechanism_gate.py",
    ".githooks/",
)

AXIS_HEADING_RE = re.compile(r"^##\s+Ось\s+(\d+)", re.MULTILINE)
SKIP_RE = re.compile(r"оси\s*:\s*не-механизм\s*\(", re.IGNORECASE)


def parse_axes(map_text: str) -> list[int]:
    return [int(n) for n in AXIS_HEADING_RE.findall(map_text)]


def _matches(path: str, pref: str) -> bool:
    if pref.endswith("/"):
        return path.startswith(pref)
    return path == pref


def mechanism_paths(staged: list[str]) -> list[str]:
    return [p for p in staged
            if any(_matches(p, pref) for pref in MECHANISM_PREFIXES)]


def find_missing(text: str, axes: list[int]) -> list[int]:
    return [n for n in axes
            if not re.search(rf"ось\s+{n}\s*:", text, re.IGNORECASE)]


def decide(msg: str, staged: list[str], map_text: str | None,
           merging: bool = False) -> tuple[int, str]:
    """Чистое решение гейта: блок и отказ — только из сообщения коммита."""
    hits = mechanism_paths(staged)
    if not hits:
        return 0, ""
    if merging:
        return 0, ""
    if SKIP_RE.search(msg):
        return 0, ""
    if map_text is None:
        return 1, (f"карта осей не найдена ({MAP_PATH}) — fail-closed, "
                   "коммит отклонён (D-0055 OS-репо)")
    axes = parse_axes(map_text)
    if not axes:
        return 1, ("в карте не найдено ни одной оси (## Ось N) — "
                   "fail-closed (D-0055 OS-репо)")
    missing = find_missing(msg, axes)
    if missing:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                   + "\nОсевой блок правила 10(б) неполон — нет вердикта по осям: "
                   + ", ".join(str(n) for n in missing)
                   + "\nДобавь в СООБЩЕНИЕ коммита «ось N: покрыта / в очередь / "
                   "н-п <почему>» на каждую ось карты либо явный отказ "
                   "«оси: не-механизм (<причина>)» (D-0055 OS-репо).")
    return 0, ""


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout or ""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("mechanism_gate: нужен путь к файлу сообщения коммита", file=sys.stderr)
        return 1
    staged = _git("diff", "--cached", "--name-only").splitlines()
    merge_head = _git("rev-parse", "--git-path", "MERGE_HEAD").strip()
    merging = bool(merge_head) and Path(merge_head).exists()
    msg = Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    map_text = (MAP_PATH.read_text(encoding="utf-8", errors="replace")
                if MAP_PATH.exists() else None)
    code, reason = decide(msg, staged, map_text, merging)
    if code:
        print("mechanism_gate: " + reason, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
