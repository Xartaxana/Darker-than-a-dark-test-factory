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

import datetime
import json
import re
import shutil
import sys
from collections import defaultdict
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
    # Story-цепочка (spec-story-board v3): READ-ONLY карточка, синтезированная из
    # QAREADY-строк escalations.md + docs/feature-registry.yaml (story:<iid>) +
    # test-cases/bugs зоны — НЕ отдельный артефакт-файл. Критик-вход (Б4,
    # решение Lead): hierarchyLevel 0 (не 1) — уровня 1 в этом репо никогда не
    # было, внешний TrackState-провайдер может прятать эпик-уровень из
    # канбана; с level 0 рендер идентичен трём существующим типам.
    {"id": "story", "name": "Story", "hierarchyLevel": 0, "icon": "epic", "workflow": "story-workflow"},
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
    # П1 Р0 п.4 (spec-p1-dedup v7): отдельная колонка для Merged — дубль-кейс,
    # поглощённый journey-TC. INV 1:1 с STATUS_MAP ниже (коллапс невозможен).
    # board_view.py COLUMNS её сознательно НЕ несёт (как сейчас tc-blocked) —
    # карточка не отображается на HTML-борде, только на TrackState.
    ("tc-merged", "Merged", "done"),
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
    # story (лестница стадий M-SB2 спеки — read-only, НЕ вносится в STATUS_MAP
    # ниже: карточки пишутся отдельным проходом build(), мимо STATUS_MAP[itype]
    # цикла артефактов, см. collect_stories()/_STORY_STAGE_NAME).
    ("story-detected", "Обнаружена", "new"),
    ("story-writing-cases", "Кейсы пишутся", "indeterminate"),
    ("story-review", "На ревью", "indeterminate"),
    ("story-automation", "Автоматизация", "indeterminate"),
    ("story-covered", "Покрыта", "done"),
]

# Стадии story в каноническом порядке лестницы (id, human name) — производные
# из STATUSES выше (единственный источник правды), а не дублирующий литерал.
STORY_STAGE_IDS = [sid for sid, _, _ in STATUSES if sid.startswith("story-")]
_STORY_STAGE_NAME = {sid: name for sid, name, _ in STATUSES if sid.startswith("story-")}

