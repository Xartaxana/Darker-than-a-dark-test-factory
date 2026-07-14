"""queue_snapshot — генерируемый статус фабрики: frontmatter → state/factory-status.md.

Находка ревью A4 (docs/08): ручные счётчики в HANDOFF расходятся с реальностью
(«41 Approved» при фактических 37). Правило G1: очередь и счётчики НЕ ведутся
руками — только этим скриптом из frontmatter артефактов. HANDOFF остаётся
resume-заметками и ссылается сюда.

Запускается верхним уровнем /qa-loop в конце прохода (перед коммитом борды)
и человеком в любой момент. Идемпотентен: одинаковое состояние → одинаковый файл
при фиксированном моменте генерации (от настенных часов зависят generated_at и
производные от него возрасты: *_freshness_hours, untriaged_failure_age).

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
AUTOMATION_ORDER = ["active", "quarantined", "needs_maintenance", "deprecated", "retired"]

# r10-release-readiness (docs/10 D2+P1): suites, для которых считаем свежесть
# последнего прогона. Только эти три названы спекой — "verification" (есть в
# schemas/run.schema.yaml) сюда не входит.
RELEASE_SUITES = ["smoke", "regression", "canary"]


def _parse_ts(value) -> "datetime.datetime | None":
    """ISO-строка -> aware datetime, либо None (тот же паттерн, что sla_sweep._parse_ts)."""
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


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
    automation: Counter = Counter()      # B3: lifecycle автотестов (не-active — сигнал)
    bug_status: Counter = Counter()
    bugs_open: list[str] = []
    known_issues: list[str] = []
    test_debt: list[str] = []            # B4: долг тестовой системы, отдельно от багов
    run_status: Counter = Counter()
    locks: list[str] = []
    total = Counter()

    # r10-release-readiness (docs/10 D2+P1): дополнительные срезы для секции
    # "Release readiness" — собираются в том же проходе по артефактам.
    runs_latest: dict[str, dict] = {}          # suite -> {id, status, updated, ts}
    untriaged: list[dict] = []                 # runs со status NeedsTriage: {id, ts}
    tc_priority_total: Counter = Counter()      # priority -> кол-во кейсов
    tc_priority_automated: Counter = Counter()  # priority -> кол-во Automated
    p0_uncovered: list[str] = []                # id P0-кейсов не в статусе Automated
    quarantine_ids: list[str] = []              # id кейсов с automation_status: quarantined
    blocker_critical_open: list[str] = []       # id app_bug, Open|Reopened, blocker|critical
    test_debt_open: list[str] = []              # id test_debt, Open|Reopened

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
            astatus = str(meta.get("automation_status") or "").strip()
            if astatus:
                automation[astatus] += 1
            if astatus == "quarantined":
                quarantine_ids.append(key)
            priority = str(meta.get("priority") or "").strip()
            if priority:
                tc_priority_total[priority] += 1
                if status == "Automated":
                    tc_priority_automated[priority] += 1
            if priority == "P0" and status != "Automated":
                p0_uncovered.append(key)
        elif itype == "bug":
            # B4: test_debt — не дефект приложения; своя секция, не пугает счётчики багов.
            if str(meta.get("type", "")).strip() == "test_debt":
                if status not in ("Verified", "Rejected"):
                    kind = str(meta.get("debt_kind") or "?").strip()
                    test_debt.append(
                        f"{key} [{kind}] {status} — {meta.get('title', '')}")
                    if status in ("Open", "Reopened"):
                        test_debt_open.append(key)
                continue
            bug_status[status] += 1
            if status in ("Open", "Reopened", "Blocked"):
                resolution = str(meta.get("resolution") or "").strip()
                tag = f" [{resolution}]" if resolution else ""
                bugs_open.append(
                    f"{key} [{meta.get('severity', '?')}] {status}{tag} — {meta.get('title', '')}")
            if status in ("Open", "Reopened") and \
                    str(meta.get("severity", "")).strip().lower() in ("blocker", "critical"):
                blocker_critical_open.append(key)
            # B2: known_issue — отдельная секция дайджеста, не теряется среди Open.
            if str(meta.get("known_issue") or "").strip().lower() == "true":
                known_issues.append(
                    f"{key} [{meta.get('severity', '?')}] {status} — {meta.get('title', '')}")
        elif itype == "run":
            run_status[status] += 1
            suite = str(meta.get("suite") or "").strip()
            updated_raw = str(meta.get("updated") or "").strip()
            ts = _parse_ts(updated_raw)
            if suite in RELEASE_SUITES:
                cur = runs_latest.get(suite)
                if cur is None or (ts is not None and (cur["ts"] is None or ts > cur["ts"])):
                    runs_latest[suite] = {"id": key, "status": status, "updated": updated_raw, "ts": ts}
            if status == "NeedsTriage":
                untriaged.append({"id": key, "updated": updated_raw, "ts": ts})

    return {"tc_status": tc_status, "tc_by_area": tc_by_area, "automation": automation,
            "bug_status": bug_status, "bugs_open": bugs_open, "known_issues": known_issues,
            "test_debt": test_debt, "run_status": run_status,
            "locks": locks, "total": total, "aut": _read_aut(),
            "escalations": _escalation_lines(),
            "runs_latest": runs_latest, "untriaged": untriaged,
            "tc_priority_total": tc_priority_total, "tc_priority_automated": tc_priority_automated,
            "p0_uncovered": p0_uncovered, "quarantine_ids": quarantine_ids,
            "blocker_critical_open": blocker_critical_open, "test_debt_open": test_debt_open}


def _fmt_counter(c: Counter, order: list[str]) -> str:
    parts = [f"{s}: **{c[s]}**" for s in order if c.get(s)]
    parts += [f"{s}: **{n}**" for s, n in sorted(c.items()) if s not in order]
    return " · ".join(parts) if parts else "—"


def _render_release_readiness(data: dict, generated_at: str) -> list[str]:
    """r10-release-readiness (docs/10 D2+P1). Все данные — из существующих
    артефактов; отсутствующий файл/поле рендерится явным «n/a», не падением."""
    aut = data["aut"]
    now_dt = _parse_ts(generated_at)
    lines = ["## Release readiness", ""]

    # 1. Сборка под тестом.
    if aut:
        commit = str(aut.get("source_commit") or "").strip()
        lines.append(
            f"- Сборка: {aut.get('version_name', 'n/a')} (versionCode {aut.get('version_code', 'n/a')}), "
            f"commit `{commit[:8] if commit else 'n/a'}`, built_at {aut.get('built_at', 'n/a')}")
    else:
        lines.append("- Сборка: n/a (state/app-under-test.yaml не найден)")

    # 2. Свежесть последнего прогона по каждому suite.
    for suite in RELEASE_SUITES:
        info = data["runs_latest"].get(suite)
        metric = f"{suite}_freshness_hours"
        if not info:
            lines.append(f"- {suite}: not_run")
            continue
        if info["ts"] is not None and now_dt is not None:
            age = f"{(now_dt - info['ts']).total_seconds() / 3600.0:.1f}"
        else:
            age = "n/a"
        lines.append(f"- {suite}: {info['status']} · {metric}: **{age}** ({info['id']})")

    # 3. Открытые blocker/critical (bugs прикладного типа).
    bc = data["blocker_critical_open"]
    lines.append(f"- Открытые blocker/critical: **{len(bc)}**" +
                 (f" — {', '.join(bc)}" if bc else ""))

    # 4. Known issues — только счёт (список уже есть в секции «Известные проблемы»).
    lines.append(f"- Известные проблемы (known_issue): **{len(data['known_issues'])}**")

    # 5. P0/P1 automation coverage.
    for pr in ("P0", "P1"):
        tot = data["tc_priority_total"].get(pr, 0)
        auto = data["tc_priority_automated"].get(pr, 0)
        pct = f"{round(auto / tot * 100)}%" if tot else "n/a"
        metric = f"{pr.lower()}_automation_coverage"
        lines.append(f"- {metric}: **{pct}** ({auto}/{tot})")
    if data["p0_uncovered"]:
        lines.append(f"  - непокрытые P0: {', '.join(data['p0_uncovered'])}")

    # 6. Test debt (открытый).
    td = data["test_debt_open"]
    lines.append(f"- Test debt открыт: **{len(td)}**" +
                 (f" — {', '.join(td)}" if td else ""))

    # 7. Карантин автотестов (test-case.automation_status: quarantined).
    qid = data["quarantine_ids"]
    lines.append(f"- Карантин автотестов: **{len(qid)}**" +
                 (f" — {', '.join(qid)}" if qid else ""))

    # 8. Untriaged — счёт + максимальный возраст (untriaged_failure_age).
    untriaged = data["untriaged"]
    ages = [(now_dt - u["ts"]).total_seconds() / 3600.0
            for u in untriaged if u["ts"] is not None and now_dt is not None]
    if not untriaged:
        max_age = "0"
    elif ages:
        max_age = f"{max(ages):.1f}"
    else:
        max_age = "n/a"
    lines.append(f"- Untriaged: **{len(untriaged)}** · untriaged_failure_age: **{max_age}**")

    lines.append("")
    return lines


def render(data: dict, generated_at: str) -> str:
    aut = data["aut"]
    lines = [
        "# Статус фабрики (генерируется, НЕ редактировать руками)",
        "",
        f"generated_at: {generated_at} · генератор: `scripts/queue_snapshot.py`",
        "Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). "
        "Ручные числа в HANDOFF/докках не имеют силы.",
        "",
    ]
    lines += _render_release_readiness(data, generated_at)
    lines += [
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
        f"- автотесты (B3): {_fmt_counter(data['automation'], AUTOMATION_ORDER)}",
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
        f"## Известные проблемы, known_issue ({len(data['known_issues'])})",
        "",
    ]
    lines += [f"- {b}" for b in data["known_issues"]] or ["- нет"]
    lines += [
        "",
        f"## Test debt ({len(data['test_debt'])})",
        "",
    ]
    lines += [f"- {b}" for b in data["test_debt"]] or ["- нет"]
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
