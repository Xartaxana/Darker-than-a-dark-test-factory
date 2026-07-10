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
                еженедельной калибровки OS-репо;

                D-0058 (порт OS-репо, task_id journal-port-by-basis):
                --by <model> обязателен для accepted/rejected (самодекларация
                принимающего). Для accepted дополнительно матрица: легален,
                если tier(by) строго выше tier(agent) (haiku<sonnet<opus<fable;
                agent=scout/builder/critic -> tier статично, как в референсе;
                прочие агенты конвейера -> модель читается из frontmatter
                .claude/agents/<agent>.md; agent неизвестен нигде -> предупреждение
                в stderr, 'by' считается достаточным), либо задан --basis из
                {critic, queued-to-lead}; agent=lead -> матрица не применяется,
                'by' достаточно. rejected несёт 'by' без tier/basis-проверки
                (буквальное чтение спеки OS-репо);

                D-0060, ветки continuation/retry для delegated на СУЩЕСТВУЮЩИЙ
                (не описанный выше "новый") task_id, чья задача ОТКРЫТА
                (последнее событие по task_id — не accepted): agent новой
                строки отличается от agent ВСЕХ предыдущих delegated этого
                task_id -> легально без доп. флагов (continuation, напр.
                critic-вход); agent совпадает с одним из предыдущих -> легально
                ТОЛЬКО с --attempt >=2 И существующим выше rejected по этому
                task_id (ретрай); иначе — отказ (дубль-паттерн t-029). Задача
                ЗАКРЫТАЯ (есть accepted) — только --reopen-task, без изменений.
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

# D-0058 (порт OS-репо, task_id journal-port-by-basis): матрица приёмки.
# 'by' обязателен для accepted/rejected. Для accepted дополнительно легален
# только если tier(by) строго выше tier(agent), либо задан валидный 'basis'.
BY_REQUIRED_EVENTS = {"accepted", "rejected"}
TIER_ORDER = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
# Статично для канонических ярусов-функций (как в референсе OS-репо) —
# scout/builder/critic не читаются из frontmatter даже если файл существует.
AGENT_TIER = {"scout": "haiku", "builder": "sonnet", "critic": "opus"}
BASIS_VALUES = {"critic", "queued-to-lead"}
AGENTS_DIR = REPO / ".claude" / "agents"
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
FRONTMATTER_MODEL_RE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)


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


def _prior_delegated_agents(records: list[dict], task_id: str) -> set[str]:
    return {r.get("agent") for r in records
            if r.get("task_id") == task_id and r.get("event") == "delegated"
            and r.get("agent")}


def _has_rejected(records: list[dict], task_id: str) -> bool:
    return any(r.get("task_id") == task_id and r.get("event") == "rejected"
               for r in records)


def _read_agent_frontmatter_model(agent: str) -> str | None:
    """Читает поле 'model' из frontmatter .claude/agents/<agent>.md (read-only,
    файл не создаётся и не правится). None, если файла/поля нет."""
    path = AGENTS_DIR / f"{agent}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    model_m = FRONTMATTER_MODEL_RE.search(m.group(1))
    return model_m.group(1).strip() if model_m else None


def _warn_stderr(msg: str) -> None:
    """Печать предупреждения в stderr, устойчивая к узкой кодовой странице
    консоли (тот же класс риска, что и у финального print(line) в main() —
    UnicodeEncodeError на символе вне codepage не должен давать ложный сбой;
    см. комментарий в main())."""
    try:
        print(msg, file=sys.stderr)
    except UnicodeEncodeError:
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
        print(msg, file=sys.stderr)


def _resolve_agent_tier(agent: str) -> str | None:
    """Tier-имя исполнителя для матрицы D-0058, либо None, если матрица не
    применяется. agent='lead' -> матрица не применяется (по спеке, 'by'
    достаточно). Неизвестный агент (не в статическом списке и не читается из
    .claude/agents/*.md frontmatter) -> предупреждение в stderr и None —
    генератор не блокирует журналирование ещё не описанного будущего
    агента конвейера."""
    if agent == "lead":
        return None
    if agent in AGENT_TIER:
        return AGENT_TIER[agent]
    model = _read_agent_frontmatter_model(agent)
    if model in TIER_ORDER:
        return model
    _warn_stderr(
        f"log_append: WARNING — неизвестна модель агента '{agent}' (нет в "
        "статическом списке scout/builder/critic и не читается из "
        ".claude/agents/<agent>.md frontmatter); матрица D-0058 не "
        "проверяется для этой строки, 'by' считается достаточным"
    )
    return None


def _matrix_violation(agent: str, by: str, basis: str) -> str | None:
    """Правило D-0058 для accepted. Возвращает текст нарушения или None."""
    agent_tier = _resolve_agent_tier(agent)
    if agent_tier is None:
        return None
    by_tier = TIER_ORDER.get(by)
    ok_tier = by_tier is not None and by_tier > TIER_ORDER[agent_tier]
    ok_basis = basis in BASIS_VALUES
    if ok_tier or ok_basis:
        return None
    return (
        f"agent={agent!r} (tier={agent_tier}) принят by={by!r} — не строго "
        f"выше яруса исполнителя, и --basis не задан валидным значением "
        f"({sorted(BASIS_VALUES)})"
    )


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
                   reopen_task: str = "", by: str = "",
                   basis: str = "") -> str:
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
    by = by.strip()
    basis = basis.strip()
    if event in BY_REQUIRED_EVENTS:
        if not by:
            raise SystemExit(
                f"--by обязателен для события '{event}' (D-0058 OS-репо, "
                "самодекларация принимающего)")
        if event == "accepted":
            violation = _matrix_violation(agent, by, basis)
            if violation:
                raise SystemExit(f"accepted отклонён матрицей D-0058: {violation}")
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
            else:
                # D-0058 (порт OS-репо), задача ОТКРЫТА (последнее событие
                # не accepted): continuation/retry-ветки.
                prior_agents = _prior_delegated_agents(records, task_id)
                if agent not in prior_agents:
                    pass  # (б) continuation другим ярусом — легально
                else:
                    valid_attempt = attempt >= 2
                    if not (valid_attempt and _has_rejected(records, task_id)):
                        # (в) не выполнены условия ретрая -> (г) дубль-паттерн
                        raise SystemExit(
                            f"повторный delegated тем же agent={agent!r} по "
                            f"task_id={task_id!r} без --attempt >=2 и "
                            "существующего rejected по этому task_id — "
                            "запрещённый дубль-паттерн (класс t-029, D-0060)")
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
    if by:
        record["by"] = by
    if basis:
        record["basis"] = basis
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
    p_rt.add_argument("--by", default="",
                      help="модель принимающего (обязательна для accepted/"
                           "rejected, D-0058 OS-репо)")
    p_rt.add_argument("--basis", default="",
                      help="critic|queued-to-lead — обходит tier-матрицу "
                           "D-0058 для accepted")

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
                              reopen_task=args.reopen_task,
                              by=args.by, basis=args.basis)
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
