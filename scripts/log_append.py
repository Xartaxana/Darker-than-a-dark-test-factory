"""Каноничное добавление строк в журналы конвейера.

Назначение — заменить ad-hoc `printf '%s\n' ... >> файл` с `$(date -u ...)`:
такие вызовы каждый раз требуют подтверждения (командная подстановка не
проходит статический анализ sandbox) и не проверяют формат записи.

Использование:
  python scripts/log_append.py routing --event delegated --agent builder \
      --model sonnet --category implementation --notes "что делегировано"
  python scripts/log_append.py orchestrator "Правило" "агент" "артефакт" "исход"

routing      -> logs/routing-log.jsonl (одна JSON-строка; ts подставляется сам;
                model ОБЯЗАТЕЛЬНА для delegated/escalated/accepted/rejected —
                CLAUDE.md; типизированные поля D-0053 OS-репо:
                --task-id обязателен для delegated/accepted/rejected/
                escalated/defect_found; --attempt и --failure-class —
                для rejected; --witness — для accepted по builder;
                --ref (task_id исходного accepted) — для defect_found,
                model там не требуется — она в исходном событии)
orchestrator -> state/orchestrator-log.md (строка таблицы `| ts | ... |`,
                ровно 4 ячейки после времени; ts подставляется сам)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROUTING_LOG = REPO / "logs" / "routing-log.jsonl"
ORCH_LOG = REPO / "state" / "orchestrator-log.md"

ROUTING_EVENTS = {"delegated", "accepted", "rejected", "escalated",
                  "decomposable", "dispatch_skipped", "defect_found",
                  "lead_degraded", "lead_restored"}
MODEL_REQUIRED_EVENTS = {"delegated", "escalated", "accepted", "rejected"}
TASK_REQUIRED_EVENTS = {"delegated", "accepted", "rejected", "escalated",
                        "defect_found"}
FAILURE_CLASSES = {"spec", "capability", "recon", "tooling"}


def _now_iso(*, suffix_z: bool = False) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return ts + "Z" if suffix_z else ts


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def append_routing(event: str, agent: str, *, model: str = "",
                   category: str = "", notes: str = "", task_id: str = "",
                   attempt: int = 0, failure_class: str = "",
                   witness: str = "", ref: str = "") -> str:
    if event not in ROUTING_EVENTS:
        raise SystemExit(f"неизвестное событие '{event}'; допустимы: "
                         + ", ".join(sorted(ROUTING_EVENTS)))
    if event in MODEL_REQUIRED_EVENTS and not model:
        raise SystemExit(f"--model обязательна для события '{event}' (CLAUDE.md, журнал маршрутизации)")
    if event in TASK_REQUIRED_EVENTS and not task_id:
        raise SystemExit(f"--task-id обязателен для события '{event}' (D-0053 OS-репо)")
    if event == "rejected":
        if failure_class not in FAILURE_CLASSES:
            raise SystemExit("--failure-class обязателен для 'rejected': "
                             + "/".join(sorted(FAILURE_CLASSES)) + " (D-0052/D-0053)")
        if attempt < 1:
            raise SystemExit("--attempt (>=1) обязателен для 'rejected' (правило 6, D-0053)")
    if event == "accepted" and agent == "builder" and not witness:
        raise SystemExit("--witness (фактический вывод прогона) обязателен для accepted по builder (D-0052)")
    if event == "defect_found" and not ref:
        raise SystemExit("--ref (task_id исходного accepted) обязателен для 'defect_found' (D-0052/D-0053)")
    record: dict[str, object] = {"ts": _now_iso(), "event": event, "agent": agent}
    if model:
        record["model"] = model
    if task_id:
        record["task_id"] = task_id
    if attempt:
        record["attempt"] = attempt
    if failure_class:
        record["failure_class"] = failure_class
    if witness:
        record["witness"] = witness
    if ref:
        record["ref"] = ref
    if category:
        record["category"] = category
    if notes:
        record["notes"] = notes
    line = json.dumps(record, ensure_ascii=False)
    _append_line(ROUTING_LOG, line)
    return line


def append_orchestrator(cells: list[str]) -> str:
    if len(cells) != 4:
        raise SystemExit("orchestrator ожидает ровно 4 ячейки: правило, агент, артефакт, исход")
    safe = [c.replace("|", "\\|").replace("\n", " ").strip() for c in cells]
    line = "| " + " | ".join([_now_iso(suffix_z=True)] + safe) + " |"
    _append_line(ORCH_LOG, line)
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="target", required=True)

    p_rt = sub.add_parser("routing", help="строка в logs/routing-log.jsonl")
    p_rt.add_argument("--event", required=True)
    p_rt.add_argument("--agent", required=True)
    p_rt.add_argument("--model", default="")
    p_rt.add_argument("--task-id", dest="task_id", default="")
    p_rt.add_argument("--attempt", type=int, default=0)
    p_rt.add_argument("--failure-class", dest="failure_class", default="")
    p_rt.add_argument("--witness", default="")
    p_rt.add_argument("--ref", default="")
    p_rt.add_argument("--category", default="")
    p_rt.add_argument("--notes", default="")

    p_orch = sub.add_parser("orchestrator", help="строка в state/orchestrator-log.md")
    p_orch.add_argument("cells", nargs=4,
                        metavar=("ПРАВИЛО", "АГЕНТ", "АРТЕФАКТ", "ИСХОД"))

    args = parser.parse_args(argv)
    if args.target == "routing":
        line = append_routing(args.event, args.agent, model=args.model,
                              category=args.category, notes=args.notes,
                              task_id=args.task_id, attempt=args.attempt,
                              failure_class=args.failure_class,
                              witness=args.witness, ref=args.ref)
    else:
        line = append_orchestrator(args.cells)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
