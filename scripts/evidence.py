"""evidence — доступ к контракту доказательств schemas/evidence.yaml (C2, docs/09).

Единственная библиотека, через которую скрипты/агенты отвечают на вопрос
«достаточно ли доказательств у вердикта»:
- `verdicts()` — реестр вердиктов из контракта;
- `evidence_for(verdict)` — список обязательных элементов {id, description};
- `ids_for(verdict)` — только id, для быстрой проверки набора «что уже собрано»;
- `missing(verdict, collected)` — каких id не хватает в уже собранном наборе;
- `validate()` — целостность самого контракта (гоняется self-tests'ами).

Контракт — спецификация, а не state: грузится из schemas/, кэшируется на процесс.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO / "schemas" / "evidence.yaml"

_cache: dict | None = None


def load(*, force: bool = False) -> dict:
    global _cache
    if _cache is None or force:
        import yaml
        _cache = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8")) or {}
    return _cache


def verdicts() -> list[str]:
    return list((load().get("verdicts") or {}).keys())


def evidence_for(verdict: str) -> list[dict]:
    v = (load().get("verdicts") or {}).get(verdict) or {}
    return list(v.get("evidence") or [])


def ids_for(verdict: str) -> set[str]:
    return {str(e.get("id")) for e in evidence_for(verdict)}


def missing(verdict: str, collected: set[str] | list[str]) -> set[str]:
    """Каких обязательных id не хватает в уже собранном наборе `collected`."""
    return ids_for(verdict) - set(collected)


def validate() -> list[str]:
    """Внутренняя целостность контракта. Пусто = ок."""
    errors: list[str] = []
    data = load()
    verdicts_map = data.get("verdicts") or {}
    if not verdicts_map:
        errors.append("verdicts: пустой реестр")
        return errors
    for verdict, spec in verdicts_map.items():
        items = (spec or {}).get("evidence") or []
        if not items:
            errors.append(f"{verdict}: пустой список evidence")
            continue
        seen_ids: set[str] = set()
        for item in items:
            iid = str((item or {}).get("id") or "").strip()
            desc = str((item or {}).get("description") or "").strip()
            if not iid:
                errors.append(f"{verdict}: элемент без id")
            elif iid in seen_ids:
                errors.append(f"{verdict}: дубль id `{iid}`")
            else:
                seen_ids.add(iid)
            if not desc:
                errors.append(f"{verdict}: `{iid or '?'}` без description")
    return errors


def main() -> int:
    errors = validate()
    for e in errors:
        print(f"  [ERROR] {e}")
    vs = verdicts()
    print(f"evidence: вердиктов {len(vs)}, ошибок {len(errors)}; " +
          ", ".join(f"{v}:{len(evidence_for(v))}" for v in vs))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
