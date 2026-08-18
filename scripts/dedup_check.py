"""dedup_check — preflight-детектор ДУБЛИРУЮЩИХ тест-кейсов (WARN-ярус).

МОТИВ (слово оператора 2026-08-18). Механизм слияния (`spec-p1-dedup v7`,
статус `Merged` + `merged_into`) РЕТРОАКТИВЕН по построению: `rules.yaml`
вынесен в его явные non-goals, переход разрешён только human/lead. То есть
он умеет склеивать уже написанное и по конструкции НИЧЕГО не делает в момент
написания. Слово оператора: «сначала писать кучу кейсов, а потом их
дедуплицировать — плохой вариант; при написании мы уже должны не порождать
дублей».

ЧТО ЛОВИМ — замер, а не гипотеза. Механическая кластеризация всех 103
Approved-кейсов (Жаккар по токенам заголовка внутри области) дала плотный
кластер из ЧЕТЫРЁХ P1-кейсов:

    TC-197  visibility-скрытие есть, AO3-фильтр нет
    TC-199  фильтр есть, visibility нет
    TC-200  обе причины разом
    TC-201  ни одной

Это таблица истинности 2x2 по двум булевым флагам, выписанная четырьмя
отдельными кейсами, — то есть один параметризованный кейс, размноженный на
комбинации состояний. Соседи того же сорта: `Restore` x5 (backup), «ручной
синк» x4, `checkPageDensity` x3.

ПОЧЕМУ WARN, А НЕ ERROR (слово оператора). Признак «похожести» —
эвристика по заголовкам, а не доказательство дубля; порог подобран на одном
корпусе. Гейт, который блокирует легитимный кейс на непроверенной эвристике,
будет обойдён или выключен — и мы получим механизм-пожелание. Поэтому:
сначала WARN и накопление evidence, продвижение в ERROR — по замеру
(D-0063: продвижение в код-гейт по evidence, не ради симметрии). Режим
ERROR уже реализован флагом `--strict`, но в preflight НЕ включён.

ХРАПОВИК. На момент введения в корпусе уже лежат известные пары (их разбор —
отдельная работа Lead по spec-p1-dedup). Если печатать их каждый прогон,
сигнал утонет в шуме и гейт перестанут читать. Поэтому известные пары —
BASELINE: они считаются, но не кричат; кричат ТОЛЬКО НОВЫЕ. Это делает
детектор монотонным: корпус не может стать хуже незаметно.

Запуск: python scripts/dedup_check.py [--threshold 0.30] [--strict]
Коды выхода: 0 — нет НОВЫХ пар (WARN допустимы); 1 — есть новые И задан
--strict.
"""
from __future__ import annotations

import argparse
import re
import sys
from itertools import combinations
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

REPO = Path(__file__).resolve().parent.parent
CASES_DIR = REPO / "test-cases"

DEFAULT_THRESHOLD = 0.30
# Терминальные/нерелевантные статусы: `Merged` уже поглощён (проверять его на
# дубли — считать одно и то же дважды), `Blocked` не развивается.
SKIPPED_STATUSES = {"Merged", "Blocked"}

# Служебные слова, которые не несут предметной нагрузки и раздувают
# пересечение до ложных срабатываний.
STOPWORDS = set("""
и в во не на с со что а по к из у за от до для или же бы то как при над под
без есть нет только the a of to in on by with for is are and or not
кейс тест works work это того чтобы если когда после перед
""".split())

