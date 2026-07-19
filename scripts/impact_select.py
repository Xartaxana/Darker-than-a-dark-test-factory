"""impact_select — read-only выбор затронутых областей test-cases по git-диапазону
app-under-test/ (docs/09 Этап 4 п.5, D1). Шаг 1 из 2: карта impact + этот скрипт;
встраивание в rules.yaml/qa-loop (файл-отчёт для конвейера) — отдельный шаг.

Карта — state/impact-map.yaml (РУКОПИСНАЯ, единственный рукописный элемент; владеет
Lead). Семантика матчинга (в этом порядке): ignore → wide_impact → rules (первое
совпадение по порядку файла карты) → unknown. wide_impact ИЛИ unknown-исходник
(протухшая/неполная карта) => безопасный fallback FULL REGRESSION.

Диапазон коммитов:
- явно: --from <sha> --to <sha>;
- по умолчанию: из state/app-under-test.yaml — to = source_commit, from = родитель
  первого коммита из coalesced_commits (либо родитель самого source_commit, если
  coalesced_commits пуст/отсутствует — build_watch.py не пишет поле, если сборка
  собрала ровно один новый коммит, D11). Невосстановимый диапазон (нет source_commit,
  git не может разрешить ревизию — напр. shallow-клон без нужного родителя) —
  честный отказ (код 1) с подсказкой про --from/--to.

Только чтение: `git -C app-under-test diff --name-only`, `rev-parse` — НИКАКИХ
fetch/checkout/write. Ничего не пишет в state/ — только stdout (markdown);
файл-отчёт для конвейера появится на шаге встраивания.

Запуск: python scripts/impact_select.py [--from <sha> --to <sha>]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import yaml

import board_sync as bs

REPO = bs.REPO
APP = REPO / "app-under-test"
MAP_PATH = REPO / "state" / "impact-map.yaml"
AUT_PATH = REPO / "state" / "app-under-test.yaml"

SMOKE_AREA = "smoke"


def _run(args: list[str], *, cwd: Path | None = None, timeout: int = 60) -> tuple[int, str]:
    """Обёртка subprocess. Тесты НЕ мокают её: они гоняют настоящий git
    по синтетическому репозиторию в tmp_path (read-only diff/rev-parse
    безопасны; уточнение при приёмке — ревью N4)."""
    try:
        p = subprocess.run(args, cwd=cwd, timeout=timeout,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s: {' '.join(args)}"
    except OSError as e:
        return 127, str(e)


class RangeError(Exception):
    """Диапазон коммитов не восстановим — честный отказ с подсказкой про --from/--to."""


# --- Глоб-матчинг карты (fnmatch-подобный, с поддержкой "**") ---

def _glob_to_regex(pattern: str) -> re.Pattern:
    """Транслирует glob-паттерн карты в анкорённый regex.

    "**" — ноль и более сегментов пути (включая "/"); "*" — что угодно, кроме "/";
    "?" — один символ, кроме "/". Остальное экранируется буквально.
    """
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if pattern[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def load_map(path: Path = MAP_PATH) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ignore = [(pat, _glob_to_regex(pat)) for pat in (data.get("ignore") or [])]
    wide = [(pat, _glob_to_regex(pat)) for pat in (data.get("wide_impact") or [])]
    rules = []
    for r in (data.get("rules") or []):
        pat = r["path"]
        rules.append((pat, _glob_to_regex(pat), list(r.get("areas") or [])))
    return {"ignore": ignore, "wide": wide, "rules": rules}


def classify_file(path: str, cmap: dict) -> tuple[str, list[str], str]:
    """Возвращает (category, areas, matched_pattern).

    category: "ignore" | "wide" | "rule" | "unknown". Порядок — как в докстринге
    модуля: ignore первым, затем wide_impact, затем rules (первое совпадение по
    порядку карты — специфичные пути стоят раньше своих же глобов)."""
    for pat, rx in cmap["ignore"]:
        if rx.match(path):
            return "ignore", [], pat
    for pat, rx in cmap["wide"]:
        if rx.match(path):
            return "wide", [], pat
    for pat, rx, areas in cmap["rules"]:
        if rx.match(path):
            return "rule", areas, pat
    return "unknown", [], ""


# --- Диапазон по умолчанию из state/app-under-test.yaml ---

def default_range() -> tuple[str, str]:
    if not AUT_PATH.exists():
        raise RangeError(f"{AUT_PATH} не найден")
    aut = yaml.safe_load(AUT_PATH.read_text(encoding="utf-8")) or {}
    to = str(aut.get("source_commit") or "").strip()
    if not to:
        raise RangeError("state/app-under-test.yaml: source_commit пуст/отсутствует")
    coalesced = aut.get("coalesced_commits") or []
    if isinstance(coalesced, str):
        # на случай "[abc12345, def67890]" распаршенного как строка (не должно
        # случиться при валидном YAML, но не падаем молча)
        coalesced = [s.strip() for s in coalesced.strip("[]").split(",") if s.strip()]
    first_new = str(coalesced[0]).strip() if coalesced else to
    rc, out = _run(["git", "-C", str(APP), "rev-parse", f"{first_new}~1"])
    if rc != 0:
        raise RangeError(
            f"не удалось разрешить родителя {first_new[:8]}~1 в app-under-test "
            f"(shallow-клон без нужной истории?): {out.strip()[:300]}")
    frm = out.strip()
    return frm, to


def diff_files(frm: str, to: str) -> list[str]:
    if not (APP / ".git").exists():
        raise RangeError(f"{APP} не является git-репозиторием (не найден .git)")
    rc, out = _run(["git", "-C", str(APP), "diff", "--name-only", f"{frm}..{to}"])
    if rc != 0:
        raise RangeError(f"git diff {frm[:8]}..{to[:8]} не прошёл: {out.strip()[:300]}")
    return [l for l in out.splitlines() if l.strip()]


# --- Выборка TC по областям (frontmatter test-cases/, ридер board_sync._iter_artifacts) ---

def test_cases_by_area() -> dict[str, list[dict]]:
    by_area: dict[str, list[dict]] = {}
    for itype, meta, _body, src in bs._iter_artifacts():
        if itype != "test-case":
            continue
        area = src.parent.name if src.parent.name != "test-cases" else "—"
        by_area.setdefault(area, []).append(meta)
    return by_area


def select(frm: str, to: str, cmap: dict) -> dict:
    files = diff_files(frm, to)
    ignored: list[str] = []
    wide: list[str] = []
    unknown: list[str] = []
    matched: list[tuple[str, list[str], str]] = []  # (path, areas, pattern)
    areas: set[str] = set()

    for f in files:
        cat, file_areas, pat = classify_file(f, cmap)
        if cat == "ignore":
            ignored.append(f)
        elif cat == "wide":
            wide.append(f)
        elif cat == "rule":
            matched.append((f, file_areas, pat))
            areas.update(file_areas)
        else:
            unknown.append(f)

    full_regression = bool(wide) or bool(unknown)
    return {
        "files": files, "ignored": ignored, "wide": wide, "unknown": unknown,
        "matched": matched, "areas": sorted(areas), "full_regression": full_regression,
    }


def render(frm: str, to: str, result: dict) -> str:
    lines = [
        "# Impact selection",
        "",
        f"Диапазон: `{frm}`..`{to}` (app-under-test/)",
        f"Файлов изменено: **{len(result['files'])}**",
        "",
    ]

    lines += ["## ignore", ""]
    lines += [f"- {f}" for f in result["ignored"]] or ["- нет"]

    lines += ["", "## wide_impact", ""]
    lines += [f"- {f}" for f in result["wide"]] or ["- нет"]

    lines += ["", "## rules (области)", ""]
    if result["matched"]:
        for f, file_areas, pat in result["matched"]:
            lines.append(f"- {f} → {', '.join(file_areas)} (`{pat}`)")
    else:
        lines.append("- нет")

    lines += ["", "## unknown (вне карты)", ""]
    lines += [f"- {f}" for f in result["unknown"]] or ["- нет"]

    lines += ["", "## Решение", ""]
    if result["full_regression"]:
        reasons = []
        if result["wide"]:
            reasons.append(f"wide_impact: {', '.join(result['wide'])}")
        if result["unknown"]:
            reasons.append(
                f"unknown (карта протухла или неполна): {', '.join(result['unknown'])}")
        lines.append(f"**FULL REGRESSION** ({'; '.join(reasons)})")
    else:
        area_list = result["areas"] or []
        lines.append(
            "Затронутые области: " + (", ".join(area_list) if area_list else "нет (все файлы ignore)"))
        by_area = test_cases_by_area()
        for area in area_list:
            cases = by_area.get(area, [])
            lines.append("")
            lines.append(f"### {area}")
            if not cases:
                lines.append("- область без кейсов")
                continue
            for c in sorted(cases, key=lambda m: str(m.get("id"))):
                lines.append(
                    f"- {c.get('id')} [{c.get('priority')}, {c.get('status')}] "
                    f"automated_by: {c.get('automated_by') or '—'}")

    lines += ["", "## smoke (гоняется на любой сборке)", ""]
    smoke_cases = test_cases_by_area().get(SMOKE_AREA, [])
    if smoke_cases:
        for c in sorted(smoke_cases, key=lambda m: str(m.get("id"))):
            lines.append(
                f"- {c.get('id')} [{c.get('priority')}, {c.get('status')}] "
                f"automated_by: {c.get('automated_by') or '—'}")
    else:
        lines.append("- область без кейсов")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Impact selection: изменённые файлы app-under-test -> области test-cases (read-only, stdout)")
    parser.add_argument("--from", dest="frm", help="начало диапазона (git sha)")
    parser.add_argument("--to", dest="to", help="конец диапазона (git sha)")
    args = parser.parse_args(argv)

    if bool(args.frm) != bool(args.to):
        print("impact_select: --from и --to задаются вместе, либо оба опущены "
              "(тогда диапазон берётся из state/app-under-test.yaml)", file=sys.stderr)
        return 1

    try:
        if args.frm and args.to:
            frm, to = args.frm, args.to
        else:
            frm, to = default_range()
        cmap = load_map()
        result = select(frm, to, cmap)
    except RangeError as e:
        print(f"impact_select: диапазон не восстановим — {e}", file=sys.stderr)
        print("  подсказка: укажи явно --from <sha> --to <sha>", file=sys.stderr)
        return 1

    print(render(frm, to, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
