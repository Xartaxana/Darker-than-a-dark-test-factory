"""queue_snapshot — генерируемый статус фабрики: frontmatter → state/factory-status.md.

Находка ревью A4 (docs/08): ручные счётчики в HANDOFF расходятся с реальностью
(«41 Approved» при фактических 37). Правило G1: очередь и счётчики НЕ ведутся
руками — только этим скриптом из frontmatter артефактов. HANDOFF остаётся
resume-заметками и ссылается сюда.

Запускается верхним уровнем /qa-loop в конце прохода (перед коммитом борды)
и человеком в любой момент. Идемпотентен: одинаковое состояние → одинаковый файл
(меткой времени служит generated_at — единственная нестабильная строка).

Запуск: python scripts/queue_snapshot.py [--stdout]
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import board_sync as bs

REPO = bs.REPO
OUT_PATH = REPO / "state" / "factory-status.md"
AUT_PATH = REPO / "state" / "app-under-test.yaml"
ESCALATIONS_PATH = REPO / "state" / "escalations.md"

# Порядок вывода статусов (жизненный цикл, не алфавит)
TC_ORDER = ["Draft", "Review", "Approved", "Automated", "Blocked"]
BUG_ORDER = ["Open", "Reopened", "Fixed", "Verified", "Rejected", "Intended", "Blocked"]
RUN_ORDER = ["NeedsTriage", "Triaged", "Closed", "Blocked"]


def _read_aut() -> dict:
    if not AUT_PATH.exists():
        return {}
    text = AUT_PATH.read_text(encoding="utf-8", errors="replace")
    out = {}
    for f in ("version_name", "version_code", "source_commit", "built_at",
              "smoke_status", "regression_status"):
        m = re.search(rf'(?m)^{f}:\s*"?([^"\n#]*[^"\n# ])"?\s*(#.*)?$', text)
        if m:
            out[f] = m.group(1).strip()
    return out


def _escalation_lines() -> list[str]:
    if not ESCALATIONS_PATH.exists():
        return []
    return [l for l in ESCALATIONS_PATH.read_text(encoding="utf-8").splitlines()
            if l.startswith("- [")]


def collect() -> dict:
    tc_status: Counter = Counter()
    tc_by_area: dict[str, Counter] = defaultdict(Counter)
    bug_status: Counter = Counter()
    bugs_open: list[str] = []
    run_status: Counter = Counter()
    locks: list[str] = []
    total = Counter()

    for itype, meta, _body, src in bs._iter_artifacts():
        status = str(meta.get("status", "?"))
        key = str(meta.get("id"))
        total[itype] += 1
        lock = str(meta.get("lock") or "").strip()
        if lock:
            locks.append(f"{key} — `{lock}`")
        if itype == "test-case":
            tc_status[status] += 1
            area = src.parent.name if src.parent.name != "test-cases" else "—"
            tc_by_area[area][status] += 1
        elif itype == "bug":
            bug_status[status] += 1
            if status in ("Open", "Reopened", "Blocked"):
                bugs_open.append(
                    f"{key} [{meta.get('severity', '?')}] {status} — {meta.get('title', '')}")
        elif itype == "run":
            run_status[status] += 1

    return {"tc_status": tc_status, "tc_by_area": tc_by_area, "bug_status": bug_status,
            "bugs_open": bugs_open, "run_status": run_status, "locks": locks,
            "total": total, "aut": _read_aut(), "escalations": _escalation_lines()}


def _fmt_counter(c: Counter, order: list[str]) -> str:
    parts = [f"{s}: **{c[s]}**" for s in order if c.get(s)]
    parts += [f"{s}: **{n}**" for s, n in sorted(c.items()) if s not in order]
    return " · ".join(parts) if parts else "—"


def render(data: dict, generated_at: str) -> str:
    aut = data["aut"]
    lines = [
        "# Статус фабрики (генерируется, НЕ редактировать руками)",
        "",
        f"generated_at: {generated_at} · генератор: `scripts/queue_snapshot.py`",
        "Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). "
        "Ручные числа в HANDOFF/докках не имеют силы.",
        "",
        "## Сборка под тестом",
        "",
        (f"- {aut.get('version_name', '?')} (versionCode {aut.get('version_code', '?')}), "
         f"commit `{str(aut.get('source_commit', ''))[:8]}`, built_at {aut.get('built_at', '?')}"
         if aut else "- state/app-under-test.yaml не найден"),
        f"- smoke: {aut.get('smoke_status', '?')} · regression: {aut.get('regression_status', '?')}",
        "",
        f"## Тест-кейсы ({sum(data['tc_status'].values())})",
        "",
        f"- {_fmt_counter(data['tc_status'], TC_ORDER)}",
        "",
        "| Область | " + " | ".join(TC_ORDER) + " |",
        "|---|" + "---|" * len(TC_ORDER),
    ]
    for area, c in sorted(data["tc_by_area"].items()):
        lines.append(f"| {area} | " + " | ".join(str(c.get(s, "")) for s in TC_ORDER) + " |")
    lines += [
        "",
        f"## Баги ({sum(data['bug_status'].values())})",
        "",
        f"- {_fmt_counter(data['bug_status'], BUG_ORDER)}",
    ]
    for b in data["bugs_open"]:
        lines.append(f"- {b}")
    lines += [
        "",
        f"## Прогоны ({sum(data['run_status'].values())})",
        "",
        f"- {_fmt_counter(data['run_status'], RUN_ORDER)}",
        "",
        f"## Активные локи ({len(data['locks'])})",
        "",
    ]
    lines += [f"- {l}" for l in data["locks"]] or ["- нет"]
    lines += [
        "",
        f"## Эскалации ({len(data['escalations'])})",
        "",
    ]
    lines += ([f"{l}" for l in data["escalations"]] or ["- нет"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Снимок очереди фабрики из frontmatter")
    parser.add_argument("--stdout", action="store_true", help="вывести в stdout, файл не писать")
    args = parser.parse_args(argv)

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = render(collect(), generated_at)
    if args.stdout:
        print(text)
        return 0
    OUT_PATH.write_text(text, encoding="utf-8")
    data = collect()
    print(f"queue_snapshot: {OUT_PATH.name} обновлён — "
          f"TC {sum(data['tc_status'].values())}, багов {sum(data['bug_status'].values())}, "
          f"прогонов {sum(data['run_status'].values())}, локов {len(data['locks'])}, "
          f"эскалаций {len(data['escalations'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