# BASELINE — пары, известные детектору. Считаются, но не кричат; кричат
# ТОЛЬКО новые. Удаление пары отсюда без разбора = молчаливое сокрытие.
#
# ВЕРДИКТ У КАЖДОЙ ПАРЫ (проход Lead 2026-08-19,
# docs/tasks/p1-dedup-lead-pass.md Р-4). Пара без вердикта — незакрытый
# вопрос; пара с вердиктом «не дубль» закрыта по СУЩЕСТВУ и снова
# «кандидатом» не считается. Восемь пар прохода 2026-08-18 из списка ушли:
# их кейсы слиты и из сравнения выбыли (Merged не сравнивается).
#
# Критерий разбора: дубль = ОДНА ЦЕЛЬ + ОДНА ПОВЕРХНОСТЬ + различие только в
# значении параметра. Различие поверхности (панель против оверлея, нативный
# экран против WebView, живой сайт против replay) дублем НЕ является —
# это независимые пути кода, и слияние прячет, ГДЕ сломалось.
VERDICT_NOT_DUP_CANARY = "не дубль: canary live/replay — цели противоположны"
VERDICT_NOT_DUP_GUARD = "не дубль: разные правила одного guard'а"
VERDICT_NOT_DUP_SURFACE = "не дубль: разные поверхности/подсистемы/события"
VERDICT_MERGE_DEFERRED = "кандидат: слияние отложено (цена > выгоды, после ESC-035)"

