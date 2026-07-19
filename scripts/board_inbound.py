"""board_inbound — обратный канал борды: переходы человека с борды → артефакты.

Ядро дизайна docs/07-board-inbound.md. Артефакты (bugs/, test-cases/) остаются
источником правды; борда — интерфейс, с которого человек двигает карточки. Наивный
diff «борда vs артефакт» неоднозначен (борда впереди = человек подвинул; артефакт
впереди = агент изменил, борда отстала), поэтому классифицируем через ТРЕТЬЮ точку —
курсор последней синхронизации (state/board-cursor.json, пишет board_sync).

Запуск:  python scripts/board_inbound.py [--dry-run]
Выполняется оркестратором на шаге 0 прохода, ДО любого board_sync (docs/06 §1).

ЯДРО (этот файл): курсор-сверка, whitelist, применение статуса, конфликт→Blocked.
ОБВЯЗКА (реализована в этом же файле): pull_board() — git pull борды с origin перед
сверкой (деградирует при офлайне); collect_board_comments()/append_discussion()/
sync_comments() — перенос комментариев карточек TrackState в ## Обсуждение артефакта
(формат board/<KEY>/comments/<NNNN>.md, реверс по исходникам TrackState — см. §5 ниже).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows-консоль по умолчанию cp1251 и падает на '→'/кириллице в выводе. Фабрика
# автономна — не полагаемся на PYTHONIOENCODING, форсируем UTF-8 сами.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Переиспользуем парсер frontmatter и маппинг статусов — единственное место правды.
import board_sync as bs

REPO = bs.REPO
BOARD = bs.BOARD
CURSOR_PATH = REPO / "state" / "board-cursor.json"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"

# Обратный маппинг: id статуса TrackState -> наш статус, по типу артефакта.
INV_STATUS_MAP = {
    itype: {sid: name for name, sid in mapping.items()}
    for itype, mapping in bs.STATUS_MAP.items()
}

# Whitelist переходов человека С БОРДЫ (docs/06 §3, docs/07 §3). С 2026-07-07
# НЕ литерал: выводится из матрицы schemas/transitions.yaml (переходы с
# via_board: true и human в by) — единый источник правды C3. Паритет со старым
# литералом закреплён в scripts/tests/test_transitions.py.
# Формат: {itype: {from_status: {to_status, ...}}}, "*" = из любого статуса.
import transitions as tr
WHITELIST = tr.board_whitelist()


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TicketState:
    key: str
    itype: str
    artifact_status: str | None       # статус в артефакте сейчас
    board_status: str | None          # статус карточки сейчас (наш статус, не id)
    src: Path | None                  # путь к артефакту
    cursor_artifact: str | None       # статус артефакта на момент прошлого sync
    cursor_board: str | None          # статус карточки на момент прошлого sync (наш статус)


@dataclass
class Action:
    key: str
    kind: str                          # "apply" | "conflict" | "reject" | "noop"
    detail: str
    src: Path | None = None
    new_status: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Comment:
    """Одна реплика карточки борды. Контракт §5 docs/07.

    author/created — из frontmatter файла комментария TrackState; body — текст."""
    key: str
    author: str
    created: str        # ISO-8601, как хранит TrackState (created/updated комментария)
    body: str
    cid: str            # id файла комментария (имя без .md, напр. "0001") — для диагностики


# --- Чтение состояний ------------------------------------------------------

def load_cursor() -> dict:
    """Курсор последней синхронизации. Пусто/нет файла = первый запуск (всё noop)."""
    if not CURSOR_PATH.exists():
        return {}
    try:
        return json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_artifact_status() -> dict[str, tuple[str, str, Path]]:
    """key -> (itype, status, path) из артефактов (переиспользуем board_sync)."""
    out = {}
    for itype, meta, _body, src in bs._iter_artifacts():
        key = str(meta.get("id"))
        out[key] = (itype, str(meta.get("status", "")), src)
    return out


def _read_board_status() -> dict[str, tuple[str, str]]:
    """key -> (itype, наш_статус) из board/<KEY>/main.md (frontmatter status = id)."""
    out = {}
    if not BOARD.exists():
        return out
    for main in sorted(BOARD.glob("*/main.md")):
        meta, _body = bs._parse_frontmatter(main.read_text(encoding="utf-8", errors="replace"))
        key = str(meta.get("key") or main.parent.name)
        itype = str(meta.get("issueType", ""))
        status_id = str(meta.get("status", ""))
        our_status = INV_STATUS_MAP.get(itype, {}).get(status_id)
        if our_status:
            out[key] = (itype, our_status)
    return out


def gather() -> list[TicketState]:
    cursor = load_cursor()
    arts = _read_artifact_status()
    board = _read_board_status()
    keys = set(arts) | set(board) | set(cursor)
    states: list[TicketState] = []
    for key in sorted(keys):
        itype_a = arts.get(key, (None, None, None))[0]
        itype_b = board.get(key, (None, None))[0]
        cur = cursor.get(key, {})
        states.append(TicketState(
            key=key,
            itype=itype_a or itype_b or cur.get("itype") or "",
            artifact_status=arts.get(key, (None, None, None))[1],
            board_status=board.get(key, (None, None))[1],
            src=arts.get(key, (None, None, None))[2],
            cursor_artifact=cur.get("artifact_status"),
            cursor_board=cur.get("board_status"),
        ))
    return states


# --- Классификация (ядро §2) ----------------------------------------------

def classify(ts: TicketState) -> Action:
    # Первый запуск / тикет без курсора: нечего сверять, считаем базой (noop).
    if ts.cursor_board is None and ts.cursor_artifact is None:
        return Action(ts.key, "noop", "нет курсора (первый sync) — принято за базу")

    human_moved = ts.board_status is not None and ts.board_status != ts.cursor_board
    agent_moved = ts.artifact_status is not None and ts.artifact_status != ts.cursor_artifact

    if not human_moved and not agent_moved:
        return Action(ts.key, "noop", "без изменений")
    if agent_moved and not human_moved:
        return Action(ts.key, "noop", "изменил агент, борда догонит при sync")
    if human_moved and agent_moved:
        return Action(
            ts.key, "conflict",
            f"конфликт: человек {ts.cursor_board}→{ts.board_status}, "
            f"агент {ts.cursor_artifact}→{ts.artifact_status}",
            src=ts.src, extra={"human_to": ts.board_status, "agent_to": ts.artifact_status},
        )

    # Только человек подвинул — проверяем whitelist.
    src_status = ts.cursor_artifact or "*"
    target = ts.board_status
    allowed = WHITELIST.get(ts.itype, {})
    ok = target in allowed.get(src_status, set()) or target in allowed.get("*", set())
    if not ok:
        return Action(
            ts.key, "reject",
            f"переход {src_status}→{target} не в whitelist для {ts.itype} — игнор (sync вернёт карточку)",
        )
    return Action(
        ts.key, "apply", f"{src_status}→{target}",
        src=ts.src, new_status=target,
    )


# --- Применение (ядро §3, §4) ---------------------------------------------

def _rewrite_field(text: str, field: str, value: str) -> tuple[str, bool]:
    """Заменяет строку `field: ...` во frontmatter. Возвращает (текст, изменено)."""
    pat = re.compile(rf"(?m)^{re.escape(field)}:\s*.*$")
    if pat.search(text):
        return pat.sub(f'{field}: {value}', text, count=1), True
    return text, False


def _set_field(text: str, field: str, value: str) -> str:
    """Заменяет строку `field: ...`, а если её нет — ВСТАВЛЯЕТ сразу после `status:`.

    Нужно для старых артефактов без status_since/reopen_count (созданы до шаблона
    docs/06): без вставки SLA-sweep не увидит время перехода."""
    new, changed = _rewrite_field(text, field, value)
    if changed:
        return new
    # Вставляем после строки status: (она всегда есть во frontmatter артефакта).
    return re.sub(r"(?m)^(status:\s*.*)$", rf"\1\n{field}: {value}", text, count=1)


def _bump_reopen_count(text: str) -> str:
    m = re.search(r"(?m)^reopen_count:\s*(\d+)\s*$", text)
    if m:
        return re.sub(r"(?m)^reopen_count:\s*\d+\s*$",
                      f"reopen_count: {int(m.group(1)) + 1}", text, count=1)
    return _set_field(text, "reopen_count", "1")  # старый артефакт без поля


def apply_status(src: Path, new_status: str, *, dry: bool) -> str:
    text = src.read_text(encoding="utf-8")
    stamp = _utcnow()
    new, changed = _rewrite_field(text, "status", new_status)
    if not changed:
        return f"  [WARN] {src.name}: нет строки status: — пропуск"
    # status_since обязателен для SLA-sweep — вставляем, если поля нет (старые артефакты).
    new = _set_field(new, "status_since", f'"{stamp}"')
    new, _ = _rewrite_field(new, "updated", f'"{stamp}"')
    if new_status == "Reopened":
        new = _bump_reopen_count(new)
    if not dry:
        src.write_text(new, encoding="utf-8")
    return f"  [OK] {src.name}: status → {new_status} (status_since={stamp})"


def apply_conflict(action: Action, ts_board: str, ts_agent: str, *, dry: bool) -> str:
    """Конфликт (§4): артефакт → Blocked, строка в escalations, реплика в обсуждение."""
    if action.src is None:
        return f"  [WARN] {action.key}: конфликт без артефакта — только эскалация"
    text = action.src.read_text(encoding="utf-8")
    stamp = _utcnow()
    new, changed = _rewrite_field(text, "status", "Blocked")
    new = _set_field(new, "status_since", f'"{stamp}"')
    new, _ = _rewrite_field(new, "updated", f'"{stamp}"')
    # B5: конфликт борда↔артефакт нужно решить человеку — product_decision.
    new = _set_field(new, "blocked_reason", "product_decision")
    if not dry and changed:
        action.src.write_text(new, encoding="utf-8")
        _append_escalation(
            action.key,
            f"конфликт борда↔артефакт: человек→{ts_board}, агент→{ts_agent}. "
            f"Артефакт переведён в Blocked, нужно решение человека.",
        )
    return f"  [CONFLICT] {action.key}: CONFLICT → Blocked + эскалация (человек→{ts_board}, агент→{ts_agent})"


def _append_escalation(key: str, reason: str) -> None:
    stamp = _utcnow()
    line = f"- [{stamp}] **{key}** — {reason}\n"
    header = "" if ESCALATIONS_PATH.exists() else (
        "# Эскалации фабрики\n\nАктивные варнинги, требующие человека "
        "(docs/06 §4). Строку удаляет человек по разрешении.\n\n"
    )
    with ESCALATIONS_PATH.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(line)


# --- Синхронизация комментариев борда ↔ ## Обсуждение (обвязка, docs/07 §5) ----
#
# ФОРМАТ ХРАНЕНИЯ КОММЕНТАРИЕВ TrackState (реверс по исходникам IstiN/trackstate,
# lib/data/repositories/trackstate_repository{,_helpers,_mutations}.dart):
#   каждая реплика карточки — ОТДЕЛЬНЫЙ файл  board/<KEY>/comments/<NNNN>.md
#   (id зерокрополнен до 4 знаков: 0001.md, 0002.md, …; см. _nextCommentId).
#   Тело файла — markdown с YAML-frontmatter, который пишет _buildCommentMarkdown:
#       ---
#       author: "<identity>"      # строка в кавычках (_yamlScalar экранирует \ и ")
#       created: <ISO-8601 UTC>   # напр. 2026-07-04T10:00:00.000Z, БЕЗ кавычек
#       updated: <ISO-8601 UTC>
#       ---
#       <текст реплики>
#   При чтении (_parseComment) значимы поля author/created/updated и тело.
# Это НЕ гипотеза — формат снят напрямую с кода провайдера. Единственное допущение:
# board_sync (rmtree+регенерация) не пишет comments/ и не трогает их, поэтому папка
# comments/ живёт как «человеческая сторона» рядом с main.md — это согласуется с
# дизайном docs/07 §2 (правки человека в board/, наш курсор — в state/).

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def _parse_comment_file(path: Path) -> Comment | None:
    """Парсит один board/<KEY>/comments/<NNNN>.md в Comment. None — если не разобрать."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # ВАЖНО: created/updated читаем СЫРЫМИ строками, а не через bs._parse_frontmatter —
    # тот прогоняет frontmatter через PyYAML, который коэрсит ISO-таймстамп в
    # datetime и при str() выдаёт "2026-07-04 10:00:00+00:00" (пробел вместо T,
    # без .000Z). Для комментария нужна точная строка автора, как её записал TrackState.
    m = _FM_RE.match(text)
    if not m:
        return None
    fm, body = m.group(1), m.group(2)
    raw = {}
    for line in fm.splitlines():
        mm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if mm:
            raw[mm.group(1)] = mm.group(2).strip().strip('"')
    author = raw.get("author") or "unknown"
    created = raw.get("created") or raw.get("updated") or ""
    key = path.parent.parent.name
    return Comment(key=key, author=author, created=created,
                   body=(body or "").strip(), cid=path.stem)


