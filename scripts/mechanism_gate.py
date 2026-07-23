"""Гейт правила 10(б) — D-0055 OS-репо + tier-декларация D-0072 (t-071).

ЖИВОЙ файл: .githooks/commit-msg вызывает его напрямую. (Историческая
заметка «НЕ живой файл» снята 2026-07-14: порт tier-требования из
tools/mechanism_gate.py OS-репо — decide_full/resolve_lead_binding/
lead_family/find_tier_declaration/tier_declared_ok, принят с critic-ревью
t-068 — сдавался соседним файлом по D-0069 и был установлен на этот путь
при приёмке; заметка о неактивности пережила установку — класс
«док лжёт о живости enforcement'а», сверено чтением .githooks/commit-msg.)

Унаследованное от твина: карта осей ОДНА и живёт в OS-репо, недоступна
→ fail-closed (F-7); решений (DECISIONS_FULL) в этом репо нет, поэтому
осевой блок и строка отказа «оси: не-механизм (<причина>)» ищутся
ТОЛЬКО в сообщении коммита (F-A); merge-коммиты пропускаются (F-C);
scripts/ вне триггера кроме самозащиты гейта и .githooks/ (D-0065
OS-репо, F-25).

Изменение 2026-07-23 (разбор очереди Lead, «D:\-якоря в облаке»;
критик-вход gate-map-anchor-0723, вердикт ДОРАБОТАТЬ исполнен):
ИСТОЧНИК текста карты разрешается цепочкой (см. resolve_map_source) —
env-override → живая карта по каноническому пути → закоммиченный срез
state/sibling-map.snapshot.md. Узкий fail-closed сохранён и усилен:
нет ни одного источника — отказ, как раньше; выставленный но
нечитаемый env-путь — тоже fail-closed БЕЗ тихого отката (явная
конфигурация не подменяется дефолтом молча). ЧЕСТНО ПРО ОСТАТКИ
срез-ветки (переформулировка по блокеру 1 вердикта — прежний claim
«не ослаблена ни в одной ветке» был переоценён):
(1) same-commit-ужатие: гейт читает срез из рабочего дерева, поэтому
    коммит, одновременно удаляющий ось из среза и трогающий механизм,
    прошёл бы без вердикта по удалённой оси (воспроизведено критиком:
    срез 9→8 + CLAUDE.md, вердикты 1-8 + tier → PASS). Закрыто КОДОМ:
    snapshot_shrink_guard() — ось, исчезающая из staged-среза
    относительно HEAD-среза, требует явной строки
    «ось N: удалена (<причина>)» в сообщении, иначе отказ.
(2) отставший срез: новая ось живой карты не потребуется в облаке,
    пока срез не обновлён. Кодом в облаке НЕ ловится (живая карта
    недостижима by definition) — детектор: кросс-репо сверка среза с
    живой картой на еженедельной калибровке OS; регистрация этого
    чека в OS-носителе — ОБЯЗАТЕЛЬНЫЙ кросс-репо handoff первой
    OS-достижимой сессии (правило 4б/F-48: пункт только в HANDOFF
    этого репо для OS-калибровки не существует); плюс stderr-строка
    на каждом механизменном коммите по срезу (видимость фолбэка) и
    анти-дрейф unit-тест (ловит ужатие ниже 9 — но только на прогоне
    тестов, не на хуке, и рост live не ловит).
Срез — под самозащитой гейта (MECHANISM_PREFIXES): его правка сама
требует осевой блок+tier.

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

import os
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
MAP_ENV_VAR = "AO3_SIBLING_MAP"
REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_SNAPSHOT_REL = "state/sibling-map.snapshot.md"
MAP_SNAPSHOT_PATH = REPO_ROOT / "state" / "sibling-map.snapshot.md"

MECHANISM_PREFIXES = (
    "CLAUDE.md",
    ".claude/agents/",
    ".claude/skills/",
    "schemas/",
    "state/rules.yaml",
    # D-0065 OS-репо: самозащита enforcement-цепочки
    "scripts/mechanism_gate.py",
    ".githooks/",
    # 2026-07-23: срез карты осей — вход этого же гейта; тихая правка
    # среза = обход полноты осевого блока, поэтому сам срез механизмен.
    MAP_SNAPSHOT_REL,
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


def _read_map(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def resolve_map_source() -> tuple[str | None, str, bool]:
    """Текст карты осей — тройная цепочка (2026-07-23; fail-closed D-0055
    сохранён, меняется только ИСТОЧНИК текста):

    1. env AO3_SIBLING_MAP — явное указание сессии (например, облачный
       клон OS-репо в нестандартном пути). Выставлен, но файл не
       читается → честный fail-closed БЕЗ тихого отката ниже по цепочке:
       явная конфигурация не подменяется дефолтом молча (класс F-30 —
       env-состояние не принимается на веру).
    2. Канонический Windows-путь живой карты — прежнее поведение,
       Windows-сессии не замечают изменения.
    3. Закоммиченный срез state/sibling-map.snapshot.md — фолбэк для
       сред без D:\ (облако); факт использования main() печатает в
       stderr (виден в выводе git commit); сверка среза с живой картой
       — чек еженедельной калибровки (детектор дрейфа).

    Возвращает (текст|None, метка источника для текста отказа,
    использован_ли_срез)."""
    env_raw = os.environ.get(MAP_ENV_VAR, "").strip()
    if env_raw:
        env_path = Path(env_raw)
        try:
            if env_path.is_file():
                return _read_map(env_path), f"env {MAP_ENV_VAR}={env_raw}", False
        except OSError:
            pass
        return None, f"env {MAP_ENV_VAR}={env_raw} — выставлен, но не читается (тихий откат к дефолтам запрещён)", False
    try:
        if MAP_PATH.exists():
            return _read_map(MAP_PATH), str(MAP_PATH), False
    except OSError:
        pass
    try:
        if MAP_SNAPSHOT_PATH.is_file():
            return _read_map(MAP_SNAPSHOT_PATH), f"срез {MAP_SNAPSHOT_REL}", True
    except OSError:
        pass
    return None, f"{MAP_PATH}; срез {MAP_SNAPSHOT_REL} тоже недоступен", False


def snapshot_shrink_guard(msg: str, head_axes: list[int],
                          staged_axes: list[int]) -> tuple[int, str]:
    """Q2-guard (блокер 1 вердикта critic gate-map-anchor-0723,
    обход воспроизведён): срез читается из рабочего дерева, поэтому
    same-commit-удаление оси из среза снимало бы требование вердикта по
    ней. Ось, исчезнувшая из staged-среза относительно HEAD-среза,
    легальна только с ЯВНОЙ строкой «ось N: удалена (<причина>)» в
    сообщении коммита — та же самодекларативная форма, что skip/tier;
    иначе fail-closed. Пустые head_axes (срез только создаётся) — не
    ужатие. Рост осей guard не трогает."""
    removed = [n for n in head_axes if n not in staged_axes]
    unjustified = [n for n in removed
                   if not re.search(rf"ось\s+{n}\s*:\s*удалена",
                                    msg, re.IGNORECASE)]
    if unjustified:
        return 1, ("срез карты осей ужат этим же коммитом: ось(и) "
                   + ", ".join(str(n) for n in unjustified)
                   + f" удалены из {MAP_SNAPSHOT_REL} без явной строки "
                   "«ось N: удалена (<причина>)» в сообщении — fail-closed "
                   "(same-commit-обход, вердикт critic gate-map-anchor-0723)")
    return 0, ""


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


def find_tier_declarations(msg: str) -> list[str]:
    """ВСЕ значения строк «tier: <значение>» — только из СООБЩЕНИЯ коммита
    (не из диффа), та же самодекларативная форма, что и skip-строка.

    Штабной фикс OS-репо 2026-07-22 (гейт-батч t-278, критик t-068),
    принят Lead'ом 2026-07-23: прежний `.search()` матчил только ПЕРВУЮ
    tier-строку — цитированная строка (например, высокий ярус в
    процитированном тексте) маскировала настоящую декларацию ниже по
    сообщению. Теперь `.findall()`: проходят только сообщения, где
    КАЖДАЯ найденная tier-строка не ниже привязки. Fail-closed на
    цитатах — осознанный трейдофф (цитируешь чужую tier-строку в
    механизменном коммите — перефразируй, чтобы она не парсилась)."""
    return [v.strip() for v in TIER_LINE_RE.findall(msg)]


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
           merging: bool = False, map_label: str = str(MAP_PATH)) -> tuple[int, str]:
    """Чистое решение гейта: блок и отказ — только из сообщения коммита.
    map_label — метка источника карты для текста отказа (main() передаёт
    итог resolve_map_source; дефолт сохраняет прежние вызовы/тесты)."""
    hits = mechanism_paths(staged)
    if not hits:
        return 0, ""
    if merging:
        return 0, ""
    if SKIP_RE.search(msg):
        return 0, ""
    if map_text is None:
        return 1, (f"карта осей не найдена ({map_label}) — fail-closed, "
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
                 merging: bool = False, map_label: str = str(MAP_PATH)) -> tuple[int, str]:
    """decide() плюс tier-требование (D-0072, t-071 порт): строка tier
    на ветке «механизм» (осевой блок уже пройден, не skip, не merge).
    Гейт проверяет только форму декларации — истинность судит калибровка
    (см. docstring модуля, D-0063)."""
    code, reason = decide(msg, staged, map_text, merging, map_label)
    if code:
        return code, reason
    hits = mechanism_paths(staged)
    if not hits or merging or SKIP_RE.search(msg):
        return 0, ""
    binding = resolve_lead_binding()
    declared_all = find_tier_declarations(msg)
    if not declared_all:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                    + "\nНет строки «tier: <значение>» (привязка lead: "
                    + binding + ") — " + _tier_queue_note())
    below = [d for d in declared_all if not tier_declared_ok(d, binding)]
    if below:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                    + "\nЯрус не lead: «tier: " + below[0]
                    + "» не совпадает с привязкой (" + binding + "); при "
                    "нескольких tier-строках отказ даёт ЛЮБАЯ ниже привязки "
                    "(fail-closed на цитатах, штабной фикс t-278) — "
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
    if MAP_SNAPSHOT_REL in staged and not merging:
        head_axes = parse_axes(_git("show", f"HEAD:{MAP_SNAPSHOT_REL}"))
        staged_axes = parse_axes(_git("show", f":{MAP_SNAPSHOT_REL}"))
        code, reason = snapshot_shrink_guard(msg, head_axes, staged_axes)
        if code:
            print("mechanism_gate: " + reason, file=sys.stderr)
            return code
    map_text, map_label, used_snapshot = resolve_map_source()
    if used_snapshot and mechanism_paths(staged) and not merging:
        # Видимость фолбэка в выводе КАЖДОГО механизменного коммита без
        # живой карты — вторая половина детектора дрейфа (первая — чек
        # калибровки: сверка среза с живой картой).
        print("mechanism_gate: живая карта осей недоступна — использован "
              f"закоммиченный срез {MAP_SNAPSHOT_REL}; сверка среза с "
              "живой картой — чек еженедельной калибровки", file=sys.stderr)
    code, reason = decide_full(msg, staged, map_text, merging, map_label)
    if code:
        print("mechanism_gate: " + reason, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
