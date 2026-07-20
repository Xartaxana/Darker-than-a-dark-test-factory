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
import sys
from pathlib import Path

import yaml

# Windows-консоль (cp1251) искажает кириллицу в print — форсируем UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parents[1]
BOARD = REPO / "board"
PROJECT_KEY = "AO3"

# Матрица переходов (единый источник правды, schemas/transitions.yaml) — путь
# считается ОДИН раз при импорте и НЕ следует за монкипатчем bs.REPO в тестах:
# схема — часть кода/спеки, а не артефакт, который тесты подменяют на tmp_path.
TRANSITIONS_PATH = REPO / "schemas" / "transitions.yaml"

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
    # Производная колонка борды (НЕ статус схемы, НЕ в STATUS_MAP): Approved +
    # заполненный automated_by = F1-гейт, ждёт test-reviewer. См. _board_status_for.
    ("tc-awaiting-review", "Awaiting Review", "indeterminate"),
    ("tc-automated", "Automated", "done"),
    ("tc-blocked", "Blocked", "indeterminate"),
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
    ("run-blocked", "Blocked", "indeterminate"),
]

# Статические поля воркфлоу (name/statuses) — колонки. Кнопки-переходы больше
# НЕ хардкодятся: build() генерирует их из schemas/transitions.yaml (via_board),
# см. _board_transitions_for_machine/_workflows_config — единый источник правды.
WORKFLOWS = {
    "test-workflow": {
        "name": "Test Case Workflow",
        "statuses": ["tc-draft", "tc-review", "tc-approved", "tc-awaiting-review", "tc-automated", "tc-blocked"],
        "machine": "test-case",
    },
    "bug-workflow": {
        "name": "Bug Workflow",
        "statuses": ["bug-open", "bug-fixed", "bug-verified", "bug-reopened", "bug-blocked", "bug-rejected", "bug-intended"],
        "machine": "bug",
    },
    "run-workflow": {
        "name": "Test Run Workflow",
        "statuses": ["run-needstriage", "run-triaged", "run-closed", "run-blocked"],
        "machine": "run",
    },
}