def collect_board_comments(key: str) -> list[Comment]:
    """Читает все комментарии карточки board/<KEY>/comments/*.md, сорт. по id.

    Возвращает пустой список, если у карточки ещё нет комментариев (текущее
    состояние борды). Контракт §5 docs/07: обвязка над форматом TrackState."""
    comments_dir = BOARD / key / "comments"
    if not comments_dir.exists():
        return []
    out: list[Comment] = []
    for p in sorted(comments_dir.glob("*.md")):
        c = _parse_comment_file(p)
        if c and c.body:
            out.append(c)
    return out


# Дедупликация: реплики, уже перенесённые в ## Обсуждение, помечаются якорем
# автор@время в начале строки. Формат реплики (docs/06 §2, шаблон bug-report):
#   **[автор @ ISO-время]** текст
_DISCUSSION_HEADER = "## Обсуждение"
_REPLICA_RE = re.compile(r"^\*\*\[(?P<author>.+?) @ (?P<time>.+?)\]\*\*", re.M)


def _existing_replicas(text: str) -> set[tuple[str, str, str]]:
    """Множество (автор, время, первая-строка-текста) уже перенесённых реплик.

    Сопоставление по автору+времени+тексту (требование дедупликации docs/07 §5).
    Текст берём как первую непустую строку после маркера — этого достаточно, чтобы
    отличить разные реплики с одинаковым автором/временем и не тащить весь абзац."""
    out: set[tuple[str, str, str]] = set()
    if _DISCUSSION_HEADER not in text:
        return out
    section = text.split(_DISCUSSION_HEADER, 1)[1]
    lines = section.splitlines()
    for i, line in enumerate(lines):
        m = _REPLICA_RE.match(line)
        if not m:
            continue
        after = line[m.end():].strip()
        if not after:
            # текст на следующей строке
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    after = nxt.strip()
                    break
        out.add((m.group("author").strip(), m.group("time").strip(), after))
    return out