# Статические поля воркфлоу (name/statuses) — колонки. Кнопки-переходы больше
# НЕ хардкодятся: build() генерирует их из schemas/transitions.yaml (via_board),
# см. _board_transitions_for_machine/_workflows_config — единый источник правды.
WORKFLOWS = {
    "test-workflow": {
        "name": "Test Case Workflow",
        "statuses": ["tc-draft", "tc-review", "tc-approved", "tc-awaiting-review", "tc-automated", "tc-merged", "tc-blocked"],
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
    # "machine": "story" НЕ существует в schemas/transitions.yaml (намеренно —
    # read-only карточка): _workflows_config()/_board_transitions_for_machine
    # находят пустой machine и отдают transitions=[] — ни одной кнопки-перехода,
    # что и требуется (board_inbound её тип не знает вовсе, см. docs M-SB2).
    "story-workflow": {
        "name": "Story Workflow",
        "statuses": STORY_STAGE_IDS,
        "machine": "story",
    },
}

# Наш статус (в YAML артефакта) -> id статуса TrackState, по типу артефакта
STATUS_MAP = {
    "test-case": {"Draft": "tc-draft", "Review": "tc-review", "Approved": "tc-approved",
                  "Automated": "tc-automated", "Merged": "tc-merged", "Blocked": "tc-blocked"},
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


# --- Writeback frontmatter (AT-BUG-038: EOL-перегон + отсутствие границы) --
#
# Образец — scripts/gitlab_sync.py::writeback_gitlab_issue: read_bytes/
# write_bytes (БАЙТОВЫЙ режим — read_text/write_text транслируют EOL всего
# файла на universal-newlines при КАЖДОЙ записи, даже если меняется одно
# поле — воспроизведено в bugs/AT-BUG-038.md) + поиск СТРОГО в теле
# frontmatter (между открывающим и закрывающим '---'), не по всему файлу.
# ОТДЕЛЬНЫЙ regex от _parse_frontmatter выше: тот — терпимый ридер для
# обхода артефактов (fallback на построчный парсинг), этот — точная граница
# для записи, симметричная gitlab_sync.FRONTMATTER_RE.
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def _frontmatter_body_span(text: str) -> tuple[int, int] | None:
    """(start, end) среза ТЕЛА frontmatter, либо None — frontmatter
    отсутствует/битый (нет закрывающего '---')."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return m.start(1), m.end(1)


def _subn_frontmatter_field(text: str, pattern: re.Pattern, replacement: str,
                             count: int = 1) -> tuple[str, int]:
    """re.subn СТРОГО в теле frontmatter (не во всём файле, класс 2
    AT-BUG-038). Возвращает (новый_текст, число_замен); 0 замен — либо
    frontmatter битый, либо искомая строка не найдена в его теле —
    вызывающий код решает, отказ это или легальный no-op (совпадает со
    старым поведением re.subn на всём файле)."""
    span = _frontmatter_body_span(text)
    if span is None:
        return text, 0
    start, end = span
    new_body, n = pattern.subn(replacement, text[start:end], count=count)
    if n == 0:
        return text, 0
    return text[:start] + new_body + text[end:], n


def _utc_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        text = src.read_bytes().decode("utf-8")
        new_text, n = _subn_frontmatter_field(
            text, re.compile(r"(?m)^status:[ \t]*Review[ \t]*(?=\r?\n|$)"), "status: Approved")
        if n == 0:
            return False, f"{key}: не нашёл строку status: Review в файле"
        stamp = _utc_stamp()
        new_text, _ = _subn_frontmatter_field(
            new_text, re.compile(r'(?m)^updated:[^\r\n]*'), f'updated: "{stamp}"')
        src.write_bytes(new_text.encode("utf-8"))
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
        text = src.read_bytes().decode("utf-8")
        new_text, n_subs = _subn_frontmatter_field(
            text, re.compile(r"(?m)^priority:[ \t]*P[0-3][ \t]*(?=\r?\n|$)"), f"priority: {priority}")
        if n_subs == 0:
            return False, f"{key}: не нашёл строку priority: PN в файле"
        stamp = _utc_stamp()
        new_text, _ = _subn_frontmatter_field(
            new_text, re.compile(r'(?m)^updated:[^\r\n]*'), f'updated: "{stamp}"')
        src.write_bytes(new_text.encode("utf-8"))
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
        text = src.read_bytes().decode("utf-8")
        # re.subn (не сравнение new_text == text): ставить значение в то же,
        # что уже есть, — легальный no-op апдейт, а не "не нашёл строку"
        # (класс закрыт так же в set_priority выше).
        new_text, n_subs = _subn_frontmatter_field(
            text, re.compile(r"(?m)^severity:[ \t]*[A-Za-z]+[ \t]*(?=\r?\n|$)"), f"severity: {severity}")
        if n_subs == 0:
            return False, f"{key}: не нашёл строку severity: <значение> в файле"
        stamp = _utc_stamp()
        new_text, _ = _subn_frontmatter_field(
            new_text, re.compile(r'(?m)^updated:[^\r\n]*'), f'updated: "{stamp}"')
        src.write_bytes(new_text.encode("utf-8"))
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
    terminal = set(machine.get("terminal") or [])
    out: list[dict] = []
    for t in machine.get("transitions") or []:
        if not t.get("via_board"):
            continue
        to = str(t["to"])
        frm = str(t["from"])
        # Н2 критик-диффа: '*' не разворачивается на терминальные статусы
        # без from_terminal — иначе борда рисует кнопку (Merged -> Review),
        # которую classify всё равно отобьёт (UX-мусор + второй дубль
        # wildcard-семантики вне матрицы).
        if frm == "*":
            froms = [s for s in statuses
                     if s != to and (t.get("from_terminal") or s not in terminal)]
        else:
            froms = [frm]
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


# === Story-цепочка (spec-story-board v3) ====================================
#
# Общий сборщик story-данных, переиспользуемый ОБЕИМИ поверхностями (board_sync
# build() ниже и board_view.collect(), которая импортирует collect_stories как
# ФУНКЦИЮ — пути читаются из REPO В МОМЕНТ ВЫЗОВА этой функции, не при импорте
# модуля, см. докстринг ниже и conftest.py:144-149).
#
# Источники (все читаются заново при каждом вызове, O(файлы) без сети):
#   - state/escalations.md: QAREADY-<iid> строки (E7, scripts/gitlab_inbound.py)
#   - docs/feature-registry.yaml: записи story:<iid> -> зона feature-id
#   - test-cases/*.md: поле features (пересечение с зоной), status, red_lock,
#     automation_status
#   - bugs/*.md: test_cases/found_in/runs (канал Б9 + бейдж «регресс сборки»)
#   - runs/*.md: tc_results (бейдж «зелёные в <RUN-id>») + suite/source_commit
#     (бейдж «регресс сборки», v3.1)
#   - state/app-under-test.yaml: source_commit текущей сборки (v3.1)

# Ключ QAREADY-строки: широкий матч (любой суффикс после "QAREADY-") — нужен,
# чтобы отличить "не наш формат ключа" (CAP/SYNC-RACE-*) от "формат верный, но
# нет обязательного E7-суффикса" и напечатать ПРИЧИНУ игнора в обоих случаях
# (Б5 DoD: "CAP/SYNC-RACE игнор со строкой в выводе"), а не молча их пропустить.
_STORY_KEY_ANY_RE = re.compile(r"\*\*(QAREADY-[^*]+)\*\*(\s*\[resolved:[^\]]*\])?")
_STORY_KEY_DIGIT_RE = re.compile(r"^QAREADY-(\d+)$")
_STORY_TS_RE = re.compile(r"^-\s*\[([^\]]+)\]")
_STORY_DELIM = " — "
# Обязательный E7-суффикс (Б5) — литерал из scripts/gitlab_inbound.py::scan_qaready
# (f"{title} — фича разработчика помечена QAready: ..."). Б6: якорим на ПОСЛЕДНЕЕ
# вхождение — внешний (недоверенный) заголовок айтема может сам нести " — ".
_STORY_E7_SUFFIX = "фича разработчика помечена QAready"
_STORY_E7_ANCHOR = _STORY_DELIM + _STORY_E7_SUFFIX


def _iter_story_lines(escalations_text: str):
    """Парсит строки QAREADY-<iid> из state/escalations.md (Б5/Б6).

    yield: dict(key, iid, ts, resolved, title) для строк, прошедших фильтр
    (^QAREADY-(\\d+)$ ключ + обязательный E7-суффикс). Строки, провалившие
    фильтр (QAREADY-CAP, QAREADY-SYNC-RACE-*, битый формат) — печатают причину
    игнора в stdout (Б5 DoD) и не попадают в вывод."""
    for line in escalations_text.splitlines():
        if "QAREADY-" not in line:
            continue
        m = _STORY_KEY_ANY_RE.search(line)
        if not m:
            continue
        key, resolved_marker = m.group(1), m.group(2)
        dm = _STORY_KEY_DIGIT_RE.match(key)
        if not dm:
            print(f"  [WARN] story: {key} не матчит ^QAREADY-(\\d+)$ — игнор (не story-строка)")
            continue
        iid = dm.group(1)
        rest = line[m.end():]
        if not rest.startswith(_STORY_DELIM):
            print(f"  [WARN] story: {key} без разделителя « — » после ключа — игнор")
            continue
        reason = rest[len(_STORY_DELIM):]
        anchor = reason.rfind(_STORY_E7_ANCHOR)
        if anchor == -1:
            print(f"  [WARN] story: {key} без обязательного E7-суффикса — игнор")
            continue
        title = reason[:anchor].strip()
        tsm = _STORY_TS_RE.match(line)
        yield {
            "key": key, "iid": iid, "ts": tsm.group(1) if tsm else "",
            "resolved": bool(resolved_marker), "title": title,
        }


def _group_story_lines(lines: list[dict]) -> dict[str, dict]:
    """iid(str) -> {"discovered_ts" (Б7: ПЕРВАЯ строка), "title" (последняя),
    "resolved" (текущее/финальное состояние), "reopened" (Б7: resolved,
    ЗА КОТОРЫМ следует более поздняя непогашенная строка того же iid)}.

    Строки приходят в порядке появления в escalations.md — файл append-only,
    поэтому порядок = хронологический (docs/06 §4)."""
    per_iid: dict[str, list[dict]] = defaultdict(list)
    for ln in lines:
        per_iid[ln["iid"]].append(ln)
    out: dict[str, dict] = {}
    for iid, entries in per_iid.items():
        reopened = False
        seen_resolved = False
        for e in entries:
            if e["resolved"]:
                seen_resolved = True
            elif seen_resolved:
                reopened = True
        out[iid] = {
            "discovered_ts": entries[0]["ts"],
            "title": entries[-1]["title"] or entries[0]["title"],
            "resolved": entries[-1]["resolved"],
            "reopened": reopened,
        }
    return out


def _iid_sort_key(iid: str):
    return (0, int(iid)) if iid.isdigit() else (1, iid)


def _latest_run_by_suite(run_metas: list[dict], suite: str) -> dict | None:
    """Прогон с максимальным id (лексикографический max по фиксированной ширине
    RUN-YYYYMMDD-HHMM == хронологический max, сверено критиком — тот же приём,
    что и «последний прогон» в лестнице стадий, п.5) среди артефактов runs/ с
    suite==suite и id, НАЧИНАЮЩИМСЯ с "RUN-" (иные префиксы/без id — исключены)."""
    candidates = [
        m for m in run_metas
        if str(m.get("suite", "")) == suite and str(m.get("id", "")).startswith("RUN-")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda m: str(m.get("id")))


_STORY_RUN_STATUS_RU = {
    "Triaged": "разобрано",
    "NeedsTriage": "разбирается",
    "Closed": "чисто",
}

# Критик-вход (Б3б): found_in хранит СОКРАЩЁННЫЙ hex-хэш ПРОИЗВОЛЬНОЙ длины
# (живой прецедент bugs/BUG-050..052.md: "commit 63f6aac" — 7 символов, не 8) —
# фиксированный срез current_commit[:8] промахивался мимо более коротких
# записей. Извлекаем ЛЮБЫЕ hex-токены длины >=7 из found_in и проверяем, что
# каждый — ПРЕФИКС (case-insensitive) полного source_commit (found_in несёт
# усечённую форму, не наоборот).
_HEX_TOKEN_RE = re.compile(r"[0-9a-fA-F]{7,}")


def _found_in_matches_commit(found_in: str, current_commit: str) -> bool:
    commit_lower = current_commit.lower()
    return any(commit_lower.startswith(token.lower()) for token in _HEX_TOKEN_RE.findall(found_in or ""))


def _regression_badge(run_metas: list[dict], bug_metas: list[dict], current_commit: str | None) -> str:
    """(v3.1 + критик-вход Б2) Бейдж «регресс сборки», ОДИН на все
    story-карточки этого прогона build()/collect(). Источники — max RUN-id по
    suite smoke/regression, чей frontmatter source_commit == текущему
    (state/app-under-test.yaml).

    Б2: РАЗБИВКА ПО SUITE — агрегированное «48/49 · чисто» при частичном
    совпадении (только smoke ИЛИ только regression) молчало о втором suite,
    не гонявшемся вовсе на этой сборке (критик-проба). Каждый suite —
    отдельный сегмент: либо "<suite> <RUN-id> P/T · статус", либо явное
    "<suite>: нет прогона на этой сборке"."""
    if not current_commit:
        return "регресс сборки: прогона ещё не было"

    matched: dict[str, dict] = {}
    for suite in ("smoke", "regression"):
        run = _latest_run_by_suite(run_metas, suite)
        if run is not None and str(run.get("source_commit") or "") == current_commit:
            matched[suite] = run
    if not matched:
        return "регресс сборки: прогона ещё не было"

    parts: list[str] = []
    matched_run_ids: set[str] = set()
    for suite in ("smoke", "regression"):
        run = matched.get(suite)
        if run is None:
            parts.append(f"{suite}: нет прогона на этой сборке")
            continue
        totals = run.get("totals") or {}
        passed = int(totals.get("passed") or 0)
        total = sum(int(totals.get(k) or 0) for k in ("passed", "failed", "skipped", "quarantined"))
        status_ru = _STORY_RUN_STATUS_RU.get(str(run.get("status") or ""), str(run.get("status") or ""))
        run_id = str(run.get("id"))
        parts.append(f"{suite} {run_id} {passed}/{total} · {status_ru}")
        matched_run_ids.add(run_id)

    # Б3а: переименовано из «новых багов: K» — прежняя формулировка сидела
    # рядом со списком «Баги: BUG-x, BUG-y» (канал Б9, ДРУГОЙ подсчёт, багов
    # на кейсах зоны вообще, вне привязки к конкретному прогону) и читалась
    # как противоречие (критик-проба BUG-059/060, runs: []).
    new_bugs = set()
    for bug in bug_metas:
        runs = bug.get("runs") or []
        if not any(str(r) in matched_run_ids for r in runs):
            continue
        if _found_in_matches_commit(str(bug.get("found_in") or ""), current_commit):
            new_bugs.add(str(bug.get("id")))

    return "регресс сборки: " + " · ".join(parts) + f" · новых багов в прогоне: {len(new_bugs)}"


def _current_build_commit() -> str | None:
    """source_commit ТЕКУЩЕЙ сборки из state/app-under-test.yaml (v3.1) — путь
    резолвится из глобального REPO В МОМЕНТ ВЫЗОВА (Б-тестопригодность)."""
    path = REPO / "state" / "app-under-test.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    commit = data.get("source_commit")
    return str(commit).strip() if commit else None


def collect_stories() -> tuple[list[dict], list[str]]:
    """Общий сборщик story-данных (M-SB2 спеки story-board) — единственная точка
    входа для ОБЕИХ поверхностей (board_sync.build() и board_view.collect()).

    Пути резолвятся из ГЛОБАЛЬНОГО REPO (модульный атрибут этого модуля) В МОМЕНТ
    ВЫЗОВА этой функции — не при импорте (прецедент TRANSITIONS_PATH выше,
    который сознательно НЕ следует за монкипатчем; здесь наоборот — юниты на
    синтетике (tmp_path) обязаны видеть свой state/escalations.md и
    docs/feature-registry.yaml, поэтому REPO читается лениво).

    Возвращает (stories, warnings):
      stories — list[dict], один на КАЖДЫЙ iid, когда-либо встреченный в
        QAREADY-строках escalations.md (после Б5-фильтра), отсортированный по
        числовому iid. Поля: iid, title, stage_id, stage_name, stage_index
        (1..5), badges (list[str]), tc_keys (list[str]), bug_keys (list[str]),
        discovered_ts.
      warnings — list[str], детекторы M-SB4 (а)/(б) (без "[WARN] " префикса —
        печать/форматирование на стороне вызывающего)."""
    esc_path = REPO / "state" / "escalations.md"
    esc_text = esc_path.read_text(encoding="utf-8", errors="replace") if esc_path.exists() else ""
    groups = _group_story_lines(list(_iter_story_lines(esc_text)))

    registry_path = REPO / "docs" / "feature-registry.yaml"
    registry_features: list[dict] = []
    if registry_path.exists():
        data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        registry_features = data.get("features") or []

    # zone_index: iid(str, КАК ЗАДАНО в реестре — нормализация ниже) -> [feature-id]
    zone_index: dict[str, list[str]] = defaultdict(list)
    for f in registry_features:
        raw = f.get("story")
        if raw is None or str(raw).strip() == "":
            continue
        zone_index[str(raw).strip()].append(str(f.get("id")))

    tc_metas: list[dict] = []
    bug_metas: list[dict] = []
    run_metas: list[dict] = []
    for itype, meta, _body, _src in _iter_artifacts():
        if itype == "test-case":
            tc_metas.append(meta)
        elif itype == "bug":
            bug_metas.append(meta)
        elif itype == "run":
            run_metas.append(meta)

    feature_to_tcs: dict[str, list[str]] = defaultdict(list)
    for meta in tc_metas:
        for fid in (meta.get("features") or []):
            feature_to_tcs[str(fid)].append(str(meta.get("id")))
    tc_by_id = {str(m.get("id")): m for m in tc_metas}
    bug_by_id = {str(m.get("id")): m for m in bug_metas}

    # Для бейджа "зелёные в <RUN-id>" (стадия 5) нужен ПОСЛЕДНИЙ прогон ЛЮБОГО
    # suite (не только smoke/regression) — отдельная выборка от _regression_badge.
    any_run_candidates = [m for m in run_metas if str(m.get("id", "")).startswith("RUN-")]
    latest_run = max(any_run_candidates, key=lambda m: str(m.get("id"))) if any_run_candidates else None

    current_commit = _current_build_commit()
    regression_badge = _regression_badge(run_metas, bug_metas, current_commit)

    stories: list[dict] = []
    warnings: list[str] = []  # M-SB4 + критик-вход (unknown-status WARN, ниже)
    for iid, g in groups.items():
        zone_feature_ids = sorted(zone_index.get(iid, []))
        zone_tc_keys = sorted({tc for fid in zone_feature_ids for tc in feature_to_tcs.get(fid, [])})
        zone_tc_metas = [tc_by_id[k] for k in zone_tc_keys if k in tc_by_id]

        badges: list[str] = []
        if not g["resolved"]:
            stage_idx = 0  # "Обнаружена"
            if g["reopened"]:
                badges.append("переоткрыта")
        else:
            features_without_cases = [fid for fid in zone_feature_ids if not feature_to_tcs.get(fid)]
            blocked_cases = [m for m in zone_tc_metas if str(m.get("status")) == "Blocked"]
            draft_cases = [m for m in zone_tc_metas if str(m.get("status")) == "Draft"]
            no_links = len(zone_feature_ids) == 0
            # Критик-вход (не-блокер): статус вне enum test-case.schema.yaml
            # молча утекал бы в "Покрыта" (else-ветка ловила ЛЮБОЙ остаток) —
            # трактуем как слабое звено (стадия 2) + WARN, не падение.
            # П1 Р0 п.5 (spec-p1-dedup v7): Merged — легальный статус, НЕ попадает
            # в unknown_cases (иначе каждый journey-поглощённый дубль ложно
            # деградировал бы стадию стори до «слабое звено»).
            unknown_cases = [
                m for m in zone_tc_metas
                if str(m.get("status")) not in ("Draft", "Review", "Approved", "Automated", "Blocked", "Merged")
            ]

            if no_links or features_without_cases or draft_cases or blocked_cases or unknown_cases:
                stage_idx = 1  # "Кейсы пишутся"
                if no_links:
                    badges.append("связки нет")
                else:
                    badges.append(f"фич без кейсов: {len(features_without_cases)}/{len(zone_feature_ids)}")
                if draft_cases:
                    badges.append(f"черновиков: {len(draft_cases)}")
                if blocked_cases:
                    reasons = sorted({str(m.get("blocked_reason") or "unspecified") for m in blocked_cases})
                    badges.append(f"⚠ заблокировано: {len(blocked_cases)} ({', '.join(reasons)})")
                for m in unknown_cases:
                    warnings.append(
                        f"story: story-{iid} — {m.get('id')} несёт статус «{m.get('status')}» вне enum "
                        f"test-case (Draft/Review/Approved/Automated/Blocked) — учтён как слабое звено, "
                        f"стадия «Кейсы пишутся»")
            else:
                # Непусто по построению (features_without_cases пуст И zone_feature_ids
                # непуст ⇒ у каждой фичи зоны есть >=1 кейс ⇒ zone_tc_metas непуст) —
                # никаких all([])/vacuous truth над потенциально пустым множеством.
                # unknown_cases уже исключены веткой выше ⇒ статусы ⊆
                # {Review, Approved, Automated, Merged}.
                statuses_present = {str(m.get("status")) for m in zone_tc_metas}
                if "Review" in statuses_present:
                    stage_idx = 2  # "На ревью"
                elif "Approved" in statuses_present:
                    stage_idx = 3  # "Автоматизация"
                elif zone_tc_metas and all(str(m.get("status")) in ("Automated", "Merged") for m in zone_tc_metas):
                    # Критик-вход (не-блокер): ПОЗИТИВНАЯ проверка, не "что осталось
                    # после исключений" — "Покрыта" требует явного all(), а не
                    # молчаливого else. Недостижимо иначе по построению выше, но
                    # защита от будущего протекания статуса остаётся явной.
                    # П1 Р0 п.5: Merged засчитан в «Покрыта» — дубль-кейс поглощён
                    # journey, его покрытие несёт merged_into.
                    stage_idx = 4  # "Покрыта"
                    if latest_run is not None:
                        tc_results = latest_run.get("tc_results") or {}
                        # Знаменатель бейджа БЕЗ Merged (П1 Р0 п.5): у Merged-кейса
                        # automated_by пуст, он никогда не появится в tc_results —
                        # включение его в знаменатель занижало бы дробь навсегда.
                        non_merged_keys = [
                            k for k in zone_tc_keys
                            if str(tc_by_id.get(k, {}).get("status")) != "Merged"
                        ]
                        present = [k for k in non_merged_keys if k in tc_results]
                        if present:
                            green = sum(1 for k in present if tc_results.get(k) == "passed")
                            badges.append(f"зелёные в {latest_run.get('id')}: {green}/{len(non_merged_keys)}")
                    quarantine = [
                        m for m in zone_tc_metas
                        if str(m.get("status")) == "Automated"
                        and str(m.get("automation_status") or "") != "active"
                    ]
                    if quarantine:
                        badges.append(f"автотестов в карантине: {len(quarantine)}")
                else:
                    # Недостижимо по построению (см. выше) — но не вакуумная
                    # истина по умолчанию: если каким-то образом дошли сюда без
                    # all()==True, откатываемся на слабое звено, не "Покрыта".
                    stage_idx = 1
                    badges.append(f"фич без кейсов: 0/{len(zone_feature_ids)}")

        # Б9: канал "багов на кейсах стори" — Open|Reopened баги на TC зоны (a)
        # ПЛЮС красные замки (red_lock) TC зоны, тоже отфильтрованные Open|Reopened.
        tc_set = set(zone_tc_keys)
        bugs_a = {
            str(m.get("id")) for m in bug_metas
            if str(m.get("status")) in ("Open", "Reopened")
            and any(str(tc) in tc_set for tc in (m.get("test_cases") or []))
        }
        bugs_b = set()
        for m in zone_tc_metas:
            rl = str(m.get("red_lock") or "").strip()
            if not rl:
                continue
            bug = bug_by_id.get(rl)
            if bug is not None and str(bug.get("status")) in ("Open", "Reopened"):
                bugs_b.add(rl)
        bug_keys = sorted(bugs_a | bugs_b)
        badges.append(f"багов на кейсах стори: {len(bug_keys)}")

        # v3.1: бейдж «регресс сборки» — ОДИН и тот же на каждой карточке.
        badges.insert(0, regression_badge)

        stage_id = STORY_STAGE_IDS[stage_idx]
        stories.append({
            "iid": iid,
            "title": g["title"],
            "discovered_ts": g["discovered_ts"],
            "stage_id": stage_id,
            "stage_name": _STORY_STAGE_NAME[stage_id],
            "stage_index": stage_idx + 1,
            "badges": badges,
            "tc_keys": zone_tc_keys,
            "bug_keys": bug_keys,
        })

    stories.sort(key=lambda s: _iid_sort_key(s["iid"]))

    # M-SB4: WARN двусторонний (warnings уже несёт unknown-status находки из
    # цикла выше, если были).
    feature_iids = set(zone_index.keys())
    for iid, g in sorted(groups.items(), key=lambda kv: _iid_sort_key(kv[0])):
        if g["resolved"] and iid not in feature_iids:
            warnings.append(
                f"story: QAREADY-{iid} resolved без записей story:{iid} в docs/feature-registry.yaml "
                f"(стратег забыл конвенцию)")
    for iid in sorted(feature_iids - set(groups.keys()), key=_iid_sort_key):
        warnings.append(f"story: story:{iid} в docs/feature-registry.yaml без строки QAREADY-{iid} (сирота/опечатка iid)")

    return stories, warnings


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
            "resolution": "done" if status_id.endswith(("automated", "verified", "closed", "merged")) else None,
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

    # Story-цепочка (spec-story-board v3): карточки пишутся ОТДЕЛЬНЫМ проходом,
    # МИМО цикла артефактов выше (STATUS_MAP[itype][status_str] не знает про
    # itype "story" — read-only инвариант, story-стадии НЕ вносятся в STATUS_MAP).
    stories, story_warnings = collect_stories()
    for w in story_warnings:
        print(f"  [WARN] {w}")
    for s in stories:
        key = f"story-{s['iid']}"
        summary = s["title"] or key
        labels = [f"stage:{s['stage_id']}"] + list(s["badges"])
        updated = s["discovered_ts"] or "2026-07-02T00:00:00Z"

        issue_dir = BOARD / key
        issue_dir.mkdir(parents=True, exist_ok=True)
        fm = {
            "key": key, "project": PROJECT_KEY, "issueType": "story", "status": s["stage_id"],
            "priority": "p2", "summary": summary, "assignee": "qa-agents",
            "reporter": "qa-agents", "labels": labels, "components": [], "fixVersions": [],
            "watchers": [], "parent": None, "epic": None,
            "created": updated, "updated": updated, "archived": False,
            "resolution": "done" if s["stage_id"] == "story-covered" else None,
        }
        fm_lines = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items())
        body = (
            f"Стадия: **{s['stage_name']}**\n\n"
            f"TC зоны: {', '.join(s['tc_keys']) if s['tc_keys'] else '—'}\n\n"
            f"Баги: {', '.join(s['bug_keys']) if s['bug_keys'] else '—'}\n\n"
            f"Бейджи: {', '.join(s['badges']) if s['badges'] else '—'}\n"
        )
        main = (f"---\n{fm_lines}\n---\n\n# {summary}\n\n"
                f"_Синтезировано из `state/escalations.md` (QAREADY-{s['iid']}) + "
                f"`docs/feature-registry.yaml` (story:{s['iid']}) — READ-ONLY, борда не меняет источники._\n\n"
                f"{body}")
        (issue_dir / "main.md").write_text(main, encoding="utf-8")

        index.append({
            "key": key, "path": f"board/{key}/main.md", "parent": None, "epic": None,
            "parentPath": None, "epicPath": None, "summary": summary, "issueType": "story",
            "status": s["stage_id"], "priority": "p2", "assignee": "qa-agents",
            "labels": labels, "updated": updated,
            "resolution": fm["resolution"], "children": [], "archived": False,
        })
        count += 1
        print(f"story-{s['iid']}: стадия {s['stage_name']}")

    (BOARD / ".trackstate" / "index" / "issues.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    (BOARD / ".trackstate" / "index" / "tombstones.json").write_text("[]", encoding="utf-8")

    # Курсор для board_inbound (docs/07 §2): снимок «что борда и артефакты содержали
    # в момент этой синхронизации» — по построению они здесь идентичны. Это ТРЕТЬЯ
    # точка отсчёта, по которой обратный канал отличает правку человека от рассинхрона.
    # _iter_artifacts() внутри неё не видит story (не файловый артефакт) — курсор
    # story не получает, board_inbound про story не знает вовсе (read-only).
    _write_inbound_cursor()

    if unmapped:
        print(f"board_sync: {len(unmapped)} артефакт(ов) с немаппящимся статусом (см. [WARN] выше; "
              f"валидация схем — не наша задача, см. validate_frontmatter.py)")
    print(f"board/ собрана: {count} тикетов ({sum(1 for i in index if i['issueType']=='test-case')} TC, "
          f"{sum(1 for i in index if i['issueType']=='bug')} bug, "
          f"{sum(1 for i in index if i['issueType']=='run')} run, "
          f"{sum(1 for i in index if i['issueType']=='story')} story)")


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
