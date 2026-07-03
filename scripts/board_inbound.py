"""board_inbound — обратный канал борды: переходы человека с борды → артефакты.

Ядро дизайна docs/07-board-inbound.md. Артефакты (bugs/, test-cases/) остаются
источником правды; борда — интерфейс, с которого человек двигает карточки. Наивный
diff «борда vs артефакт» неоднозначен (борда впереди = человек подвинул; артефакт
впереди = агент изменил, борда отстала), поэтому классифицируем через ТРЕТЬЮ точку —
курсор последней синхронизации (state/board-cursor.json, пишет board_sync).

Запуск:  python scripts/board_inbound.py [--dry-run]
Выполняется оркестратором на шаге 0 прохода, ДО любого board_sync (docs/06 §1).

ЯДРО (этот файл): курсор-сверка, whitelist, применение статуса, конфликт→Blocked.
ОБВЯЗКА (делегируется, помечено TODO): git pull борды, синхронизация комментариев,
формат TrackState-комментариев, вызов из pre_steps.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows-консоль по умолчанию cp1251 и падает на '→'/кириллице в выводе. Фабрика
# автономна — не полагаемся на PYTHONIOENCODING, форсируем UTF-8 сами.
try:
    sys.stdout.reconfigure(encoding="utf-8")
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

# Whitelist переходов человека (docs/06 §3, docs/07 §3). Значение — множество
# допустимых целевых статусов; "*" среди источников = из любого статуса.
# Формат: {itype: {from_status: {to_status, ...}}}
WHITELIST = {
    "bug": {
        "Open":     {"Fixed", "Rejected", "Intended", "Blocked"},
        "Reopened": {"Fixed", "Rejected", "Intended", "Blocked"},
        "*":        {"Open"},  # ручное переоткрытие из любого статуса
    },
    "test-case": {
        "Draft":  {"Approved"},
        "Review": {"Approved"},
        "*":      {"Review"},  # вернуть на доработку из любого статуса
    },
    "run": {},  # переходы с борды не принимаются, только комментарии
}


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
    applied = sum(1 for a in actions if a.kind == "apply")
    conflicts = sum(1 for a in actions if a.kind == "conflict")
    rejected = sum(1 for a in actions if a.kind == "reject")
    print(f"board-inbound{' (dry-run)' if dry else ''}: "
          f"{applied} применено, {conflicts} конфликтов, {rejected} отклонено, "
          f"{len(actions) - applied - conflicts - rejected} без изменений")
    return actions


def main() -> None:
    ap = argparse.ArgumentParser(description="Обратный канал борды → артефакты (docs/07)")
    ap.add_argument("--dry-run", action="store_true", help="показать действия, не менять артефакты")
    args = ap.parse_args()
    # TODO(обвязка): git pull борды с origin ДО сверки, чтобы видеть коммиты человека.
    # TODO(обвязка): синхронизация комментариев карточка ↔ ## Обсуждение (docs/07 §5).
    reconcile(dry=args.dry_run)


if __name__ == "__main__":
    main()