def _replica_key(c: Comment) -> tuple[str, str, str]:
    first = next((ln.strip() for ln in c.body.splitlines() if ln.strip()), "")
    return (c.author, c.created, first)


def append_discussion(artifact_path: Path, comment: Comment, *, dry: bool) -> str:
    """Дозаписывает реплику comment в раздел ## Обсуждение артефакта (docs/06 §2).

    Формат строки: `**[автор @ ISO-время]** текст`. Реплика человека → фабрике ход:
    выставляем `awaiting: qa`. Раздел создаётся, если его нет (старые артефакты до
    шаблона docs/06). Дедупликация — на стороне sync_comments (по _replica_key)."""
    text = artifact_path.read_text(encoding="utf-8")
    replica = f"**[{comment.author} @ {comment.created}]** {comment.body.strip()}\n"

    if _DISCUSSION_HEADER in text:
        # Дозапись в конец существующего раздела (последний раздел файла по шаблону).
        new = text.rstrip("\n") + "\n\n" + replica
    else:
        new = text.rstrip("\n") + f"\n\n{_DISCUSSION_HEADER}\n\n" + replica

    # Реплика человека → ход за фабрикой (awaiting: qa). Поле может отсутствовать
    # в старом артефакте — тогда вставляем его во frontmatter после status:.
    new = _set_field(new, "awaiting", "qa")
    stamp = _utcnow()
    new, _ = _rewrite_field(new, "updated", f'"{stamp}"')

    if not dry:
        artifact_path.write_text(new, encoding="utf-8")
    return f"  [COMMENT] {comment.key}: перенесена реплика [{comment.author} @ {comment.created}] (awaiting: qa)"