BASELINE: dict[frozenset, str] = {
    # canary: live против replay — детектор дрейфа сайта против нашей регрессии
    frozenset({"TC-066", "TC-067"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-068", "TC-069"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-070", "TC-071"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-070", "TC-074"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-070", "TC-075"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-070", "TC-076"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-071", "TC-074"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-071", "TC-075"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-071", "TC-077"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-072", "TC-073"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-074", "TC-075"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-074", "TC-076"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-075", "TC-077"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-076", "TC-077"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-078", "TC-079"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-078", "TC-080"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-078", "TC-081"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-079", "TC-080"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-079", "TC-081"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-080", "TC-081"}): VERDICT_NOT_DUP_CANARY,
    frozenset({"TC-082", "TC-083"}): VERDICT_NOT_DUP_CANARY,
    # guard тап-зон: четыре разных правила одного механизма
    frozenset({"TC-119", "TC-120"}): VERDICT_NOT_DUP_GUARD,
    frozenset({"TC-119", "TC-121"}): VERDICT_NOT_DUP_GUARD,
    frozenset({"TC-119", "TC-122"}): VERDICT_NOT_DUP_GUARD,
    # разные поверхности / подсистемы / события жизненного цикла
    frozenset({"TC-008", "TC-151"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-010", "TC-011"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-049", "TC-059"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-114", "TC-115"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-133", "TC-134"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-139", "TC-141"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-151", "TC-152"}): VERDICT_NOT_DUP_SURFACE,
    frozenset({"TC-207", "TC-212"}): VERDICT_NOT_DUP_SURFACE,
    # одна цель и одна поверхность — слияние обосновано, но отложено
    frozenset({"TC-030", "TC-063"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-116", "TC-117"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-126", "TC-127"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-138", "TC-140"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-138", "TC-142"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-138", "TC-143"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-140", "TC-142"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-140", "TC-143"}): VERDICT_MERGE_DEFERRED,
    frozenset({"TC-142", "TC-143"}): VERDICT_MERGE_DEFERRED,
}


# --- детектор 2: ВЛОЖЕННОСТЬ СЦЕНАРИЯ (слово оператора 2026-08-18) --------
# «Если один кейс повторяет шаги другого, но проходит на пару шагов дальше,
# то не надо писать новый — надо расширить старый: будет один кейс и
# несколько проверок».
# Это ДРУГОЙ класс, чем схожесть заголовков: тот ловит таблицу истинности
# (одна глубина, разные значения флагов), этот — приставку (одна и та же
# дорога, разная длина). Признак сильнее заголовочного, потому что смотрит
# на фактические шаги, а не на формулировку.
SCENARIO_HEADING_RE = re.compile(r"(?m)^##\s+Сценарий")
NEXT_HEADING_RE = re.compile(r"(?m)^##\s+")
STEP_MARKER_RE = re.compile(r"\*\*(Given|When|Then|And|But)\*\*", re.IGNORECASE)
# Минимальная длина общей приставки: 2 шага — это обычно только Given+When
# (общее предусловие), что само по себе дублем не является.
MIN_SHARED_STEPS = 3
STEP_MATCH_THRESHOLD = 0.75


def extract_steps(text: str) -> list[str]:
    """Нормализованные шаги секции «Сценарий (Given-When-Then)».

    Пустой список — валидный исход (у кейса нет секции либо она не размечена
    маркерами): такой кейс просто не участвует в детекте вложенности."""
    m = SCENARIO_HEADING_RE.search(text or "")
    if not m:
        return []
    rest = text[m.end():]
    nxt = NEXT_HEADING_RE.search(rest)
    body = rest[:nxt.start()] if nxt else rest

    steps: list[str] = []
    parts = STEP_MARKER_RE.split(body)
    # split даёт [до-первого-маркера, маркер, текст, маркер, текст, ...]
    for i in range(1, len(parts) - 1, 2):
        marker = parts[i].lower()
        chunk = re.sub(r"`[^`]*`", " ", parts[i + 1])        # код-ссылки — шум
        chunk = re.sub(r"\s+", " ", chunk).strip().lower()
        if chunk:
            steps.append(f"{marker}: {chunk}")
    return steps


def _steps_match(a: str, b: str) -> bool:
    """Шаги считаются одинаковыми при высокой лексической близости —
    точное равенство слишком хрупко к правкам формулировок."""
    if a == b:
        return True
    ta, tb = normalize_tokens(a), normalize_tokens(b)
    return jaccard(ta, tb) >= STEP_MATCH_THRESHOLD


def find_prefix_pairs(cases: list[dict],
                      min_shared: int = MIN_SHARED_STEPS) -> list[dict]:
    """Пары «короткий кейс — приставка длинного» внутри одной области.

    Возвращает dict с `short`/`long`: адресат правки — ДЛИННЫЙ кейс не
    заводится, а короткий расширяется."""
    by_area: dict[str, list[dict]] = {}
    for case in cases:
        if case.get("steps"):
            by_area.setdefault(case["area"], []).append(case)

    found: list[dict] = []
    for area, group in sorted(by_area.items()):
        for a, b in combinations(sorted(group, key=lambda c: c["id"]), 2):
            short, long_ = (a, b) if len(a["steps"]) <= len(b["steps"]) else (b, a)
            n = len(short["steps"])
            if n < min_shared or n == len(long_["steps"]):
                continue                      # приставка либо пустая, либо не короче
            if all(_steps_match(s, l) for s, l in zip(short["steps"], long_["steps"])):
                found.append({"area": area, "short": short, "long": long_,
                              "shared": n, "extra": len(long_["steps"]) - n,
                              "key": frozenset({short["id"], long_["id"]})})
    return sorted(found, key=lambda p: (-p["shared"], p["area"]))


def normalize_tokens(title: str) -> set[str]:
    """Токены заголовка без пунктуации, регистра и служебных слов."""
    text = (title or "").lower().replace("ё", "е")
    text = re.sub(r"[«»\"'`(),.:;—–\-/\\\[\]{}]", " ", text)
    return {w for w in text.split() if len(w) > 2 and w not in STOPWORDS}


def _frontmatter_value(text: str, field: str) -> str | None:
    m = re.search(rf"(?m)^{re.escape(field)}:\s*(.+)$", text)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def collect_cases(cases_dir: Path = CASES_DIR) -> list[dict]:
    """Все тест-кейсы в нетерминальных статусах: id/area/title/status."""
    found: list[dict] = []
    if not cases_dir.is_dir():
        return found
    for path in sorted(cases_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        case_id = _frontmatter_value(text, "id")
        title = _frontmatter_value(text, "title")
        status = _frontmatter_value(text, "status")
        if not case_id or not title:
            continue
        if status in SKIPPED_STATUSES:
            continue
        found.append({
            "id": case_id, "title": title, "status": status or "?",
            "area": path.parent.name, "path": path,
            "tokens": normalize_tokens(title),
            "steps": extract_steps(text),
        })
    return found


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def find_similar_pairs(cases: list[dict], threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    """Пары кейсов ОДНОЙ области со схожестью заголовков >= threshold.

    Сравнение ТОЛЬКО внутри области намеренно: одинаковые формулировки в
    разных областях (например «Restore …» в backup и sync) описывают разные
    механизмы, и межобластные пары давали бы шум без сигнала."""
    by_area: dict[str, list[dict]] = {}
    for case in cases:
        by_area.setdefault(case["area"], []).append(case)

    pairs: list[dict] = []
    for area, group in sorted(by_area.items()):
        for a, b in combinations(sorted(group, key=lambda c: c["id"]), 2):
            score = jaccard(a["tokens"], b["tokens"])
            if score >= threshold:
                pairs.append({"area": area, "a": a, "b": b, "score": score,
                              "key": frozenset({a["id"], b["id"]})})
    return sorted(pairs, key=lambda p: (-p["score"], p["area"]))


def run(cases_dir: Path = CASES_DIR, threshold: float = DEFAULT_THRESHOLD,
        baseline: set[frozenset] | None = None) -> tuple[list[dict], list[dict]]:
    """Возвращает (новые_пары, известные_пары) по ОБОИМ детекторам.

    Храповик общий: пара, известная по любому признаку, не кричит дважды."""
    baseline = BASELINE if baseline is None else baseline
    cases = collect_cases(cases_dir)
    pairs = find_similar_pairs(cases, threshold)
    prefix_pairs = find_prefix_pairs(cases)

    seen = {p["key"] for p in pairs}
    for p in prefix_pairs:
        p["kind"] = "prefix"
        if p["key"] not in seen:
            pairs.append(p)
            seen.add(p["key"])
    for p in pairs:
        p.setdefault("kind", "title")

    fresh = [p for p in pairs if p["key"] not in baseline]
    known = [p for p in pairs if p["key"] in baseline]
    return fresh, known


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="dedup_check — детектор дублирующих тест-кейсов (WARN)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"порог схожести заголовков (умолчание {DEFAULT_THRESHOLD})")
    parser.add_argument("--strict", action="store_true",
                        help="выходить с кодом 1 при НОВЫХ парах (ещё НЕ включено "
                             "в preflight — продвижение по evidence, D-0063)")
    parser.add_argument("--cases-dir", default=str(CASES_DIR))
    args = parser.parse_args(argv)

    fresh, known = run(Path(args.cases_dir), args.threshold)

    for pair in fresh:
        if pair.get("kind") == "prefix":
            print(f"  [WARN] НОВЫЙ кандидат в дубли (вложенность сценария, "
                  f"{pair['area']}): {pair['long']['id']} продолжает "
                  f"{pair['short']['id']}")
            print(f"         общих шагов: {pair['shared']}, сверх них у "
                  f"{pair['long']['id']}: {pair['extra']}")
            print(f"         {pair['short']['id']}: {pair['short']['title'][:100]}")
            print(f"         {pair['long']['id']}: {pair['long']['title'][:100]}")
            print(f"         Не заводи новый кейс — РАСШИРЬ {pair['short']['id']}: "
                  "один кейс, несколько проверок (слово оператора 2026-08-18).")
            continue
        print(f"  [WARN] НОВЫЙ кандидат в дубли ({pair['score']:.2f}, "
              f"{pair['area']}): {pair['a']['id']} <-> {pair['b']['id']}")
        print(f"         {pair['a']['id']}: {pair['a']['title'][:100]}")
        print(f"         {pair['b']['id']}: {pair['b']['title'][:100]}")
        print("         Если это варианты ОДНОГО механизма — параметризуй "
              "существующий кейс вместо нового (слово оператора 2026-08-18).")

    # Сводка по ВЕРДИКТАМ, а не по факту: разобранная пара («не дубль») и
    # незакрытый кандидат — разные вещи, и печатать их одним числом значит
    # потерять смысл прохода Lead 2026-08-19.
    by_verdict: dict[str, int] = {}
    for pair in known:
        verdict = BASELINE.get(pair["key"], "без вердикта") if isinstance(BASELINE, dict) \
            else "без вердикта"
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
    print(f"dedup_check: новых кандидатов: {len(fresh)}, известных: {len(known)}")
    for verdict, count in sorted(by_verdict.items()):
        print(f"    {count:>3} — {verdict}")
    return 1 if (fresh and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
