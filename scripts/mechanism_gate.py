"""Гейт правила 10(б) — D-0055 OS-репо + tier-декларация D-0072 (t-071).

ЖИВОЙ файл: .githooks/commit-msg вызывает его напрямую. (Историческая
заметка «НЕ живой файл» снята 2026-07-14: порт tier-требования из
tools/mechanism_gate.py OS-репо — decide_full/resolve_lead_binding/
lead_family/find_tier_declaration/tier_declared_ok, принят с critic-ревью
t-068 — сдавался соседним файлом по D-0069 и был установлен на этот путь
при приёмке; заметка о неактивности пережила установку — класс
«док лжёт о живости enforcement'а», сверено чтением .githooks/commit-msg.)

Унаследованное от твина (не менялось): карта осей ОДНА и живёт в
OS-репо, путь абсолютный, недоступна → fail-closed (F-7); решений
(DECISIONS_FULL) в этом репо нет, поэтому осевой блок и строка отказа
«оси: не-механизм (<причина>)» ищутся ТОЛЬКО в сообщении коммита (F-A);
merge-коммиты пропускаются (F-C); scripts/ вне триггера кроме
самозащиты гейта и .githooks/ (D-0065 OS-репо, F-25).

Новое — tier-требование (D-0072, порт правила 7 tools/mechanism_gate.py
OS-репо): на ветке «механизм» (осевой блок уже пройден, не skip, не
merge) сообщение коммита обязано нести ОТДЕЛЬНУЮ строку
«tier: <значение>» — самодекларация фактического яруса коммиттера,
аналог dispatch_skipped. В OS-репо ожидаемое значение читается из
roles.lead в delegation.config.yaml; в этом (AO3) репо такого конфига
нет и заводить сюда yaml-зависимость ради одного дефолта незачем —
resolve_lead_binding() ниже упрощена до константы: ожидаемая привязка
— дефолт семейства "fable" (субскрипционный дефолт Lead, тот же смысл,
что и дефолт OS-версии при отсутствующем/непарсящемся конфиге).
Функция оставлена (не заменена россыпью литералов), чтобы будущий
конфиг пилота подключился без правки вызывающего кода.

Декларация принимается точным совпадением с привязкой ИЛИ вхождением
её ярусного семейства (fable/opus/sonnet/haiku, по подстроке) — та же
семантика, что в OS-версии. Отсутствие строки tier и декларация ниже
lead — РАЗНЫЕ тексты отказа, оба несут инструкцию: Lead-класс работы
в этом репо — в очередь Lead явной строкой в docs/HANDOFF.md или
журнале сессии (носитель очереди пилота — HANDOFF, НЕ CURRENT_CONTEXT
— это принадлежность OS-репо). Skip-ветка («оси: не-механизм») и
merge-коммиты строку tier не требуют — тот же невод исключений, что и
у осевого блока.

Самодекларативность (D-0063, двухслойный enforcement): этот гейт
гарантирует только ФОРМУ — присутствие и совпадение строки tier с
ожидаемой привязкой; ИСТИННОСТЬ декларации (соврал ли коммиттер про
свой фактический ярус) код не проверяет и проверить не может — это
судит калибровка ярусом выше, по транскриптам (cc_usage), тем же
детектором, что D-0042/D-0056: чек 8 PROCESS/WEEKLY_CALIBRATION_PROTOCOL.md
(OS-репо) явно сверяет tier-строки механизменных коммитов периода с
фактической моделью сессии и относит расхождение к нарушению класса
F-36/F-29; та же чек-8 проверка заодно аудирует строки «оси:
не-механизм» как потенциальный обход tier-требования (переименование
механизменной правки в «не-механизм», чтобы не декларировать ярус).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Оба потока: тексты отказа гейта — кириллица и в stdout, и в stderr
# (эталон — ui_snapshot.py; класс доложен builder'ом e4-impact-selection).
# errors="replace" (докс/09 «Мелкое хозяйство» п.1, 2026-07-18): голый
# reconfigure(encoding="utf-8") оставлял errors="strict" — на редкой
# консоли, где повторная кодировка встречает суррогат, это всё ещё
# падение; replace не теряет диагностируемость (гейт и так печатает
# кириллицу, не бинарные данные), просто убирает последний шанс
# ValueError вместо тихой замены символа.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MAP_PATH = Path(r"D:\Improving_AI\Operating-System-for-LLMs\docs\SIBLING_MAP.md")

MECHANISM_PREFIXES = (
    "CLAUDE.md",
    ".claude/agents/",
    ".claude/skills/",
    "schemas/",
    "state/rules.yaml",
    # D-0065 OS-репо: самозащита enforcement-цепочки
    "scripts/mechanism_gate.py",
    ".githooks/",
)

LEAD_FAMILIES = ("fable", "opus", "sonnet", "haiku")

# AO3 пилот: нет delegation.config.yaml → дефолт семейства "fable"
# (субскрипционный дефолт Lead, D-0072). Константа вместо парсинга
# yaml — заводить сюда зависимость не от чего резолвить.
DEFAULT_LEAD_BINDING = "fable"

TIER_LINE_RE = re.compile(r"^\s*tier\s*:\s*(\S.*?)\s*$", re.IGNORECASE | re.MULTILINE)

AXIS_HEADING_RE = re.compile(r"^##\s+Ось\s+(\d+)", re.MULTILINE)
SKIP_RE = re.compile(r"оси\s*:\s*не-механизм\s*\(", re.IGNORECASE)


def parse_axes(map_text: str) -> list[int]:
    return [int(n) for n in AXIS_HEADING_RE.findall(map_text)]


def _matches(path: str, pref: str) -> bool:
    if pref.endswith("/"):
        return path.startswith(pref)
    return path == pref


def mechanism_paths(staged: list[str]) -> list[str]:
    return [p for p in staged
            if any(_matches(p, pref) for pref in MECHANISM_PREFIXES)]


def find_missing(text: str, axes: list[int]) -> list[int]:
    return [n for n in axes
            if not re.search(rf"ось\s+{n}\s*:", text, re.IGNORECASE)]


def resolve_lead_binding() -> str:
    """Ожидаемая tier-привязка для этого репо. AO3 не имеет
    delegation.config.yaml (в отличие от OS-репо) — возвращает дефолт
    семейства "fable" безусловно. Выделена в функцию, а не разбросана
    константой по вызывающему коду, чтобы будущий конфиг пилота
    подключился без правки decide_full()."""
    return DEFAULT_LEAD_BINDING


def lead_family(binding: str) -> str | None:
    """Ярусное семейство привязанной модели по подстроке (fable/opus/
    sonnet/haiku); None — семейство не распознано (не-Claude привязка),
    тогда годится только точное совпадение model id."""
    low = binding.lower()
    for fam in LEAD_FAMILIES:
        if fam in low:
            return fam
    return None


def find_tier_declaration(msg: str) -> str | None:
    """Значение строки «tier: <значение>» — только из СООБЩЕНИЯ коммита
    (не из диффа), та же самодекларативная форма, что и skip-строка."""
    m = TIER_LINE_RE.search(msg)
    return m.group(1).strip() if m else None


def tier_declared_ok(declared: str, binding: str) -> bool:
    if declared == binding:
        return True
    fam = lead_family(binding)
    if fam is None:
        return False
    return fam in declared.lower()


def _tier_queue_note() -> str:
    return ("механизменный коммит — Lead-tier работа: сессия на ярусе "
            "ниже привязки lead НЕ коммитит механизм сама, а кладёт его "
            "в очередь явной строкой в docs/HANDOFF.md или журнале "
            "сессии (носитель очереди в этом репо — HANDOFF, не "
            "CURRENT_CONTEXT); сессия lead-яруса добавляет строку "
            "«tier: <своя модель>» (D-0072).")


def decide(msg: str, staged: list[str], map_text: str | None,
           merging: bool = False) -> tuple[int, str]:
    """Чистое решение гейта: блок и отказ — только из сообщения коммита.
    Не изменена относительно живого scripts/mechanism_gate.py — этот
    порт трогает только tier-слой (decide_full ниже)."""
    hits = mechanism_paths(staged)
    if not hits:
        return 0, ""
    if merging:
        return 0, ""
    if SKIP_RE.search(msg):
        return 0, ""
    if map_text is None:
        return 1, (f"карта осей не найдена ({MAP_PATH}) — fail-closed, "
                   "коммит отклонён (D-0055 OS-репо)")
    axes = parse_axes(map_text)
    if not axes:
        return 1, ("в карте не найдено ни одной оси (## Ось N) — "
                   "fail-closed (D-0055 OS-репо)")
    missing = find_missing(msg, axes)
    if missing:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                   + "\nОсевой блок правила 10(б) неполон — нет вердикта по осям: "
                   + ", ".join(str(n) for n in missing)
                   + "\nДобавь в СООБЩЕНИЕ коммита «ось N: покрыта / в очередь / "
                   "н-п <почему>» на каждую ось карты либо явный отказ "
                   "«оси: не-механизм (<причина>)» (D-0055 OS-репо).")
    return 0, ""


def decide_full(msg: str, staged: list[str], map_text: str | None,
                 merging: bool = False) -> tuple[int, str]:
    """decide() плюс tier-требование (D-0072, t-071 порт): строка tier
    на ветке «механизм» (осевой блок уже пройден, не skip, не merge).
    Гейт проверяет только форму декларации — истинность судит калибровка
    (см. docstring модуля, D-0063)."""
    code, reason = decide(msg, staged, map_text, merging)
    if code:
        return code, reason
    hits = mechanism_paths(staged)
    if not hits or merging or SKIP_RE.search(msg):
        return 0, ""
    binding = resolve_lead_binding()
    declared = find_tier_declaration(msg)
    if declared is None:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                    + "\nНет строки «tier: <значение>» (привязка lead: "
                    + binding + ") — " + _tier_queue_note())
    if not tier_declared_ok(declared, binding):
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                    + "\nЯрус не lead: «tier: " + declared
                    + "» не совпадает с привязкой (" + binding + ") — "
                    + _tier_queue_note())
    return 0, ""


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout or ""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("mechanism_gate: нужен путь к файлу сообщения коммита", file=sys.stderr)
        return 1
    staged = _git("diff", "--cached", "--name-only").splitlines()
    merge_head = _git("rev-parse", "--git-path", "MERGE_HEAD").strip()
    merging = bool(merge_head) and Path(merge_head).exists()
    msg = Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    map_text = (MAP_PATH.read_text(encoding="utf-8", errors="replace")
                if MAP_PATH.exists() else None)
    code, reason = decide_full(msg, staged, map_text, merging)
    if code:
        print("mechanism_gate: " + reason, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