def sync_comments(states: dict[str, TicketState], *, dry: bool) -> int:
    """Переносит НОВЫЕ комментарии карточек в ## Обсуждение артефактов. Возвращает
    число перенесённых реплик. Дедуп: пропускаем уже присутствующие (автор+время+текст)."""
    moved = 0
    for key, ts in states.items():
        if ts.src is None:
            continue  # нет артефакта (карточка-сирота) — переносить некуда
        board_comments = collect_board_comments(key)
        if not board_comments:
            continue
        text = ts.src.read_text(encoding="utf-8")
        existing = _existing_replicas(text)
        for c in board_comments:
            if _replica_key(c) in existing:
                continue
            print(append_discussion(ts.src, c, dry=dry))
            existing.add(_replica_key(c))  # не дублировать в пределах одного прохода
            moved += 1
    return moved


# --- git pull борды (обвязка, docs/07 §7) ----------------------------------

def pull_board(*, dry: bool) -> None:
    """Подтягивает коммиты человека (переходы/комментарии борды) с origin ДО сверки.

    Требование автономности (docs/06 §5): офлайн/недоступность origin НЕ должна
    вешать проход — при любой ошибке пишем предупреждение и продолжаем на локальной
    борде. Без интерактива, один pull текущей ветки, короткий таймаут."""
    if dry:
        print("board-inbound: --dry-run — git pull пропущен")
        return
    # Есть ли origin вообще (может не быть настроен локально).
    try:
        remotes = subprocess.run(
            ["git", "remote"], cwd=str(REPO), capture_output=True,
            text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"board-inbound: git недоступен ({e}) — работаю на локальной борде")
        return
    if "origin" not in remotes.stdout.split():
        print("board-inbound: origin не настроен — работаю на локальной борде")
        return
    try:
        # --no-edit/--no-rebase: без интерактивного редактора merge-сообщения.
        r = subprocess.run(
            ["git", "pull", "--no-edit", "--no-rebase", "origin", "HEAD"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("board-inbound: [WARN] git pull завис (таймаут) — работаю на локальной борде")
        return
    except (OSError, subprocess.SubprocessError) as e:
        print(f"board-inbound: [WARN] git pull не удался ({e}) — работаю на локальной борде")
        return
    if r.returncode == 0:
        tail = (r.stdout or "").strip().splitlines()
        print(f"board-inbound: git pull ok" + (f" — {tail[-1]}" if tail else ""))
    else:
        err = (r.stderr or r.stdout or "").strip().splitlines()
        msg = err[-1] if err else "неизвестная ошибка"
        print(f"board-inbound: [WARN] git pull origin недоступен ({msg}) — работаю на локальной борде")


# --- Оркестрация -----------------------------------------------------------

def reconcile(*, dry: bool) -> list[Action]:
    states = {ts.key: ts for ts in gather()}
    actions = [classify(ts) for ts in states.values()]
    for a in actions:
        if a.kind == "apply":
            print(apply_status(a.src, a.new_status, dry=dry))
        elif a.kind == "conflict":
            ts = states[a.key]
            print(apply_conflict(a, ts.board_status, ts.artifact_status, dry=dry))
        elif a.kind == "reject":
            print(f"  [SKIP] {a.key}: {a.detail}")
        # noop — молча
    # Синхронизация комментариев карточек → ## Обсуждение (docs/07 §5). Идёт после
    # статусов: конфликт мог перевести артефакт в Blocked, но реплики переносим всегда.
    comments_moved = sync_comments(states, dry=dry)
    applied = sum(1 for a in actions if a.kind == "apply")
    conflicts = sum(1 for a in actions if a.kind == "conflict")
    rejected = sum(1 for a in actions if a.kind == "reject")
    print(f"board-inbound{' (dry-run)' if dry else ''}: "
          f"{applied} применено, {conflicts} конфликтов, {rejected} отклонено, "
          f"{comments_moved} реплик перенесено, "
          f"{len(actions) - applied - conflicts - rejected} без изменений")
    # Продвигаем курсор к ТЕКУЩЕМУ согласованному состоянию (docs/07 §2.1). Курсор
    # обязан продвигать тот, кто ОБРАБОТАЛ изменения, а не только board_sync: иначе
    # если sync не отработает в конце прохода (краш/пропуск), следующий проход увидит
    # ЛОЖНЫЙ конфликт (борда=цель человека, артефакт=применённая цель, курсор=старый →
    # human_moved И agent_moved). board_sync в конце прохода перезапишет курсор финалом.
    if not dry:
        _advance_cursor()
    return actions


def _advance_cursor() -> None:
    """Пишет state/board-cursor.json = текущее (артефакт, борда) для каждого тикета.

    Вызывается в конце board_inbound после применения. В отличие от курсора board_sync
    (там борда == артефакт по построению), здесь фиксируем ФАКТИЧЕСКИЕ раздельные
    состояния борды и артефакта — это корректная база отсчёта для следующего прохода
    даже если борда отстала от артефакта (агент менял, sync не успел)."""
    arts = _read_artifact_status()   # key -> (itype, status, path)
    board = _read_board_status()     # key -> (itype, наш_статус)
    cursor = {}
    for key in set(arts) | set(board):
        itype = (arts.get(key) or board.get(key) or (None,))[0]
        cursor[key] = {
            "itype": itype,
            "artifact_status": arts.get(key, (None, None, None))[1],
            "board_status": board.get(key, (None, None))[1],
        }
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(cursor, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Обратный канал борды → артефакты (docs/07)")
    ap.add_argument("--dry-run", action="store_true", help="показать действия, не менять артефакты")
    args = ap.parse_args()
    # Обвязка (docs/07 §7): подтянуть коммиты человека с origin ДО сверки. Не вешает
    # проход при офлайне — деградирует до локальной борды с предупреждением.
    pull_board(dry=args.dry_run)
    # Обвязка (docs/07 §5): синхронизация комментариев карточка ↔ ## Обсуждение
    # выполняется внутри reconcile() (sync_comments), после применения статусов.
    reconcile(dry=args.dry_run)


if __name__ == "__main__":
    main()
