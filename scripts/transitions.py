"""transitions — доступ к матрице переходов schemas/transitions.yaml (C3, docs/09).

Единственная библиотека, через которую скрипты фабрики отвечают на вопросы:
- легален ли переход X→Y для актора A (`is_allowed`);
- какие переходы человек может делать С БОРДЫ (`board_whitelist` —
  board_inbound.WHITELIST строится отсюда, а не литералом);
- какие эффекты обязателен переход (`effects_for`);
- цела ли сама матрица (`validate` — гоняется self-tests'ами).

Матрица — спецификация, а не state: грузится из schemas/, кэшируется на процесс.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import board_sync as bs

REPO = bs.REPO
MATRIX_PATH = REPO / "schemas" / "transitions.yaml"

_cache: dict | None = None


def load(*, force: bool = False) -> dict:
    global _cache
    if _cache is None or force:
        import yaml
        _cache = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8")) or {}
    return _cache


def _machine(itype: str) -> dict:
    return (load().get("machines") or {}).get(itype) or {}


def statuses(itype: str) -> list[str]:
    return list(_machine(itype).get("statuses") or [])


def _factory_actors() -> set[str]:
    groups = (load().get("actors") or {}).get("groups") or {}
    return set(groups.get("factory") or [])


def find(itype: str, frm: str, to: str) -> list[dict]:
    """Все правила матрицы, покрывающие переход frm→to (учитывая from: "*")."""
    out = []
    for t in _machine(itype).get("transitions") or []:
        if t.get("to") == to and t.get("from") in (frm, "*"):
            out.append(t)
    return out


def is_allowed(itype: str, frm: str, to: str, actor: str) -> bool:
    """Легален ли переход для актора. Актор: "human", имя агента/скрипта.

    "factory" в by разрешает любого актора из actors.groups.factory;
    неизвестный актор не разрешён ничем, кроме прямого упоминания."""
    if frm == to:
        return False
    factory = _factory_actors()
    for t in find(itype, frm, to):
        by = t.get("by") or []
        if actor in by:
            return True
        if "factory" in by and actor in factory:
            return True
    return False


def effects_for(itype: str, frm: str, to: str) -> set[str]:
    """Обязательные эффекты перехода: always_effects + effects всех правил."""
    eff = set(load().get("always_effects") or [])
    for t in find(itype, frm, to):
        eff.update(t.get("effects") or [])
    return eff


def board_whitelist() -> dict[str, dict[str, set[str]]]:
    """Whitelist переходов человека С БОРДЫ: {itype: {from: {to, ...}}}.

    Формат совместим с board_inbound (ключ "*" = из любого статуса). Попадают
    только переходы с via_board: true и human в by."""
    out: dict[str, dict[str, set[str]]] = {}
    for itype, machine in (load().get("machines") or {}).items():
        wl: dict[str, set[str]] = {}
        for t in machine.get("transitions") or []:
            if not t.get("via_board"):
                continue
            if "human" not in (t.get("by") or []):
                continue
            wl.setdefault(str(t["from"]), set()).add(str(t["to"]))
        out[itype] = wl
    return out


def validate() -> list[str]:
    """Внутренняя целостность матрицы. Пусто = ок."""
    errors: list[str] = []
    data = load()
    factory = _factory_actors()
    known_actors = factory | {"human", "factory"}

    for itype, machine in (data.get("machines") or {}).items():
        sts = set(machine.get("statuses") or [])
        if not sts:
            errors.append(f"{itype}: пустой список statuses")
            continue
        for field in ("initial", "terminal"):
            for s in machine.get(field) or []:
                if s not in sts:
                    errors.append(f"{itype}: {field} `{s}` нет в statuses")
        seen: set[tuple] = set()
        for t in machine.get("transitions") or []:
            frm, to = str(t.get("from")), str(t.get("to"))
            if frm != "*" and frm not in sts:
                errors.append(f"{itype}: from `{frm}` нет в statuses")
            if to not in sts:
                errors.append(f"{itype}: to `{to}` нет в statuses")
            if frm == to:
                errors.append(f"{itype}: петля {frm}→{to} запрещена")
            by = t.get("by") or []
            if not by:
                errors.append(f"{itype}: {frm}→{to} без акторов (by)")
            for actor in by:
                if actor not in known_actors:
                    errors.append(f"{itype}: {frm}→{to} неизвестный актор `{actor}`")
            key = (frm, to, tuple(sorted(by)))
            if key in seen:
                errors.append(f"{itype}: дубль правила {frm}→{to} {by}")
            seen.add(key)
            # Блокировка обязана оставлять след человеку
            if to == "Blocked" and "escalation" not in (t.get("effects") or []):
                errors.append(f"{itype}: {frm}→Blocked без эффекта escalation")
        # Терминальный статус: фабрика из него не выводит (только человек)
        for term in machine.get("terminal") or []:
            for t in machine.get("transitions") or []:
                if t.get("from") == term and set(t.get("by") or []) - {"human"}:
                    errors.append(f"{itype}: из терминального {term} есть не-human переход")
    return errors


def main() -> int:
    errors = validate()
    for e in errors:
        print(f"  [ERROR] {e}")
    wl = board_whitelist()
    print(f"transitions: машин {len(load().get('machines') or {})}, ошибок {len(errors)}; "
          f"board-whitelist: " + ", ".join(
            f"{k}:{sum(len(v) for v in wl[k].values())}" for k in sorted(wl)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
