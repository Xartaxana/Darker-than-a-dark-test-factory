"""Каноничное добавление строк в журналы конвейера.

Несёт порт механизма D-0076 из эталонного репо
(Operating-System-for-LLMs), заведённого по инциденту F-44 ЭТОГО репо:
delegated (critic, e4-pipeline-wiring, 12:14:52) был записан в журнал,
но воркер фактически не был запущен — фантомная запись, необнаружимая
без явного скана открытых диспатчей. Сдан builder'ом соседним именем и
размещён Lead'ом при приёмке (D-0069; critic ACCEPT t-100 эталонного
журнала).

Добавление 1 — --worker-ref для routing (обязателен для event=delegated):
хэндл, по которому следующая сессия найдёт воркера/результат (id
фонового таска, job id, cli:<ISO для синхронного CLI-вызова>,
retro:<пометка для ретроактивной записи>); значение существует только
ПОСЛЕ фактического запуска воркера — сам факт заполнения поля не
доказывает, что воркер жив, но отсутствие поля гарантированно ловит
случай, когда строка написана ДО или ВМЕСТО запуска.

Добавление 2 — подкоманда `open-dispatches`: сканирует
logs/routing-log.jsonl и печатает task_id, чьё ПОСЛЕДНЕЕ по порядку
файла lifecycle-событие — delegated (т.е. задача открыта: делегирована,
но ещё не закрыта/не эскалирована/не признана decomposable).

Почему файловый порядок здесь безопасен (в отличие от эталонного
репо, где журнал пишет Edit-тул сессии и потребовался отдельный закон
"accepted закрывает" для устойчивости к ручной перестановке): в AO3
журнал ПО ПОЛИТИКЕ пишется только этим скриптом (append-only, ts
подставляется из системных часов в момент вызова _now_iso(); это
дисциплинарная, не физическая гарантия — bootstrap-строки до политики,
как journal_created, вне её, но и вне lifecycle-скана) — строки
не появляются не в хронологическом порядке. Поэтому
"последнее по порядку файла" эквивалентно "последнее по времени", и
закон открытости проще: reopen ЛЕГАЛЕН в AO3 (--reopen-task на
CLI-уровне уже существующего log_append.py), поэтому здесь НЕ
действует правило "accepted закрывает навсегда" из эталонного репо —
delegated ПОСЛЕ accepted (reopen) обязан вновь считаться открытым, и
эта функция это делает автоматически, просто беря последнее событие.

Добавление 3 (порт-батч штаба, эталон логики: tools/journal_validator.py
OS-репо, правило 9в2) — `--replaces-worker <прежний worker_ref>`: легальный
delegated поверх ОТКРЫТОГО task_id тем же agent'ом БЕЗ вердикта (замена
умершего воркера — не ретрай правила 6, поэтому легально без --attempt;
--attempt вместе с --replaces-worker — SystemExit, два основания не
смешиваются). Значение обязано буквально совпасть с worker_ref какой-то
предыдущей delegated-строки этого же task_id (любого agent) — иначе
SystemExit (защита от фиктивной замены). Маркер `replaces_worker:<хэндл>`
дописывается в notes, если его там ещё нет.

Добавление 4 (порт-батч штаба) — защита от «тихо-успешен вне среды»:
перед записью строки проверяется, что каталог журнала (logs/ для routing,
state/ для orchestrator) уже существует И это часть git-репозитория
(`_verify_environment`); вне ожидаемого деплоя — явный SystemExit, а не
тихое создание чужой структуры директорий.

Использование:
  python scripts/log_append.py routing --event delegated \
      --agent builder --model sonnet --task-id t-042 \
      --worker-ref "job:bg-4471" --category implementation --notes "..."
  python scripts/log_append.py routing --event delegated \
      --agent builder --model sonnet --task-id t-042 \
      --replaces-worker "job:bg-4471" --worker-ref "job:bg-9001" \
      --category implementation --notes "воркер завис, замена без вердикта"
  python scripts/log_append.py open-dispatches
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
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

# D-0076: события, из которых складывается lifecycle открытости task_id
# (пересечено с ROUTING_EVENTS ниже — если словарь событий когда-нибудь
# лишится одного из имён, скан не должен молча падать на несуществующем
# имени события).
_OPEN_DISPATCH_LIFECYCLE_CANDIDATES = {
    "delegated", "accepted", "rejected", "escalated", "decomposable",
}

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


def _prior_worker_refs(records: list[dict], task_id: str) -> set[str]:
    """Все worker_ref всех delegated (любого agent) этого task_id --
    правило replaces_worker ищет заявленный прежний хэндл именно здесь
    (эталон логики: tools/journal_validator.py OS-репо, task_worker_refs)."""
    return {r.get("worker_ref") for r in records
            if r.get("task_id") == task_id and r.get("event") == "delegated"
            and r.get("worker_ref")}


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


def _git_repo_present(start: Path) -> bool:
    """True, если `start` реально внутри git-репозитория: сперва
    однозначный git-плюмбинг-вызов (`git rev-parse
    --is-inside-work-tree`, cwd=start); git недоступен/бинарник не
    найден/это не репо -> фолбэк на присутствие каталога .git по
    цепочке родителей start (буквально то, что просит спека: "git
    rev-parse --is-inside-work-tree ИЛИ наличие .git по пути
    журнала")."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(start), capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip() == "true":
            return True
    except (FileNotFoundError, OSError):
        pass
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return True
    return False


def _verify_environment(*, require_dir: Path) -> tuple[bool, str]:
    """Защита от «тихо-успешен вне среды» (класс критик-находки штаба,
    D-0076-порт): строка уходит на диск, только если require_dir (родитель
    целевого файла журнала — logs/ для routing, state/ для orchestrator)
    УЖЕ существует (скрипт не создаёт директории в чужом/скопированном
    месте — раньше это молча делал path.parent.mkdir(parents=True) внутри
    _append_line) И это часть git-репозитория. Возвращает (ok, объяснение
    для SystemExit при ok=False); при ok=True объяснение пустое."""
    if not require_dir.exists():
        return False, (
            f"деплой не распознан: каталог '{require_dir}' не существует — "
            "log_append.py отказывается тихо создавать структуру директорий "
            "вне ожидаемого деплоя (защита «тихо-успешен вне среды»); "
            "если это новый деплой — создайте каталог сознательно и повторите"
        )
    if _git_repo_present(require_dir):
        return True, ""
    return False, (
        f"деплой не распознан: '{require_dir}' не внутри git-репозитория "
        "(git rev-parse --is-inside-work-tree не подтвердил, .git не найден "
        "по цепочке родителей) — отказ вместо тихой записи в чужом месте"
    )


def append_routing(event: str, agent: str, *, model: str = "",
                   category: str = "", notes: str = "", task_id: str = "",
                   attempt: int = 0, failure_class: str = "",
                   witness: str = "", ref: str = "",
                   reopen_task: str = "", by: str = "",
                   basis: str = "", worker_ref: str = "",
                   replaces_worker: str = "") -> str:
    task_id = task_id.strip()  # F-C: пробелы в id недопустимы
    worker_ref = worker_ref.strip()
    replaces_worker = replaces_worker.strip()
    if event not in ROUTING_EVENTS:
        raise SystemExit(f"неизвестное событие '{event}'; допустимы: "
                         + ", ".join(sorted(ROUTING_EVENTS)))
    if event in MODEL_REQUIRED_EVENTS and not model:
        raise SystemExit(f"--model обязательна для события '{event}' (CLAUDE.md, журнал маршрутизации)")
    if event in TASK_REQUIRED_EVENTS and not task_id:
        raise SystemExit(f"--task-id обязателен для события '{event}' (D-0053 OS-репо)")
    # D-0076 (порт OS-репо, инцидент F-44): delegated без worker_ref
    # неотличим от фантомной записи (строка есть, воркер не запущен).
    if event == "delegated" and not worker_ref:
        raise SystemExit(
            "--worker-ref обязателен для события 'delegated' (D-0076): "
            "хэндл, по которому следующая сессия найдёт воркера/результат "
            "(id фонового таска, job id, cli:<ISO>, retro:<...>)")
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
                # не accepted): continuation/retry/replaces_worker-ветки.
                prior_agents = _prior_delegated_agents(records, task_id)
                if agent not in prior_agents:
                    pass  # (б) continuation другим ярусом — легально
                else:
                    # replaces_worker (замена умершего воркера) — НЕ ретрай:
                    # взаимоисключающе с --attempt, чтобы не смешивать два
                    # разных легальных основания в одной строке (замена
                    # умершего воркера vs повтор после отклонения, правило 6).
                    if replaces_worker and attempt:
                        raise SystemExit(
                            "--replaces-worker и --attempt взаимоисключающие: "
                            "замена умершего воркера — не ретрай (правило 6 "
                            "требует attempt>=2 + rejected; --replaces-worker "
                            "легализует делегирование без вердикта)")
                    valid_attempt = attempt >= 2
                    if valid_attempt and _has_rejected(records, task_id):
                        pass  # (в) легальный ретрай после rejected
                    elif replaces_worker:
                        prior_refs = _prior_worker_refs(records, task_id)
                        if replaces_worker not in prior_refs:
                            raise SystemExit(
                                f"--replaces-worker={replaces_worker!r} не "
                                f"встречается ни в одном предыдущем delegated "
                                f"task_id={task_id!r} — фиктивная замена "
                                "запрещена (эталон: правило 9в2 "
                                "tools/journal_validator.py OS-репо)")
                        marker = f"replaces_worker:{replaces_worker}"
                        if marker not in notes:
                            notes = f"{notes}; {marker}" if notes else marker
                    else:
                        # (в) не выполнены условия ретрая, replaces_worker
                        # не задан -> (г) дубль-паттерн
                        raise SystemExit(
                            f"повторный delegated тем же agent={agent!r} по "
                            f"task_id={task_id!r} без --attempt >=2 и "
                            "существующего rejected по этому task_id — "
                            "запрещённый дубль-паттерн (класс t-029, D-0060); "
                            "легальная альтернатива — --replaces-worker "
                            "<прежний worker_ref> при замене умершего "
                            "воркера без вердикта")
    ok, env_msg = _verify_environment(require_dir=ROUTING_LOG.parent)
    if not ok:
        raise SystemExit(env_msg)
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
    if worker_ref:
        record["worker_ref"] = worker_ref
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
    ok, env_msg = _verify_environment(require_dir=ORCH_LOG.parent)
    if not ok:
        raise SystemExit(env_msg)
    _append_line(ORCH_LOG, line)
    return line


def find_open_dispatches(records: list[dict]) -> list[dict]:
    """D-0076: task_id ОТКРЫТ, если его последнее по порядку файла
    lifecycle-событие (пересечение _OPEN_DISPATCH_LIFECYCLE_CANDIDATES с
    фактическим ROUTING_EVENTS) — delegated. Файловый порядок легален
    здесь по построению (см. docstring модуля): журнал пишет только этот
    скрипт, ts — с системных часов на момент вызова, поэтому строки
    физически идут хронологически. Reopen (delegated поверх accepted,
    --reopen-task) должен вновь показывать task_id открытым — этого не
    нужно кодировать отдельно, последнее событие после reopen снова
    delegated. Возвращает записи (dict) открытых task_id, старейшие
    (по позиции их ПОСЛЕДНЕГО delegated в файле — события, оставившего
    задачу открытой; для reopen/retry-цепочек это не первый delegated
    задачи) первыми."""
    lifecycle = _OPEN_DISPATCH_LIFECYCLE_CANDIDATES & ROUTING_EVENTS
    last_by_task: dict[str, tuple[int, dict]] = {}
    for idx, rec in enumerate(records):
        task_id = rec.get("task_id")
        event = rec.get("event")
        if not task_id or event not in lifecycle:
            continue
        last_by_task[task_id] = (idx, rec)
    open_items = [(idx, rec) for idx, rec in last_by_task.values()
                  if rec.get("event") == "delegated"]
    open_items.sort(key=lambda pair: pair[0])
    return [rec for _, rec in open_items]


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
    p_rt.add_argument("--worker-ref", dest="worker_ref", default="",
                      help="D-0076: хэндл, по которому следующая сессия "
                           "найдёт воркера/результат (id фонового таска, "
                           "job id, cli:<ISO>, retro:<...>); значение "
                           "существует только после запуска; обязателен "
                           "для delegated")
    p_rt.add_argument("--replaces-worker", dest="replaces_worker", default="",
                      metavar="ПРЕЖНИЙ_WORKER_REF",
                      help="осознанный delegated поверх ОТКРЫТОГО task_id "
                           "тем же agent'ом без вердикта (замена умершего "
                           "воркера, не ретрай): легально без --attempt, "
                           "если значение буквально совпадает с worker_ref "
                           "какого-то предыдущего delegated этого task_id; "
                           "маркер replaces_worker:<...> уходит в notes")

    sub.add_parser(
        "open-dispatches",
        help="D-0076: список task_id, чьё последнее lifecycle-событие — "
             "delegated (фантомная/незакрытая работа)")

    p_orch = sub.add_parser("orchestrator", help="строка в state/orchestrator-log.md")
    p_orch.add_argument("cells", nargs=4,
                        metavar=("ПРАВИЛО", "АГЕНТ", "АРТЕФАКТ", "ИСХОД"))

    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    if args.target == "routing":
        line = append_routing(args.event, args.agent, model=args.model,
                              category=args.category, notes=args.notes,
                              task_id=args.task_id, attempt=args.attempt,
                              failure_class=args.failure_class,
                              witness=args.witness, ref=args.ref,
                              reopen_task=args.reopen_task,
                              by=args.by, basis=args.basis,
                              worker_ref=args.worker_ref,
                              replaces_worker=args.replaces_worker)
        # Запись в файл (_append_line, encoding="utf-8") уже совершена выше —
        # успех функции не должен зависеть от того, что происходит дальше.
        # Эхо строки на экран может упасть с UnicodeEncodeError, если кодовая
        # страница консоли (напр. cp1251) не может представить символ строки
        # (напр. "≠"); без этой правки такой сбой давал ложный exit 1, из-за
        # которого вызывающий может решить, что запись не прошла, и ретраить —
        # создавая дубли в журнале. stdout уже сделан устойчивым к любым
        # символам заранее (выше), а не глушится исключение вокруг print
        # постфактум.
        print(line)
        return 0
    if args.target == "open-dispatches":
        records = _read_routing_records(ROUTING_LOG)
        for rec in find_open_dispatches(records):
            print(f"OPEN DISPATCH: {rec.get('task_id')} agent={rec.get('agent')} "
                  f"since {rec.get('ts')}")
        return 0
    line = append_orchestrator(args.cells)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