# Наш статус (в YAML артефакта) -> id статуса TrackState, по типу артефакта
STATUS_MAP = {
    "test-case": {"Draft": "tc-draft", "Review": "tc-review", "Approved": "tc-approved",
                  "Automated": "tc-automated", "Blocked": "tc-blocked"},
    "bug": {"Open": "bug-open", "Reopened": "bug-reopened", "Blocked": "bug-blocked", "Fixed": "bug-fixed",
            "Verified": "bug-verified", "Rejected": "bug-rejected", "Intended": "bug-intended"},
    "run": {"NeedsTriage": "run-needstriage", "Triaged": "run-triaged", "Closed": "run-closed",
            "Blocked": "run-blocked"},
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
    if itype == "test-case":
        # B3/F1 (docs/09): вторые машины на артефакте test-case (automation_status,
        # review) невидимы в основном статусе борды — проецируем их в labels.
        if meta.get("automation_status"):
            labels.append(f"automation:{meta['automation_status']}")
        if meta.get("review"):
            labels.append(f"review:{meta['review']}")
    return labels


def _assignee_for(meta: dict) -> str:
    """Проекция frontmatter `lock` на assignee борды (без изменения частоты сборки).

    - lock пуст/отсутствует -> "qa-agents" (как раньше).
    - lock содержит ":" (агентский лок "<agent>:<ISO-timestamp>") -> часть до первого ":".
    - lock без ":" (ручной лок человека, напр. "wip") -> значение целиком.
    """
    lock = str(meta.get("lock") or "").strip()
    if not lock:
        return "qa-agents"
    return lock.split(":", 1)[0]


def _wip_label_for(meta: dict) -> str | None:
    lock = str(meta.get("lock") or "").strip()
    if not lock:
        return None
    return f"wip:{_assignee_for(meta)}"


def _board_status_for(itype: str, meta: dict) -> str | None:
    """Производная колонка борды СВЕРХ обычного STATUS_MAP-маппинга — только
    проекция отображения. Статусная машина test-case (schemas/transitions.yaml,
    schemas/test-case.schema.yaml) НЕ меняется, "tc-awaiting-review" НЕ входит
    в STATUS_MAP (иначе self-test «каждый enum схемы имеет маппинг» и смысл
    STATUS_MAP как маппинга схемных статусов сломались бы).

    F1 (docs/09): test-case со status=Approved и заполненным automated_by ждёт
    ревью test-reviewer (гейт до Automated) — на борде это отдельная колонка
    "Awaiting Review", хотя статусная машина всё ещё считает его Approved.
    Кейс с review: changes_requested (доработка после ревью) остаётся в ЭТОЙ
    ЖЕ колонке — он всё ещё в цикле ревью; label review:changes_requested
    (см. _labels_for) различает подслучай, отдельной колонки не нужно.

    Возвращает id новой колонки или None (= обычный STATUS_MAP-маппинг)."""
    if itype != "test-case":
        return None
    if str(meta.get("status", "")) != "Approved":
        return None
    if not str(meta.get("automated_by") or "").strip():
        return None
    return "tc-awaiting-review"


def approve_test_case(key: str) -> tuple[bool, str]:
    """Переводит test-case Review -> Approved прямо в исходном .md файле."""
    for itype, meta, _body, src in _iter_artifacts():
        if itype != "test-case" or str(meta.get("id")) != key:
            continue
        if str(meta.get("status")) != "Review":
            return False, f"{key}: статус «{meta.get('status')}», ожидался Review"
        text = src.read_text(encoding="utf-8")
        new_text = re.sub(r"(?m)^status:\s*Review\s*$", "status: Approved", text, count=1)
        if new_text == text:
            return False, f"{key}: не нашёл строку status: Review в файле"
        import datetime
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_text = re.sub(r'(?m)^updated:.*$', f'updated: "{stamp}"', new_text, count=1)
        src.write_text(new_text, encoding="utf-8")
        return True, f"{key}: Review → Approved"
    return False, f"{key}: не найден среди test-case"


def set_priority(key: str, priority: str) -> tuple[bool, str]:
    """Меняет priority: PN во frontmatter test-case/bug .md файла."""
    priority = priority.upper()
    if priority not in {"P0", "P1", "P2", "P3"}:
        return False, f"недопустимый приоритет «{priority}»"
    for itype, meta, _body, src in _iter_artifacts():
        if itype not in ("test-case", "bug") or str(meta.get("id")) != key:
            continue
        if itype == "bug":
            return False, f"{key}: у багов приоритет выводится из severity, не редактируется напрямую"
        text = src.read_text(encoding="utf-8")
        new_text = re.sub(r"(?m)^priority:\s*P[0-3]\s*$", f"priority: {priority}", text, count=1)
        if new_text == text:
            return False, f"{key}: не нашёл строку priority: PN в файле"
        import datetime
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_text = re.sub(r'(?m)^updated:.*$', f'updated: "{stamp}"', new_text, count=1)
        src.write_text(new_text, encoding="utf-8")
        return True, f"{key}: priority → {priority}"
    return False, f"{key}: не найден среди test-case"


SEVERITY_ENUM = {"blocker", "critical", "major", "minor"}


def set_severity(key: str, severity: str) -> tuple[bool, str]:
    """Меняет severity: <значение> во frontmatter bug .md файла.

    Зеркалит set_priority: test-case отказывает (severity редактируется только у
    багов, у test-case это priority), не найден — отказ. Не трогает
    SEVERITY_TO_PRIORITY/производную колонку приоритета — та пересчитается сама
    при следующей сборке из нового значения severity."""
    severity = severity.lower()
    if severity not in SEVERITY_ENUM:
        return False, f"недопустимая severity «{severity}»"
    for itype, meta, _body, src in _iter_artifacts():
        if itype not in ("test-case", "bug") or str(meta.get("id")) != key:
            continue
        if itype == "test-case":
            return False, f"{key}: у тест-кейсов severity нет — редактируй priority"
        text = src.read_text(encoding="utf-8")
        # re.subn (не сравнение new_text == text, как в set_priority): ставить
        # severity в то же значение, что уже есть, — легальный no-op апдейт, а не
        # "не нашёл строку" (тот сравнительный подход даёт ложный отказ, когда
        # целевое значение совпадает с текущим — тот же класс дефекта у set_priority,
        # там не воспроизводится, т.к. PN формат не пересекается с типовым тестом,
        # но сохраняется; вне scope этой задачи, см. отчёт).
        new_text, n_subs = re.subn(r"(?m)^severity:\s*[A-Za-z]+\s*$", f"severity: {severity}", text, count=1)
        if n_subs == 0:
            return False, f"{key}: не нашёл строку severity: <значение> в файле"
        import datetime
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_text = re.sub(r'(?m)^updated:.*$', f'updated: "{stamp}"', new_text, count=1)
        src.write_text(new_text, encoding="utf-8")
        return True, f"{key}: severity → {severity}"
    return False, f"{key}: не найден среди test-case/bug"


def _load_transitions_matrix() -> dict:
    return yaml.safe_load(TRANSITIONS_PATH.read_text(encoding="utf-8")) or {}


def _board_transitions_for_machine(matrix: dict, machine_key: str) -> list[dict]:
    """Кнопки-переходы борды для машины `machine_key` (schemas/transitions.yaml).

    Берём ТОЛЬКО правила с via_board: true; from: "*" разворачиваем в конкретные
    статусы машины (кроме to-статуса — переход в себя не нужен). id/name
    детерминированы, чтобы вывод был воспроизводим и сравним в self-test'ах."""
    machine = (matrix.get("machines") or {}).get(machine_key) or {}
    statuses = list(machine.get("statuses") or [])
    out: list[dict] = []
    for t in machine.get("transitions") or []:
        if not t.get("via_board"):
            continue
        to = str(t["to"])
        frm = str(t["from"])
        froms = [s for s in statuses if s != to] if frm == "*" else [frm]
        for f in froms:
            out.append({
                "id": f"{machine_key}-{f}-{to}".lower(),
                "name": f"{f} → {to}",
                "from": f,
                "to": to,
            })
    return out


def _workflows_config() -> dict:
    """WORKFLOWS (name/statuses — колонки) + transitions (кнопки), сгенерированные
    из schemas/transitions.yaml. Не мутирует модульный WORKFLOWS."""
    matrix = _load_transitions_matrix()
    cfg = {}
    for wf_id, wf in WORKFLOWS.items():
        cfg[wf_id] = {
            "name": wf["name"],
            "statuses": wf["statuses"],
            "transitions": _board_transitions_for_machine(matrix, wf["machine"]),
        }
    return cfg


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
        "attachmentStorage": {"mode": "repository-path", "repositoryPath": {"path": "board/.trackstate/attachments"}},
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
    (cfg / "workflows.json").write_text(json.dumps(_workflows_config(), indent=2), encoding="utf-8")
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
    unmapped = []
    for itype, meta, body, src in _iter_artifacts():
        key = str(meta["id"])
        status_str = str(meta.get("status", ""))
        if status_str in STATUS_MAP[itype]:
            status_id = STATUS_MAP[itype][status_str]
        else:
            fallback_status = next(iter(STATUS_MAP[itype]))
            status_id = STATUS_MAP[itype][fallback_status]
            unmapped.append((key, itype, status_str))
            print(f"  [WARN] {key} ({itype}): статус «{status_str}» не в STATUS_MAP, "
                  f"фолбэк на «{fallback_status}» ({status_id})")
        derived_status = _board_status_for(itype, meta)
        if derived_status:
            status_id = derived_status
        priority = _priority_for(itype, meta)
        summary = str(meta.get("title", key))
        updated = str(meta.get("updated") or meta.get("timestamp") or "2026-07-02T00:00:00Z")
        labels = _labels_for(itype, meta)
        assignee = _assignee_for(meta)
        wip_label = _wip_label_for(meta)
        if wip_label:
            labels.append(wip_label)

        issue_dir = BOARD / key
        issue_dir.mkdir(parents=True, exist_ok=True)
        fm = {
            "key": key, "project": PROJECT_KEY, "issueType": itype, "status": status_id,
            "priority": priority, "summary": summary, "assignee": assignee,
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
            "status": status_id, "priority": priority, "assignee": assignee,
            "labels": labels, "updated": updated,
            "resolution": fm["resolution"], "children": [], "archived": False,
        })
        count += 1

    (BOARD / ".trackstate" / "index" / "issues.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    (BOARD / ".trackstate" / "index" / "tombstones.json").write_text("[]", encoding="utf-8")

    # Курсор для board_inbound (docs/07 §2): снимок «что борда и артефакты содержали
    # в момент этой синхронизации» — по построению они здесь идентичны. Это ТРЕТЬЯ
    # точка отсчёта, по которой обратный канал отличает правку человека от рассинхрона.
    _write_inbound_cursor()

    if unmapped:
        print(f"board_sync: {len(unmapped)} артефакт(ов) с немаппящимся статусом (см. [WARN] выше; "
              f"валидация схем — не наша задача, см. validate_frontmatter.py)")
    print(f"board/ собрана: {count} тикетов ({sum(1 for i in index if i['issueType']=='test-case')} TC, "
          f"{sum(1 for i in index if i['issueType']=='bug')} bug, {sum(1 for i in index if i['issueType']=='run')} run)")


def _write_inbound_cursor():
    """Пишет state/board-cursor.json: key -> {itype, artifact_status, board_status}.

    Контракт с scripts/board_inbound.py (docs/07). Вызывается в конце build(), когда
    board/ уже консистентна артефактам, поэтому board_status == artifact_status."""
    cursor = {}
    for itype, meta, _body, _src in _iter_artifacts():
        key = str(meta.get("id"))
        status = str(meta.get("status", ""))
        cursor[key] = {"itype": itype, "artifact_status": status, "board_status": status}
    cursor_path = REPO / "state" / "board-cursor.json"
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(json.dumps(cursor, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    build()
