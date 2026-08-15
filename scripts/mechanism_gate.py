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

Изменение 2026-07-23 (разбор очереди Lead, «D:\\-якоря в облаке»;
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
аналог dispatch_skipped. Ожидаемое значение читается из roles.lead в
delegation.config.yaml (корень репо); файла/ключа нет, конфиг битый —
дефолт семейства "fable" (субскрипционный дефолт Lead, D-0072).

Lead-перепривязка (порт D-0099 OS-репо, 2026-08-15, слово оператора):
delegation.config.yaml — ЖИВОЙ конфиг этого репо (не гипотетический
"будущий пилот", как было записано раньше — history снята). Источник
текста для commit-msg-гейта — HEAD-версия файла (`git show
HEAD:delegation.config.yaml`, `_head_config_text()`), НЕ рабочее
дерево: коммит, ВВОДЯЩИЙ или МЕНЯЮЩИЙ конфиг same-commit, судится по
СТАРОЙ привязке (класс snapshot_shrink_guard, второй экземпляр —
незакоммиченная/same-commit правка roles.lead планку не двигает).
`resolve_lead_binding(config_text)` — чистая функция (диска не
касается), извлекает ЯРУСНОЕ СЕМЕЙСТВО (fable/opus/sonnet/haiku) из
`roles.lead.subscription.model`, НЕ литеральный model-id (Р9 спеки
порта — резолвер возвращает семейство, отдельной ветки для точного
model-id сравнения нет и не заводится); fail-safe → "fable" + [WARN] в
stderr на КАЖДОЙ причине отката (нет текста, не парсится, roles.lead
отсутствует, model пуст, семейство не распознано, ≥2 разных семейства
в model, BOM-мусор, PyYAML недоступен). Санитарный пол: семейство
привязки НИЖЕ "opus" (по LEAD_FAMILIES: fable(0)<opus(1)<sonnet(2)<
haiku(3)) → тоже откат к "fable" + WARN — опечатка конфига
(`model: sonnet`) не снимает молча код-гейт калибровки №4. `import
yaml` — ЗАЩИЩЁННЫЙ, ВНУТРИ резолвера (Р3, порт B6 OS): гейт стоит в
commit-msg хуке, непойманный ImportError/трейсбек парсера уронил бы
ЛЮБОЙ коммит, не только механизменный.

Путь восстановления при БИТОМ конфиге (Р5): дефолт "fable" блокирует
Opus-Lead от механизменных коммитов (fable строго выше opus, tier-
декларация "opus" ниже привязки-по-умолчанию) — штатный выход: подъём
РЕЗЕРВА (Fable-сессия словом оператора, `tier: fable` СТРОГО ВЫШЕ
любой привязки по построению LEAD_FAMILIES), починка конфига тем же
Fable-коммитом.

Декларация принимается (1) точным совпадением с привязкой, (2)
вхождением её ярусного семейства (по подстроке) ИЛИ (3) семейством
СТРОГО ВЫШЕ привязки (fable при opus-привязке — резерв, D-0099).
Неоднозначная декларация — ≥2 РАЗНЫХ семейства в ОДНОЙ строке «tier:»
(напр. «sonnet (fallback от fable)») — отдельный отказ «декларация
неоднозначна» (Р4): молчаливое взятие первого совпадения запрещено.
Отсутствие строки tier и декларация ниже lead — РАЗНЫЕ тексты отказа,
оба несут инструкцию: Lead-класс работы в этом репо — в очередь Lead
явной строкой в docs/HANDOFF.md или журнале сессии (носитель очереди
пилота — HANDOFF, НЕ CURRENT_CONTEXT — это принадлежность OS-репо).
Skip-ветка («оси: не-механизм») и merge-коммиты строку tier не
требуют — тот же невод исключений, что и у осевого блока, С ОДНИМ
ИСКЛЮЧЕНИЕМ (Р12): если staged-пути коммита несут
delegation.config.yaml, skip-ветка НЕ применяется вовсе (ни к осевому
блоку, ни к tier-строке) — коммит, трогающий саму Lead-привязку,
теряет право на skip безусловно (`decide()` вызывается с
`honor_skip=not config_staged`).

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
# D-0099-порт (2026-08-15): Lead-привязка. CONFIG_PATH читает РАБОЧЕЕ
# ДЕРЕВО (пригодится, если когда-то понадобится вне commit-msg-контекста);
# commit-msg-гейт сам берёт HEAD-версию через _head_config_text() (Б5).
CONFIG_FILENAME = "delegation.config.yaml"
CONFIG_PATH = REPO_ROOT / CONFIG_FILENAME

MECHANISM_PREFIXES = (
    "CLAUDE.md",
    ".claude/agents/",
    ".claude/skills/",
    "schemas/",
    "state/rules.yaml",
    # D-0065 OS-репо: самозащита enforcement-цепочки
    "scripts/mechanism_gate.py",
    # 2026-07-31 (находка critic при ревью AT-BUG-033): журнальный гейт —
    # машинная проверка, меняющая обязанности будущих сессий (механизм по
    # D-0065), но невод его не ловил — три коммита log_append.py прошли
    # без осевого блока. Тесты scripts/tests/ намеренно НЕ в списке.
    "scripts/log_append.py",
    ".githooks/",
    # 2026-08-02 (закрытие хвоста HANDOFF «невод не покрывает
    # enforcement-скрипты», полный Lead): граница невода для scripts/ —
    # ГЕЙТЫ/ВАЛИДАТОРЫ, чей отказ или пропуск меняет, что обязано
    # случиться (стоят на пути исполнения прохода/коммита/сессии:
    # preflight, машина статусов, схемы выходов, хуки). Генераторы,
    # свиперы и локи (queue_snapshot, coverage_map, board_*, sla_sweep,
    # stale_locks, gitlab_sync, build_watch, loop_lock и пр.) — ВНЕ
    # невода: артефакты производят, обязанностей не меняют, их дефекты
    # трекаются багами конвейера (прецедент AT-BUG-038/040/041).
    "scripts/validate_frontmatter.py",
    "scripts/transitions.py",
    "scripts/arch_check.py",
    "scripts/agent_output.py",
    "scripts/evidence.py",
    "scripts/wiring_check.py",
    "scripts/hygiene_gate.py",
    "scripts/escape_check.py",
    "scripts/critic_verdict_check.py",
    "scripts/enforcement_probe.py",
    # 2026-08-09 (некрит-9, решение Lead, plan-m1-m4.md v3, M1+M4): обёртка
    # heartbeat.cmd решает, СОСТОИТСЯ ЛИ проход /qa-loop вовсе (программный
    # acquire/release локa, kill-tree по таймауту) — гейт-класс на пути
    # исполнения scheduled-запуска, не генератор/свипер.
    "scripts/heartbeat_wrap.py",
    # 2026-08-14 (spec-device-build-check.md v3, вердикт Q5): doctor —
    # preflight-гейт (SKILL qa-loop шаг 1), его код возврата меняет состав
    # правил прохода и пишет эскалации — тот же класс, что heartbeat_wrap.py
    # выше и log_append.py; сессия ниже Lead-привязки больше не добавит чек
    # в doctor без очереди Lead. Его тесты (scripts/tests/test_doctor.py) —
    # ВНЕ невода, тот же образец, что у heartbeat_wrap/log_append.
    "scripts/doctor.py",
    # 2026-07-23: срез карты осей — вход этого же гейта; тихая правка
    # среза = обход полноты осевого блока, поэтому сам срез механизмен.
    MAP_SNAPSHOT_REL,
    # D-0099-порт (2026-08-15): сама Lead-привязка — вход гейта (tier-
    # требование читает из неё ожидаемый ярус); тихая правка = обход
    # tier-требования, поэтому конфиг механизмен на общих основаниях.
    CONFIG_FILENAME,
)

LEAD_FAMILIES = ("fable", "opus", "sonnet", "haiku")

# Дефолт семейства "fable" (субскрипционный дефолт Lead, D-0072) —
# используется resolve_lead_binding() на КАЖДОЙ fail-safe ветке (нет
# конфига/файла/ключа, битый YAML, ≥2 семейства, семейство ниже opus,
# PyYAML недоступен и т.д.).
DEFAULT_LEAD_BINDING = "fable"

TIER_LINE_RE = re.compile(r"^\s*tier\s*:\s*(\S.*?)\s*$", re.IGNORECASE | re.MULTILINE)

AXIS_HEADING_RE = re.compile(r"^##\s+Ось\s+(\d+)", re.MULTILINE)
# Якорь строки (порт штабного фикса fadb7c0, OS-репо, полигон Dog D-0093,
# принят Lead 2026-07-28): без ^\s*/MULTILINE фраза матчила ИНЛАЙН-цитату
# синтаксиса отказа посреди прозы коммит-сообщения («строка "оси:
# не-механизм (...)" обходила бы гейт» — цитата сама содержала бы
# синтаксис отказа и глушила бы гейт целиком). Якорь симметричен уже
# заякоренному TIER_LINE_RE выше; строка, начинающаяся с кавычки/ёлочки
# перед маркером, не матчит — перед «оси» стоит непробельный символ.
SKIP_RE = re.compile(r"^\s*оси\s*:\s*не-механизм\s*\(", re.IGNORECASE | re.MULTILINE)


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
       сред без D:\\ (облако); факт использования main() печатает в
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


def _warn(msg: str) -> None:
    """Предупреждение в stderr — тихий откат привязки к дефолту не должен
    маскироваться под «матрица требует basis» или проходить незамеченным
    (Р6/Б1). Модуль уже реконфигурирует stdout/stderr в utf-8/replace на
    импорте (см. выше) — здесь достаточно голого print."""
    print(f"[WARN] mechanism_gate: {msg}", file=sys.stderr)


def _families_in(text: str) -> list[str]:
    """Все РАЗЛИЧНЫЕ ярусные семейства LEAD_FAMILIES, встреченные в
    `text` по подстроке (регистронезависимо), в порядке LEAD_FAMILIES
    (fable/opus/sonnet/haiku). Общий примитив для двух независимых
    проверок неоднозначности: model-строки конфига (resolve_lead_binding)
    и декларации «tier: <значение>» коммита (Р4, decide_full)."""
    low = text.lower()
    return [fam for fam in LEAD_FAMILIES if fam in low]


def resolve_lead_binding(config_text: str | None) -> str:
    """D-0099-порт (2026-08-15): ЧИСТАЯ функция (диска не касается, Б4) —
    ярусное СЕМЕЙСТВО (fable/opus/sonnet/haiku) Lead-привязки из
    `roles.lead.subscription.model` (или `.api.model`) в `config_text`
    (содержимое delegation.config.yaml; вызывающий сам решает, читать
    рабочее дерево или HEAD — см. _head_config_text()). Возвращает
    СЕМЕЙСТВО, не литеральный model-id (Р9: точного сравнения с model-id
    не существует и отдельная ветка для него не заводится — вся
    остальная логика модуля (lead_family/tier_declared_ok) уже работает
    с семействами).

    Fail-safe → "fable" + [WARN] в stderr на КАЖДОЙ из причин: конфига
    нет/пуст, YAML не парсится (в т.ч. любой иной сбой парсера — не
    только yaml.YAMLError, Р3), верхний уровень/roles/roles.lead — не
    словарь или отсутствует, model пуст/не строка, семейство модели не
    распознано, найдено ≥2 РАЗНЫХ семейства в model (неоднозначность —
    та же природа, что Р4 у деклараций коммита, но отдельная проверка:
    эта — над КОНФИГОМ, та — над СООБЩЕНИЕМ), PyYAML недоступен в этом
    интерпретаторе. `import yaml` — защищённый, ВНУТРИ этой функции
    (Р3, порт B6 OS-репо): гейт стоит в commit-msg хуке, непойманный
    ImportError/трейсбек парсера уронил бы ЛЮБОЙ коммит, не только
    механизменный — а сваленный интерпретатор без PyYAML не должен
    блокировать вообще все коммиты репозитория.

    Санитарный пол (Б1/2а): распознанное семейство НИЖЕ "opus" по
    LEAD_FAMILIES (т.е. sonnet/haiku) — тоже откат к "fable" + WARN
    «привязка ниже opus не поддерживается этим деплоем; правьте код
    осознанно» — опечатка конфига (`model: sonnet` вместо `claude-
    opus-5`) не должна молча снимать код-гейт калибровки №4 (haiku/
    sonnet-класс работы не координирует сам себя).

    Путь восстановления при БИТОМ конфиге (Р5, решение Lead): дефолт
    "fable" блокирует Opus-Lead от механизменных коммитов (fable строго
    выше opus в LEAD_FAMILIES, а не "boundary" привязки opus) — штатный
    выход: подъём РЕЗЕРВА (Fable-сессия словом оператора — резерв ВСЕГДА
    строго выше любой валидной привязки по построению индексов
    LEAD_FAMILIES), починка конфига тем же Fable-коммитом (`tier:
    fable`)."""
    if not config_text:
        return DEFAULT_LEAD_BINDING
    try:
        import yaml
    except ImportError:
        _warn("PyYAML недоступен в этом интерпретаторе — Lead-привязка "
              "не резолвится, дефолт \"fable\" (Р3)")
        return DEFAULT_LEAD_BINDING
    try:
        data = yaml.safe_load(config_text)
    except Exception as exc:  # любой сбой парсера, не только YAMLError (Р3)
        _warn(f"delegation.config.yaml не парсится как YAML ({exc}) — "
              "дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    if not isinstance(data, dict):
        _warn("delegation.config.yaml: верхний уровень — не словарь — "
              "дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    roles = data.get("roles")
    if not isinstance(roles, dict):
        _warn("delegation.config.yaml: roles отсутствует/не словарь — "
              "дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    lead = roles.get("lead")
    if not isinstance(lead, dict):
        _warn("delegation.config.yaml: roles.lead отсутствует/не словарь "
              "— дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    model = None
    sub = lead.get("subscription")
    if isinstance(sub, dict):
        model = sub.get("model")
    if not model:
        api = lead.get("api")
        if isinstance(api, dict):
            model = api.get("model")
    if not model or not isinstance(model, str) or not model.strip():
        _warn("delegation.config.yaml: roles.lead.subscription.model (или "
              ".api.model) пуст/отсутствует — дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    fams = _families_in(model)
    if not fams:
        _warn(f"delegation.config.yaml: model={model!r} — семейство не "
              "распознано (не fable/opus/sonnet/haiku) — дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    if len(fams) >= 2:
        _warn(f"delegation.config.yaml: model={model!r} — неоднозначность "
              f"(найдено {len(fams)} семейства: {fams}) — дефолт \"fable\"")
        return DEFAULT_LEAD_BINDING
    fam = fams[0]
    if LEAD_FAMILIES.index(fam) > LEAD_FAMILIES.index("opus"):
        _warn(f"delegation.config.yaml: привязка {fam!r} ниже opus не "
              "поддерживается этим деплоем; правьте код осознанно — "
              "дефолт \"fable\" (санитарный пол, калибровка №4)")
        return DEFAULT_LEAD_BINDING
    return fam


def _head_config_text() -> str | None:
    """HEAD-версия delegation.config.yaml (Б5): commit-msg-гейт судит
    коммит по привязке, ДЕЙСТВОВАВШЕЙ ДО этого коммита — незакоммиченная
    или SAME-COMMIT правка roles.lead планку не двигает (класс
    snapshot_shrink_guard, второй экземпляр). `_git()` глотает ошибки
    (capture_output) и возвращает "" и при отсутствии файла в HEAD, и
    при отсутствии HEAD вовсе (первый коммит репо) — оба случая
    неотличимы от пустого файла, что здесь не проблема: пустой текст
    тоже резолвится в "fable" через resolve_lead_binding(None) —
    корректный бутстрап (коммит, ВВОДЯЩИЙ конфиг, несёт `tier: fable`)."""
    out = _git("show", f"HEAD:{CONFIG_FILENAME}")
    return out if out else None


def lead_family(binding: str) -> str | None:
    """Ярусное семейство привязанной модели по подстроке (fable/opus/
    sonnet/haiku); None — семейство не распознано (не-Claude привязка),
    тогда годится только точное совпадение model id. Реализована через
    _families_in() — первое совпадение в порядке LEAD_FAMILIES, тот же
    порядок, что и раньше (безопасный рефакторинг, не меняет поведение
    для однозначных строк)."""
    fams = _families_in(binding)
    return fams[0] if fams else None


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
    """binding — уже РЕЗОЛВЛЕННОЕ семейство (resolve_lead_binding
    возвращает семейство, не литеральный model-id, Р9). Вызывающий
    (decide_full) обязан СНАЧАЛА исключить неоднозначность declared
    (см. _families_in/Р4) — здесь предполагается, что в declared
    распознаётся СТРОГО ОДНО семейство (или ни одного).

    Принимается: (1) точное совпадение с binding; (2) вхождение
    семейства binding подстрокой в declared (та же семантика, что
    раньше); (3) семейство declared СТРОГО ВЫШЕ binding по LEAD_FAMILIES
    (D-0099: полный Lead — это ЛЮБОЙ ярус не ниже привязки, не только
    буквальное имя "fable"; индекс меньше = сильнее, порядок
    fable(0)<opus(1)<sonnet(2)<haiku(3))."""
    if declared.strip() == binding:
        return True
    fam = lead_family(binding)
    if fam is None:
        return False
    if fam in declared.lower():
        return True
    declared_fam = lead_family(declared)
    if declared_fam is None:
        return False
    return LEAD_FAMILIES.index(declared_fam) < LEAD_FAMILIES.index(fam)


def _tier_queue_note() -> str:
    return ("механизменный коммит — Lead-tier работа: сессия на ярусе "
            "ниже привязки lead НЕ коммитит механизм сама, а кладёт его "
            "в очередь явной строкой в docs/HANDOFF.md или журнале "
            "сессии (носитель очереди в этом репо — HANDOFF, не "
            "CURRENT_CONTEXT); сессия lead-яруса добавляет строку "
            "«tier: <своя модель>» (D-0072).")


def decide(msg: str, staged: list[str], map_text: str | None,
           merging: bool = False, map_label: str = str(MAP_PATH),
           honor_skip: bool = True) -> tuple[int, str]:
    """Чистое решение гейта: блок и отказ — только из сообщения коммита.
    map_label — метка источника карты для текста отказа (main() передаёт
    итог resolve_map_source; дефолт сохраняет прежние вызовы/тесты).
    honor_skip (Р12, порт D-0099): decide_full() передаёт False, когда
    staged-пути коммита несут delegation.config.yaml — skip-строка
    «оси: не-механизм» не действует для коммита, трогающего саму
    Lead-привязку, осевой блок обязателен безусловно. Дефолт True
    сохраняет прежнее поведение для всех остальных вызовов/тестов."""
    hits = mechanism_paths(staged)
    if not hits:
        return 0, ""
    if merging:
        return 0, ""
    if honor_skip and SKIP_RE.search(msg):
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
                 merging: bool = False, map_label: str = str(MAP_PATH),
                 config_text: str | None = None) -> tuple[int, str]:
    """decide() плюс tier-требование (D-0072, t-071 порт): строка tier
    на ветке «механизм» (осевой блок уже пройден, не skip, не merge).
    Гейт проверяет только форму декларации — истинность судит калибровка
    (см. docstring модуля, D-0063).

    config_text (D-0099-порт, Б4 — инъекция для тестов): текст
    delegation.config.yaml, дефолт None ("конфига нет" — резолвится в
    "fable", регресс-пин с прежним поведением). main() передаёт
    HEAD-версию (_head_config_text()), не рабочее дерево (Б5).

    config_staged (Р12/М2.7): staged-пути несут delegation.config.yaml —
    skip-ветка не действует НИ для осевого блока (honor_skip=False
    передаётся в decide()), НИ для требования tier-строки ниже —
    коммит, трогающий саму Lead-привязку, теряет право на skip
    безусловно."""
    config_staged = CONFIG_FILENAME in staged
    code, reason = decide(msg, staged, map_text, merging, map_label,
                          honor_skip=not config_staged)
    if code:
        return code, reason
    hits = mechanism_paths(staged)
    skip_effective = SKIP_RE.search(msg) and not config_staged
    if not hits or merging or skip_effective:
        return 0, ""
    binding = resolve_lead_binding(config_text)
    declared_all = find_tier_declarations(msg)
    if not declared_all:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                    + "\nНет строки «tier: <значение>» (привязка lead: "
                    + binding + ") — " + _tier_queue_note())
    # Р4: неоднозначность (≥2 РАЗНЫХ семейства в ОДНОЙ tier-строке) —
    # отдельный отказ, проверяется ДО "below" (не первое-совпадение).
    ambiguous = [d for d in declared_all if len(_families_in(d)) >= 2]
    if ambiguous:
        return 1, ("коммит трогает механизмные файлы:\n  " + "\n  ".join(hits)
                    + "\nДекларация неоднозначна: «tier: " + ambiguous[0]
                    + "» несёт несколько ярусных семейств ("
                    + ", ".join(_families_in(ambiguous[0]))
                    + ") — укажи ровно одно (Р4) — " + _tier_queue_note())
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
    code, reason = decide_full(msg, staged, map_text, merging, map_label,
                               config_text=_head_config_text())
    if code:
        print("mechanism_gate: " + reason, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
