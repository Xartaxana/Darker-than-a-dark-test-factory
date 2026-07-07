"""agent_output — парсер machine-readable результата воркера (F2, docs/09).

Верхний уровень /qa-loop не разбирает свободный текст агента: из ответа
извлекается ПОСЛЕДНИЙ fenced-блок ```yaml с top-level ключом agent_output и
валидируется по schemas/agent-output.schema.yaml. Нет блока / блок битый →
(None, errors) — диспетчер трактует исход как degraded.

Использование: from agent_output import parse;  data, errors = parse(text)
CLI (для отладки/репетиций): python scripts/agent_output.py < файл_с_ответом
"""
from __future__ import annotations

import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import board_sync as bs

REPO = bs.REPO
SCHEMA_PATH = REPO / "schemas" / "agent-output.schema.yaml"

FENCE_RE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)

LIST_FIELDS = ("changed_files", "evidence", "next_rules", "escalations")


def _schema() -> dict:
    import yaml
    return yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8")) or {}


def parse(text: str) -> tuple[dict | None, list[str]]:
    """(payload, errors). payload=None только если блока нет/не парсится."""
    import yaml
    blocks = FENCE_RE.findall(text or "")
    payload = None
    for raw in reversed(blocks):          # контракт: последний блок побеждает
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and isinstance(data.get("agent_output"), dict):
            payload = data["agent_output"]
            break
    if payload is None:
        return None, ["нет валидного ```yaml-блока с ключом agent_output"]

    schema = _schema()
    errors: list[str] = []
    for f in schema.get("required", []):
        if str(payload.get(f) or "").strip() == "":
            errors.append(f"required-поле `{f}` отсутствует или пусто")
    fields = schema.get("fields", {}) or {}
    for name, spec in fields.items():
        value = payload.get(name)
        if value is None:
            continue
        enum = (spec or {}).get("enum")
        if enum and str(value) not in [str(e) for e in enum]:
            errors.append(f"`{name}: {value}` вне enum {enum}")
    for name in LIST_FIELDS:
        value = payload.get(name)
        if value is None:
            payload[name] = []            # нормализация: отсутствие == пустой список
        elif not isinstance(value, list):
            errors.append(f"`{name}` должен быть списком, получено: {type(value).__name__}")
    return payload, errors


def main() -> int:
    data, errors = parse(sys.stdin.read())
    for e in errors:
        print(f"  [ERROR] {e}")
    if data:
        print(f"agent_output: agent={data.get('agent')} artifact={data.get('artifact')} "
              f"result={data.get('result')} (ошибок: {len(errors)})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
