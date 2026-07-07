"""validate_frontmatter — preflight-валидация артефактов по schemas/*.schema.yaml (G3).

Битый frontmatter (опечатка в статусе, потерянное поле, дубль id) раньше всплывал
только в момент, когда правило /qa-loop или скрипт спотыкались об артефакт.
Теперь ловим до диспетчеризации: /qa-loop запускает валидатор в preflight.

Проверки:
- frontmatter присутствует и парсится;
- required-поля есть и непусты;
- id соответствует id_pattern своего типа;
- enum/pattern полей из схемы (PyYAML-коэрция дат учитывается: datetime → ISO);
- id уникален в пределах репозитория;
- поле не из схемы — [WARN], не ошибка (шаблоны эволюционируют).

Запуск: python scripts/validate_frontmatter.py
Коды выхода: 0 — чисто (WARN допустимы); 1 — есть ошибки (список в stdout).
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import board_sync as bs

REPO = bs.REPO
SCHEMAS = REPO / "schemas"
AREAS = (("test-cases", "test-case"), ("bugs", "bug"), ("runs", "run"))


def load_schema(itype: str) -> dict:
    p = SCHEMAS / f"{itype}.schema.yaml"
    if not p.exists():
        return {}
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _s(value) -> str:
    """Значение frontmatter → строка для pattern-проверок (учёт коэрции PyYAML)."""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def check_meta(meta: dict, schema: dict, rel: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []

    for f in schema.get("required", []):
        if _s(meta.get(f)).strip() == "":
            errors.append(f"{rel}: required-поле `{f}` отсутствует или пусто")

    idp = schema.get("id_pattern")
    if idp and meta.get("id") is not None and not re.match(idp, _s(meta["id"])):
        errors.append(f"{rel}: id `{_s(meta['id'])}` не соответствует `{idp}`")

    fields = schema.get("fields", {}) or {}
    for name, value in meta.items():
        if name in ("id",):
            continue
        spec = fields.get(name)
        if spec is None:
            if name not in schema.get("required", []):
                warns.append(f"{rel}: поле `{name}` не описано в схеме {schema.get('type')}")
            continue
        sval = _s(value)
        if "enum" in spec and sval and sval not in [str(e) for e in spec["enum"]]:
            errors.append(f"{rel}: `{name}: {sval}` вне enum {spec['enum']}")
        if "pattern" in spec and sval and not re.match(spec["pattern"], sval):
            errors.append(f"{rel}: `{name}: {sval}` не соответствует `{spec['pattern']}`")
    return errors, warns


def validate() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    seen_ids: dict[str, str] = {}

    for area, itype in AREAS:
        base = REPO / area
        if not base.exists():
            continue
        schema = load_schema(itype)
        if not schema:
            warns.append(f"schemas/{itype}.schema.yaml не найдена — тип {itype} не проверен")
            continue
        for md in sorted(base.rglob("*.md")):
            if md.name.upper() == "README.MD":
                continue
            rel = md.relative_to(REPO).as_posix()
            meta, _body = bs._parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            if not meta:
                errors.append(f"{rel}: frontmatter отсутствует или не парсится")
                continue
            key = _s(meta.get("id"))
            if key:
                if key in seen_ids:
                    errors.append(f"{rel}: дубль id `{key}` (уже в {seen_ids[key]})")
                else:
                    seen_ids[key] = rel
            e, w = check_meta(meta, schema, rel)
            errors += e
            warns += w
    return errors, warns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Валидация frontmatter по schemas/")
    parser.add_argument("--no-warns", action="store_true", help="не печатать WARN")
    args = parser.parse_args(argv)

    errors, warns = validate()
    for e in errors:
        print(f"  [ERROR] {e}")
    if not args.no_warns:
        for w in warns:
            print(f"  [WARN] {w}")
    print(f"validate_frontmatter: ошибок {len(errors)}, предупреждений {len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
