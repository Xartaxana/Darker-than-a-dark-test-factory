"""anchor_lint — минимальный линтер якорей `file:line` в тест-кейсах (WARN-ярус).

МОТИВ. Тест-кейсы (`test-cases/**/*.md`) ссылаются на код приложения точечными
якорями вида `` `BrowseSidePanel.kt:110` `` или `` `ao3_bridge.js:513` ``
(во фронтматтере поля `requirements`, в прозе, в таблицах). Код под якорем
двигается, якорь молчит — кейс продолжает указывать на строку, которая давно
стала другой функцией или вообще исчезла. Класс дефекта: «код под кейсом
сменился, кейс молчит».

ЧТО ЛОВИМ (и чего НЕ ловим). Линтер ловит ТОЛЬКО ГРУБЫЙ дрейф:
  - файл с таким именем нигде в корнях поиска не найден (переименован
    или удалён);
  - номер строки указывает ЗА пределы файла (файл укоротился).
Смысловой дрейф (строка существует, но там теперь другой код) НЕ ловится —
это осознанный минимум первой версии; сравнение содержимого строки с текстом
якоря — вне скоупа.

ФОРМАТ ЯКОРЯ. `<basename>.<kt|js|py|xml>:<N>` — имя файла БЕЗ пути (только
basename, `rglob` по корням поиска ищет совпадение по имени, путь в
тест-кейсе не хранится). Поддержаны:
  - диапазон `File.kt:110-120` — для проверки берётся первое число (110);
  - хвост через запятую `File.kt:100, 200` — трактуется как ДОПОЛНИТЕЛЬНЫЙ
    номер строки ТОГО ЖЕ файла (два независимых якоря на один basename).

СКОУП. Сканируются `test-cases/**/*.md` со статусом НЕ Merged/Deprecated
(`Merged` уже поглощён слиянием — дублирует dedup_check.py; `Deprecated`
кейс не развивается) — сам `scripts/` при этом на тест-кейсы НЕ сканируется.
Код ищется по ТРЁМ корням: app-under-test/ + framework/ + scripts/ (без
framework/.venv и framework/allure-*, чтобы не матчить site-packages/отчёты;
внутри scripts/ исключений нет — venv там не живёт, scripts/tests/ матчится
наравне с остальным) — класс дефекта «код под кейсом сменился, кейс молчит»
покрывает всю обвязку (тестовый фреймворк И скрипты конвейера), не только
код приложения (решение координатора).

ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ (решение Lead, эскалация
ANCHOR-LINT-SCOPE-AND-SEMANTIC-DRIFT-GAP, скоуп-часть, 2026-08-20).
Ровно ДВА носителя живых норм добавлены в скоуп сверх test-cases/:
`docs/01-test-strategy.md` (единственный живой стратегический документ,
на него ссылаются якорями типа `ao3_bridge.js:1155`) и
`exploratory-charters/*.md` (акты обследования с якорями на реальный код).
docs/ ЦЕЛИКОМ НЕ берётся — `docs/09-history.md` и другие исторические
архивы протухают ЛЕГИТИМНО (архив фиксирует, что было, а не что есть),
их включение обнулило бы детектор шумом собственных решений. У этих
источников нет статуса теркейса (`Merged`/`Deprecated`) — docs/01 вообще
без frontmatter `status`, у чартеров свой словарь жизненного цикла
(`Done`/…), не пересекающийся с test-case-терминальностью — оба
источника сканируются ЦЕЛИКОМ, без статусного фильтра.

Запуск: python scripts/anchor_lint.py [--strict] [--cases-dir DIR]
                                       [--app-dir DIR] [--framework-dir DIR]
                                       [--scripts-dir DIR]
                                       [--docs-strategy-file FILE]
                                       [--charters-dir DIR]
Коды выхода: 0 — ВСЕГДА (WARN-ярус); 1 — есть битые якоря И задан --strict
(флаг реализован, но НИГДЕ не включён — продвижение WARN -> ERROR идёт по
evidence, D-0063, не ради симметрии).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parent.parent
CASES_DIR = REPO / "test-cases"
APP_DIR = REPO / "app-under-test"
FRAMEWORK_DIR = REPO / "framework"
SCRIPTS_DIR = REPO / "scripts"
# Ровно два носителя живых норм сверх test-cases/ — решение Lead, докстринг
# модуля «ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ». НЕ вся docs/ — исторические архивы
# (docs/09-history.md и т.п.) протухают легитимно.
DOCS_STRATEGY_FILE = REPO / "docs" / "01-test-strategy.md"
CHARTERS_DIR = REPO / "exploratory-charters"

# Каталоги, которые НЕ обходим внутри корней поиска — site-packages в .venv
# и allure-* (сгенерированные отчёты) дают чужие/дублирующие basename'ы, шум
# без сигнала.
EXCLUDED_DIR_NAMES = (".venv",)
EXCLUDED_DIR_PREFIXES = ("allure-",)


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES or
               any(part.startswith(pfx) for pfx in EXCLUDED_DIR_PREFIXES)
               for part in path.parts)

# Терминальные/нерелевантные статусы: `Merged` уже поглощён слиянием (тот же
# смысл, что SKIPPED_STATUSES в dedup_check.py), `Deprecated` не развивается.
SKIPPED_STATUSES = {"Merged", "Deprecated"}

ANCHOR_EXTENSIONS = ("kt", "js", "py", "xml")

# <basename>.<ext>:<N>[-M][, N2][, N3]...
ANCHOR_RE = re.compile(
    r"(?P<file>[A-Za-z_][A-Za-z0-9_]*\.(?:" + "|".join(ANCHOR_EXTENSIONS) + r"))"
    r":(?P<line>\d+)(?:-\d+)?"
    r"(?P<extra>(?:\s*,\s*\d+)*)"
)


def _frontmatter_value(text: str, field: str) -> str | None:
    m = re.search(rf"(?m)^{re.escape(field)}:\s*(.+)$", text)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def extract_anchors(text: str) -> list[tuple[str, int]]:
    """Все якоря `(file, line)` в тексте — фронтматтер и тело равноправны.

    Хвост через запятую разворачивается в отдельные якоря того же файла;
    диапазон `N-M` даёт один якорь по первому числу."""
    out: list[tuple[str, int]] = []
    for m in ANCHOR_RE.finditer(text or ""):
        fname = m.group("file")
        out.append((fname, int(m.group("line"))))
        for extra in re.findall(r"\d+", m.group("extra") or ""):
            out.append((fname, int(extra)))
    return out


def build_basename_index(roots: list[Path]) -> dict[str, list[Path]]:
    """basename -> список путей под КОРНЯМИ поиска (app-under-test/,
    framework/, scripts/) с таким именем. Каталоги из EXCLUDED_DIR_NAMES/
    EXCLUDED_DIR_PREFIXES (.venv, allure-*) не обходятся ни в одном корне."""
    index: dict[str, list[Path]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for ext in ANCHOR_EXTENSIONS:
            for path in root.rglob(f"*.{ext}"):
                if path.is_file() and not _is_excluded(path):
                    index.setdefault(path.name, []).append(path)
    return index


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def collect_cases(cases_dir: Path = CASES_DIR) -> list[dict]:
    """Тест-кейсы в нетерминальных статусах: id/status/анкоры/путь."""
    found: list[dict] = []
    if not cases_dir.is_dir():
        return found
    for path in sorted(cases_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        case_id = _frontmatter_value(text, "id")
        status = _frontmatter_value(text, "status")
        if not case_id:
            continue
        if status in SKIPPED_STATUSES:
            continue
        found.append({
            "id": case_id, "status": status or "?", "path": path,
            "anchors": extract_anchors(text),
        })
    return found


def collect_extra_sources(docs_strategy_file: Path = DOCS_STRATEGY_FILE,
                          charters_dir: Path = CHARTERS_DIR) -> list[dict]:
    """Живые нормы вне test-cases/: docs/01-test-strategy.md (один файл) +
    exploratory-charters/*.md (ВЕСЬ каталог, не рекурсивно — чартеры плоские).

    Никакой статусной фильтрации (см. докстринг модуля «ДОПОЛНИТЕЛЬНЫЕ
    ИСТОЧНИКИ») — оба источника сканируются целиком. `id` берётся из
    frontmatter, если есть (чартеры); иначе — имя файла (docs/01 без
    frontmatter `id`)."""
    found: list[dict] = []
    paths: list[Path] = []
    if docs_strategy_file.is_file():
        paths.append(docs_strategy_file)
    if charters_dir.is_dir():
        paths.extend(sorted(charters_dir.glob("*.md")))
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        case_id = _frontmatter_value(text, "id") or path.name
        found.append({"id": case_id, "status": "?", "path": path,
                      "anchors": extract_anchors(text)})
    return found


def check_anchor(fname: str, line: int,
                  index: dict[str, list[Path]],
                  _cache: dict[Path, int]) -> tuple[bool, str | None]:
    """(ok, причина) — причина None при ok=True."""
    candidates = index.get(fname) or []
    if not candidates:
        return False, "файл не найден"
    counts = []
    for p in candidates:
        if p not in _cache:
            _cache[p] = line_count(p)
        counts.append(_cache[p])
    best = max(counts)
    if line <= best:
        return True, None
    return False, f"строка {line} за концом файла (максимум {best})"


def run(cases_dir: Path = CASES_DIR, app_dir: Path = APP_DIR,
        framework_dir: Path = FRAMEWORK_DIR,
        scripts_dir: Path = SCRIPTS_DIR,
        docs_strategy_file: Path = DOCS_STRATEGY_FILE,
        charters_dir: Path = CHARTERS_DIR) -> tuple[list[dict], int]:
    """Возвращает (список_битых, всего_якорей).

    Каждый элемент битых: {case_id, path, file, line, reason}."""
    index = build_basename_index([app_dir, framework_dir, scripts_dir])
    line_cache: dict[Path, int] = {}
    broken: list[dict] = []
    total = 0
    all_sources = collect_cases(cases_dir) + \
        collect_extra_sources(docs_strategy_file, charters_dir)
    for case in all_sources:
        for fname, line in case["anchors"]:
            total += 1
            ok, reason = check_anchor(fname, line, index, line_cache)
            if not ok:
                broken.append({
                    "case_id": case["id"], "path": case["path"],
                    "file": fname, "line": line, "reason": reason,
                })
    return broken, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="anchor_lint — линтер якорей file:line в тест-кейсах (WARN)")
    parser.add_argument("--strict", action="store_true",
                        help="выходить с кодом 1 при битых якорях (НЕ включено "
                             "нигде — продвижение по evidence, D-0063)")
    parser.add_argument("--cases-dir", default=str(CASES_DIR))
    parser.add_argument("--app-dir", default=str(APP_DIR))
    parser.add_argument("--framework-dir", default=str(FRAMEWORK_DIR))
    parser.add_argument("--scripts-dir", default=str(SCRIPTS_DIR))
    parser.add_argument("--docs-strategy-file", default=str(DOCS_STRATEGY_FILE))
    parser.add_argument("--charters-dir", default=str(CHARTERS_DIR))
    args = parser.parse_args(argv)

    broken, total = run(Path(args.cases_dir), Path(args.app_dir),
                        Path(args.framework_dir), Path(args.scripts_dir),
                        Path(args.docs_strategy_file), Path(args.charters_dir))

    for item in broken:
        anchor = f"{item['file']}:{item['line']}"
        print(f"[WARN] {item['case_id']}: {anchor} — {item['reason']}")

    print(f"anchor_lint: якорей {total}, битых {len(broken)}")
    return 1 if (broken and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
