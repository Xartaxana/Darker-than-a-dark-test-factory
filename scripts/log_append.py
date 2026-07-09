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
                model там не требуется — она в исходном событии;
                D-0060/F-23: delegated с НОВЫМ task_id, чей ФОРМАТ
                полностью (full-match ^t-(\\d+)$, не substring) совпадает
                с последовательностью t-NNN, обязан быть ровно
                max(существующих full-match t-NNN)+1 — иначе отказ с
                ожидаемым id; новый описательный id (at-bug-005,
                fix-t-12-encoding — substring "t-12" не в счёт) проходит
                свободно, его новизна уже гарантирована условием "не
                встречался"; delegated повторно на task_id, чьё последнее
                lifecycle-событие уже accepted, отклоняется без
                --reopen-task <причина>; продолжение (последнее событие
                rejected/escalated) легально без флага; id, уже
                встречавшийся в журнале, тоже продолжается свободно —
                новая проверка бьёт только по СВЕЖИМ task_id формата
                t-NNN. Гард BEST-EFFORT: read-then-append без
                файлового лока — одновременная гонка двух процессов
                может проскочить (принято Lead 2026-07-09, t-009,
                вердикт critic F-A); ловит последовательный класс
                ошибок — реальную коллизию F-23 он бы заблокировал;
                residual-дубли обоих журналов ловит чек 13(д)
                еженедельной калибровки OS-репо)
orchestrator -> state/orchestrator-log.md (строка таблицы `| ts | ... |`,
                ровно 4 ячейки после времени; ts подставляется сам)
"""
from __future__ import annotations

import argparse
import json
import re
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

# D-0060/F-23 (OS-репо): две параллельные сессии выдали один task_id двум
# разным задачам. Порядок id обязателен только для НОВЫХ task_id, ФОРМАТ
# которых полностью (full-match, не substring) совпадает с последовательностью
# t-NNN — существующая в AO3 практика описательных id (at-bug-003,
# tc-034-review, fix-t-12-encoding...) продолжает работать как раньше (t-009,
# попытка 2: спека Lead первой попытки ошибочно требовала порядок для ЛЮБОГО
# нового id, включая описательные — исправлено; substring-совпадение вроде
# "t-12" внутри "fix-t-12-encoding" тоже не должно триггерить проверку
# последовательности, иначе описательный id с цифрами внутри ложно считается
# сорвавшим порядок).
TASK_ID_FULL_RE = re.compile(r"^t-(\d+)$")
SEQ_LIKE_RE = re.compile(r"^t-(\d+)$", re.IGNORECASE)


def _read_routing_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            records.append(json.loads(raw_line))
        except json.JSONDecodeError:
            continue
    return records


def _max_task_seq(records: list[dict]) -> int:
    max_n = 0
    for rec in records:
        tid = rec.get("task_id", "")
        if not tid:
            continue
        m = TASK_ID_FULL_RE.match(tid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n


def _expected_task_id(records: list[dict]) -> str:
    return f"t-{_max_task_seq(records) + 1:03d}"


def _last_lifecycle_event(records: list[dict], task_id: str) -> str | None:
    last: str | None = None
    for rec in records:
        if rec.get("task_id") == task_id:
            last = rec.get("event")
    return last


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
                   witness: str = "", ref: str = "",
                   reopen_task: str = "") -> str:
    task_id = task_id.strip()  # F-C: пробелы в id недопустимы
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
    if event == "delegated" and task_id:
        records = _read_routing_records(ROUTING_LOG)
        existing_ids = {r.get("task_id") for r in records if r.get("task_id")}
        if task_id not in existing_ids:
            # Порядок обязателен только для id, ПОЛНОСТЬЮ (full-match, не
            # substring) совпадающего с форматом последовательности t-NNN.
            # Описательный id (at-bug-005, fix-t-12-encoding...) новизна уже
            # гарантирована условием "не встречался" — последовательность к
            # нему не применяется (t-009, попытка 2: исправление п.1 спеки).
            if SEQ_LIKE_RE.match(task_id) and not TASK_ID_FULL_RE.match(task_id):
                raise SystemExit(
                    f"task_id '{task_id}' должен быть в канонической форме 't-NNN'")
            if TASK_ID_FULL_RE.match(task_id):
                expected = _expected_task_id(records)
                if task_id != expected:
                    raise SystemExit(
                        f"новый task_id '{task_id}' должен быть '{expected}' "
                        "(max(t-NNN существующих)+1, D-0060/F-23)")
        else:
            last_event = _last_lifecycle_event(records, task_id)
            if last_event == "accepted":
                if not reopen_task:
                    raise SystemExit(
                        f"task_id '{task_id}' уже закрыт (последнее событие "
                        "accepted); повторный delegated требует "
                        "--reopen-task <причина> (D-0060/F-23)")
                reopen_note = f"reopen: {reopen_task}"
                notes = f"{notes}; {reopen_note}" if notes else reopen_note
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
    p_rt.add_argument("--reopen-task", dest="reopen_task", default="",
                      metavar="ПРИЧИНА",
                      help="осознанный delegated поверх уже accepted "
                           "task_id (D-0060/F-23); причина уходит в notes")

    p_orch = sub.add_parser("orchestrator", help="строка в state/orchestrator-log.md")
    p_orch.add_argument("cells", nargs=4,
                        metavar=("ПРАВИЛО", "АГЕНТ", "АРТЕФАКТ", "ИСХОД"))

    args = parser.parse_args(argv)
    if args.target == "routing":
        line = append_routing(args.event, args.agent, model=args.model,
                              category=args.category, notes=args.notes,
                              task_id=args.task_id, attempt=args.attempt,
                              failure_class=args.failure_class,
                              witness=args.witness, ref=args.ref,
                              reopen_task=args.reopen_task)
    else:
        line = append_orchestrator(args.cells)
    # Запись в файл (_append_line, encoding="utf-8") уже совершена выше —
    # успех функции не должен зависеть от того, что происходит дальше.
    # Эхо строки на экран может упасть с UnicodeEncodeError, если кодовая
    # страница консоли (напр. cp1251) не может представить символ строки
    # (напр. "≠"); без этой правки такой сбой давал ложный exit 1, из-за
    # которого вызывающий может решить, что запись не прошла, и ретраить —
    # создавая дубли в журнале. Делаем stdout устойчивым к любым символам
    # заранее, а не глушим исключение вокруг print постфактум.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
