"""board_sync — проекция наших QA-артефактов в борду формата TrackState.AI.

Источник правды остаётся за агентами (test-cases/, bugs/, runs/ — markdown+YAML).
Этот скрипт ТОЛЬКО читает их и генерирует каталог board/ в формате, который
понимает приложение TrackState (десктоп локально либо GitHub Pages):
  board/project.json, board/config/*.json, board/<KEY>/main.md, board/.trackstate/index

Запуск:  python scripts/board_sync.py
Идемпотентен: пересобирает board/ целиком из текущего состояния артефактов.

Расхождения статусов TrackState ↔ наши статусные машины (docs/03 §2) заданы ниже
в STATUSES/WORKFLOWS/STATUS_MAP — единственное место маппинга.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOARD = REPO / "board"
PROJECT_KEY = "AO3"

# --- Конфиг борды (отражает НАШИ статусные машины) ---

ISSUE_TYPES = [
    {"id": "test-case", "name": "Test Case", "hierarchyLevel": 0, "icon": "story", "workflow": "test-workflow"},
    {"id": "bug", "name": "Bug", "hierarchyLevel": 0, "icon": "issue", "workflow": "bug-workflow"},
    {"id": "run", "name": "Test Run", "hierarchyLevel": 0, "icon": "task", "workflow": "run-workflow"},
]

# id, human name, category (new|indeterminate|done — определяет колонку/группировку)
STATUSES = [
    # test-case
    ("tc-draft", "Draft", "new"),
    ("tc-review", "Review", "indeterminate"),
    ("tc-approved", "Approved", "indeterminate"),
    ("tc-automated", "Automated", "done"),
    # bug
    ("bug-open", "Open", "new"),
    ("bug-reopened", "Reopened", "new"),
    ("bug-blocked", "Blocked", "indeterminate"),
    ("bug-fixed", "Fixed", "indeterminate"),
    ("bug-verified", "Verified", "done"),
    ("bug-rejected", "Rejected", "done"),
    ("bug-intended", "Intended", "done"),
    # run
    ("run-needstriage", "NeedsTriage", "new"),
    ("run-triaged", "Triaged", "indeterminate"),
    ("run-closed", "Closed", "done"),
]

WORKFLOWS = {
    "test-workflow": {
        "name": "Test Case Workflow",
        "statuses": ["tc-draft", "tc-review", "tc-approved", "tc-automated"],
        "transitions": [
            {"id": "tc-submit", "name": "Submit for review", "from": "tc-draft", "to": "tc-review"},
            {"id": "tc-approve", "name": "Approve", "from": "tc-review", "to": "tc-approved"},
            {"id": "tc-automate", "name": "Automated", "from": "tc-approved", "to": "tc-automated"},
        ],
    },
    "bug-workflow": {
        "name": "Bug Workflow",
        "statuses": ["bug-open", "bug-fixed", "bug-verified", "bug-reopened", "bug-blocked", "bug-rejected", "bug-intended"],
        "transitions": [
            {"id": "bug-fix", "name": "Mark fixed (человек)", "from": "bug-open", "to": "bug-fixed"},
            {"id": "bug-verify", "name": "Verify fix", "from": "bug-fixed", "to": "bug-verified"},
            {"id": "bug-reopen", "name": "Reopen", "from": "bug-fixed", "to": "bug-reopened"},
            {"id": "bug-reject", "name": "Reject / Intended", "from": "bug-open", "to": "bug-rejected"},
        ],
    },
    "run-workflow": {
        "name": "Test Run Workflow",
        "statuses": ["run-needstriage", "run-triaged", "run-closed"],
        "transitions": [
            {"id": "run-triage", "name": "Triaged", "from": "run-needstriage", "to": "run-triaged"},
            {"id": "run-close", "name": "Close", "from": "run-triaged", "to": "run-closed"},
        ],
    },
}

# Наш статус (в YAML артефакта) -> id статуса TrackState, по типу артефакта
STATUS_MAP = {
    "test-case": {"Draft": "tc-draft", "Review": "tc-review", "Approved": "tc-approved", "Automated": "tc-automated"},
    "bug": {"Open": "bug-open", "Reopened": "bug-reopened", "Blocked": "bug-blocked", "Fixed": "bug-fixed",
            "Verified": "bug-verified", "Rejected": "bug-rejected", "Intended": "bug-intended"},
    "run": {"NeedsTriage": "run-needstriage", "Triaged": "run-triaged", "Closed": "run-closed"},
}

PRIORITIES = [{"id": "p0", "name": "P0"}, {"id": "p1", "name": "P1"},
              {"id": "p2", "name": "P2"}, {"id": "p3", "name": "P3"}]
SEVERITY_TO_PRIORITY = {"blocker": "p0", "critical": "p0", "major": "p1", "minor": "p2", "trivial": "p3"}

FIELDS = [
    {"id": "summary", "name": "Summary", "type": "string", "required": True},
    {"id": "description", "name": "Description", "type": "markdown", "required": False},
    {"id": "priority", "name": "Priority", "type": "option", "required": False},
    {"id": "assignee", "name": "Assignee", "type": "user", "required": False},
    {"id": "labels", "name": "Labels", "type": "array", "required": False},
]


# --- Парсинг YAML frontmatter (без внешних зависимостей — простой ридер) ---

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    try:
        import yaml
        meta = yaml.safe_load(raw) or {}
    except Exception:
        meta = {}
        for line in raw.splitlines():
            m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
            if m:
                meta[m.group(1)] = m.group(2).strip().strip('"')
    return meta, body


def _iter_artifacts():
    """Возвращает (issue_type, meta, body, source_path) для каждого артефакта."""
    for area, itype in (("test-cases", "test-case"), ("bugs", "bug"), ("runs", "run")):
        base = REPO / area
        if not base.exists():
            continue
        for md in sorted(base.rglob("*.md")):
            if md.name.upper() == "README.MD":
                continue
            meta, body = _parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            if not meta.get("id"):
                continue
            yield itype, meta, body, md


def _priority_for(itype: str, meta: dict) -> str:
    if itype == "bug":
        return SEVERITY_TO_PRIORITY.get(str(meta.get("severity", "")).lower(), "p2")
    pr = str(meta.get("priority", "")).lower()
    return pr if pr in {"p0", "p1", "p2", "p3"} else "p2"


def _labels_for(itype: str, meta: dict) -> list[str]:
    labels = [itype]
    for k in ("area", "risk"):
        v = meta.get(k)
        if v:
            labels.append(f"{k}:{v}")
    # связи для traceability
    for k in ("test_cases", "runs", "duplicates"):
        v = meta.get(k)
        if isinstance(v, list):
            labels += [f"{k[:-1] if k.endswith('s') else k}:{x}" for x in v]
    if itype == "bug" and meta.get("severity"):
        labels.append(f"sev:{meta['severity']}")
    return labels


def build():
    if BOARD.exists():
        shutil.rmtree(BOARD)
    (BOARD / "config" / "i18n").mkdir(parents=True, exist_ok=True)
    (BOARD / ".trackstate" / "index").mkdir(parents=True, exist_ok=True)

    # project.json
    (BOARD / "project.json").write_text(json.dumps({
        "key": PROJECT_KEY,
        "name": "AO3 Reader QA",
        "defaultLocale": "en",
        "attachmentStorage": {"mode": "none"},
        "issueKeyPattern": PROJECT_KEY + "-{number}",
        "dataModel": "nested-tree",
        "configPath": "config",
        "supportedLocales": ["en"],
    }, indent=2), encoding="utf-8")

    # config/*
    cfg = BOARD / "config"
    (cfg / "issue-types.json").write_text(json.dumps(ISSUE_TYPES, indent=2), encoding="utf-8")
    (cfg / "statuses.json").write_text(json.dumps(
        [{"id": i, "name": n, "category": c} for i, n, c in STATUSES], indent=2), encoding="utf-8")
    (cfg / "workflows.json").write_text(json.dumps(WORKFLOWS, indent=2), encoding="utf-8")
    (cfg / "priorities.json").write_text(json.dumps(PRIORITIES, indent=2), encoding="utf-8")
    (cfg / "fields.json").write_text(json.dumps(FIELDS, indent=2), encoding="utf-8")
    (cfg / "components.json").write_text("[]", encoding="utf-8")
    (cfg / "versions.json").write_text("[]", encoding="utf-8")
    (cfg / "resolutions.json").write_text(json.dumps([{"id": "done", "name": "Done"}]), encoding="utf-8")
    (cfg / "i18n" / "en.json").write_text(json.dumps({
        "issueTypes": {t["id"]: t["name"] for t in ISSUE_TYPES},
        "statuses": {i: n for i, n, _ in STATUSES},
        "priorities": {p["id"]: p["name"] for p in PRIORITIES},
        "fields": {f["id"]: f["name"] for f in FIELDS},
    }, indent=2), encoding="utf-8")

    # issues
    index = []
    count = 0
    for itype, meta, body, src in _iter_artifacts():
        key = str(meta["id"])
        status_id = STATUS_MAP[itype].get(str(meta.get("status", "")), STATUS_MAP[itype][next(iter(STATUS_MAP[itype]))])
        priority = _priority_for(itype, meta)
        summary = str(meta.get("title", key))
        updated = str(meta.get("updated") or meta.get("timestamp") or "2026-07-02T00:00:00Z")
        labels = _labels_for(itype, meta)

        issue_dir = BOARD / key
        issue_dir.mkdir(parents=True, exist_ok=True)
        fm = {
            "key": key, "project": PROJECT_KEY, "issueType": itype, "status": status_id,
            "priority": priority, "summary": summary, "assignee": "qa-agents",
            "reporter": "qa-agents", "labels": labels, "components": [], "fixVersions": [],
            "watchers": [], "parent": None, "epic": None,
            "created": updated, "updated": updated, "archived": False,
            "resolution": "done" if status_id.endswith(("automated", "verified", "closed")) else None,
        }
        fm_lines = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items())
        main = f"---\n{fm_lines}\n---\n\n# {summary}\n\n_Спроецировано из `{src.relative_to(REPO).as_posix()}` (источник правды).\nСтатус в нашей машине: **{meta.get('status')}**._\n\n{body}"
        (issue_dir / "main.md").write_text(main, encoding="utf-8")

        index.append({
            "key": key, "path": f"board/{key}/main.md", "parent": None, "epic": None,
            "parentPath": None, "epicPath": None, "summary": summary, "issueType": itype,
            "status": status_id, "priority": priority, "assignee": "qa-agents",
            "labels": labels, "updated": updated,
            "resolution": fm["resolution"], "children": [], "archived": False,
        })
        count += 1

    (BOARD / ".trackstate" / "index" / "issues.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    (BOARD / ".trackstate" / "index" / "tombstones.json").write_text("[]", encoding="utf-8")
    print(f"board/ собрана: {count} тикетов ({sum(1 for i in index if i['issueType']=='test-case')} TC, "
          f"{sum(1 for i in index if i['issueType']=='bug')} bug, {sum(1 for i in index if i['issueType']=='run')} run)")


if __name__ == "__main__":
    build()
