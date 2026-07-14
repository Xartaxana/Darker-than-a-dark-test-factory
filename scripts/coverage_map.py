"""coverage_map — генерируемая проекция полноты покрытия: frontmatter → state/coverage-map.md.

docs/09 Этап 4 п.12 / §5.2 внешнего ревью docs/10. Рукописной модели покрытия
НЕ существует и не заводится — этот файл ТОЛЬКО проекция из frontmatter
test-cases/ и runs/ (тот же принцип G1, что у queue_snapshot: числа не ведутся
руками). Риски R-01.. не хардкодятся здесь — читаются из таблицы §5
docs/01-test-strategy.md, иначе сам скрипт стал бы вторым источником истины.

Идемпотентен при фиксированном generated_at (единственная нестабильная строка).

Запуск: python scripts/coverage_map.py [--stdout]
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
OUT_PATH = REPO / "state" / "coverage-map.md"
RISK_DOC_PATH = REPO / "docs" / "01-test-strategy.md"

# Порядок из schemas/test-case.schema.yaml (enum priority/status) — не угадан.
PRIORITY_ORDER = ["P0", "P1", "P2", "P3"]
TC_STATUS_ORDER = ["Draft", "Review", "Approved", "Automated", "Blocked"]

_RISK_ID_RE = re.compile(r"(R-\d+)")
_RISK_ROW_RE = re.compile(r"^\|\s*(R-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")


def _load_risk_catalog() -> list[tuple[str, str, str]]:
    """(id, категория, описание) из таблицы §5 docs/01-test-strategy.md.

    Читаем таблицу динамически вместо хардкода списка R-01..R-NN в этом файле —
    иначе coverage_map.py сам стал бы вторым источником истины по рискам."""
    if not RISK_DOC_PATH.exists():
        return []
    text = RISK_DOC_PATH.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(?ms)^##\s*5\.[^\n]*\n(.*?)(?=\n##\s*6\.)", text)
    if not m:
        return []
    out: list[tuple[str, str, str]] = []
    for line in m.group(1).splitlines():
        rm = _RISK_ROW_RE.match(line)
        if rm:
            out.append((rm.group(1), rm.group(2).strip(), rm.group(3).strip()))
    return out


def _areas() -> list[str]:
    """Подпапки test-cases/ (= области), включая ПУСТЫЕ (без ни одного кейса)."""
    base = REPO / "test-cases"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def _is_green(run_meta: dict) -> bool:
    totals = run_meta.get("totals")
    if not isinstance(totals, dict):
        return False
    try:
        return int(totals.get("failed", 0)) == 0
    except (TypeError, ValueError):
        return False


def collect() -> dict:
    by_area: dict[str, list[dict]] = defaultdict(list)
    runs: list[dict] = []

    for itype, meta, _body, src in bs._iter_artifacts():
        if itype == "test-case":
            area = src.parent.name if src.parent.name != "test-cases" else "—"
            by_area[area].append(meta)
        elif itype == "run":
            runs.append(meta)

    for a in _areas():
        by_area.setdefault(a, [])

    green_runs = [r for r in runs if str(r.get("status")) == "Closed" and _is_green(r)]
    last_green_global = (
        max(green_runs, key=lambda r: str(r.get("updated") or "")) if green_runs else None
    )

    risk_catalog = _load_risk_catalog()
    risk_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for area, cases in by_area.items():
        for c in cases:
            # findall, не match: поле risk может нести несколько id
            # («R-04, R-06») — каждый входит в обратный индекс (ревью N2).
            for rid in _RISK_ID_RE.findall(str(c.get("risk") or "")):
                risk_index[rid].append((area, str(c.get("id"))))

    return {
        "by_area": dict(by_area),
        "risk_catalog": risk_catalog,
        "risk_index": dict(risk_index),
        "last_green_global": last_green_global,
        "has_runs": bool(runs),
    }


def _area_stats(cases: list[dict]) -> dict:
    total = len(cases)
    automated = sum(1 for c in cases if str(c.get("status")) == "Automated")
    if total == 0:
        coverage_status = None
    elif automated == 0:
        coverage_status = "none"
    elif automated == total:
        coverage_status = "designed-full"
    else:
        coverage_status = "partial"

    risks_raw = sorted({str(c.get("risk")).strip() for c in cases if str(c.get("risk") or "").strip()})
    no_risk_ids = sorted(str(c.get("id")) for c in cases if not str(c.get("risk") or "").strip())

    counts: Counter = Counter()
    for c in cases:
        pr = str(c.get("priority") or "?")
        st = str(c.get("status") or "?")
        counts[(pr, st)] += 1

    not_automated_hi = sorted(
        (str(c.get("id")), str(c.get("priority")), str(c.get("status")))
        for c in cases
        if str(c.get("priority")) in ("P0", "P1") and str(c.get("status")) != "Automated"
    )

    automated_by = sorted(
        str(c.get("automated_by")).strip()
        for c in cases
        if str(c.get("automated_by") or "").strip()
    )

    return {
        "total": total,
        "automated": automated,
        "coverage_status": coverage_status,
        "risks_raw": risks_raw,
        "no_risk_ids": no_risk_ids,
        "counts": counts,
        "not_automated_hi": not_automated_hi,
        "automated_by": automated_by,
    }


def _fmt_run(run_meta: dict | None) -> str:
    if not run_meta:
        return "нет зелёных прогонов"
    return (
        f"{run_meta.get('id')} (suite: {run_meta.get('suite', '?')}, "
        f"status: {run_meta.get('status', '?')}, updated: {run_meta.get('updated', '?')})"
    )


def render(data: dict, generated_at: str) -> str:
    by_area = data["by_area"]
    risk_catalog = data["risk_catalog"]
    risk_index = data["risk_index"]
    last_green_global = data["last_green_global"]

    stats_by_area = {area: _area_stats(cases) for area, cases in by_area.items()}

    lines = [
        "# Карта покрытия (генерируется, НЕ редактировать руками)",
        "",
        f"generated_at: {generated_at} · генератор: `scripts/coverage_map.py`",
        "Проекция из frontmatter test-cases/ и runs/ (принцип G1, как у "
        "`state/factory-status.md`). Рукописной модели покрытия не существует — "
        "этот файл не второй источник истины, а вывод.",
        "",
        "## Сводка по областям",
        "",
        "| Область | Кейсов | Automated | coverage_status |",
        "|---|---|---|---|",
    ]
    for area in sorted(by_area):
        st = stats_by_area[area]
        if st["total"] == 0:
            lines.append(f"| {area} | 0 | 0 | область без кейсов |")
        else:
            lines.append(f"| {area} | {st['total']} | {st['automated']} | {st['coverage_status']} |")

    lines += [
        "",
        "## Риски (docs/01-test-strategy.md §5) → покрытие",
        "",
        "| Риск | Категория | Покрывающие кейсы |",
        "|---|---|---|",
    ]
    if not risk_catalog:
        lines.append("| — | — | docs/01-test-strategy.md §5 не найден/не распознан |")
    for rid, cat, _desc in risk_catalog:
        covering = sorted(risk_index.get(rid, []))
        if covering:
            cell = ", ".join(f"{a}:{c}" for a, c in covering)
        else:
            cell = "риск не покрыт дизайном"
        lines.append(f"| {rid} | {cat} | {cell} |")

    lines += [
        "",
        "## Области",
        "",
    ]
    for area in sorted(by_area):
        st = stats_by_area[area]
        lines.append(f"### {area}")
        lines.append("")
        if st["total"] == 0:
            lines.append("Область без кейсов.")
            lines.append("")
            continue
        lines.append(f"- coverage_status: **{st['coverage_status']}** ({st['automated']}/{st['total']} Automated)")
        lines.append(
            "- риски: " + (", ".join(st["risks_raw"]) if st["risks_raw"] else "—")
        )
        lines.append(
            "- кейсы без risk: " + (", ".join(st["no_risk_ids"]) if st["no_risk_ids"] else "нет")
        )
        lines.append(
            "- P0/P1 не в Automated: "
            + (
                ", ".join(f"{cid} [{pr}, {stt}]" for cid, pr, stt in st["not_automated_hi"])
                if st["not_automated_hi"] else "нет"
            )
        )
        lines.append(
            "- автотесты (automated_by): "
            + (", ".join(st["automated_by"]) if st["automated_by"] else "—")
        )
        lines.append(
            "- last_green_run: " + _fmt_run(last_green_global)
            + " — деградировано до ГЛОБАЛЬНОГО прогона: схемы (test-case/run) не "
              "связывают run с конкретным TC ИЛИ с областью (нет поля "
              "run↔TC/area), см. отчёт builder'а"
        )
        lines.append("")
        lines.append("| Priority | " + " | ".join(TC_STATUS_ORDER) + " |")
        lines.append("|---|" + "---|" * len(TC_STATUS_ORDER))
        for pr in PRIORITY_ORDER:
            row = [str(st["counts"].get((pr, s), "") or "") for s in TC_STATUS_ORDER]
            lines.append(f"| {pr} | " + " | ".join(row) + " |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Карта покрытия test-cases/ из frontmatter")
    parser.add_argument("--stdout", action="store_true", help="вывести в stdout, файл не писать")
    args = parser.parse_args(argv)

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = collect()
    text = render(data, generated_at)
    if args.stdout:
        print(text)
        return 0
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"coverage_map: {OUT_PATH.name} обновлён — областей {len(data['by_area'])}, "
          f"рисков в §5 {len(data['risk_catalog'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
