"""dod_track.py (t-150, V3-Б) -- PostToolUse-хук Claude Code, копящий
трек правок и проверочных прогонов сессии/субагента, который читает
tools/dod_gate.py (SubagentStop-хук в этом же ките) для решения о
блокировке сдачи (D-0054/D-0052-механизация: "последняя правка РАНЬШЕ
последнего ЗЕЛЁНОГО проверочного прогона" -- детерминированный
инвариант, docs/tasks/2026-07-16_diet-b-design.md, «Кандидат v3-Б»).

===========================================================================
STAGING_HQ ВАРИАНТ (t-159, п.7 -- НЕ активирован, staging-копия для
ревью и постановки Lead'ом, D-0069). Отличия ОТ КИТА (exam_fullgates_kit/
tools/dod_track.py), явно, по пунктам:
 1. is_verification_command() НЕ применяет исключение "только
    самотесты гейтовой инфры" (kit-п.2а/_targets_only_gate_infra_tests
    ниже ОТСУТСТВУЕТ в этом файле совсем -- не просто выключена, а не
    перенесена). Причина: это исключение -- анти-геймификация ИМЕННО
    ЭКЗАМЕННОГО кита (билдер решает calculator/todo -- тесты гейтов
    ЗАВЕДОМО не его деливерабл, значит гонять их вместо своей задачи
    -- обход). В штабном деплое, КОГДА сессия реально РАЗРАБАТЫВАЕТ
    сами эти гейты (правка dispatch_gate.py/dod_gate.py и т.п.),
    `pytest tools/test_dispatch_gate.py` -- ЗАКОННЫЙ, единственно
    осмысленный прогон для ИМЕННО ЭТОЙ правки; кит-исключение сделало
    бы такой прогон невидимым гейту -- обратный эффект. Штабной
    канонический "python -m pytest tools/ gateway/ -q" и узкие
    таргеты (напр. "pytest tools/test_dispatch_gate.py -q") ОБА
    признаются verification-командой без исключений.
 2. build_fact() для edit-записей ДОПОЛНИТЕЛЬНО несёт "file_path"
    (из tool_input.file_path payload'а Edit/Write/MultiEdit/
    NotebookEdit) -- НОВОЕ поле, которого нет в kit-версии (там оно
    не требовалось). Нужно ТОЛЬКО штабным dod_gate.py/main_gate.py
    (staging_hq-варианты) для правила ".md/.json-only edits -- прогон
    не требуется" (см. их докстринги) -- без file_path эти гейты не
    могли бы определить расширение правленных файлов. tool_input для
    Edit/Write/MultiEdit/NotebookEdit несёт file_path ПОЛЕМ ВЕРХНЕГО
    УРОВНЯ (та же эмпирика метода, что и остальной контракт этого
    файла -- задокументированные схемы Zod в бандле для этих тулов
    единообразно называют путь именно "file_path"; отдельного живого
    смока под этот конкретный тул не делалось -- расширение по
    аналогии, не новая grep-вырезка, см. отчёт builder'а t-159).
===========================================================================

КОНТРАКТ PostToolUse -- ЭМПИРИКА, НЕ ПО ПАМЯТИ (спека t-150 требует
явно: "КОНТРАКТ payload'а PostToolUse сверь ЭМПИРИКОЙ смока, не по
памяти"). Метод и ОГРАНИЧЕНИЕ метода -- честно:
 - Источник: Zod-схемы события, извлечённые строковым grep'ом (не
   парсером/AST) из установленного бинарника Claude Code
   (`...\\npm\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe`).
   Контроль метода (F-30/F-34): позитивный (заведомо существующие
   имена полей схемы находятся) и негативный (заведомо
   несуществующая контрольная строка даёт 0 совпадений тем же
   grep'ом) прогнаны и подтвердили, что сам поиск работает, а не
   молчит "пусто" из-за промаха вызова.
 - НЕ выполнено: живой захват РЕАЛЬНОГО payload'а через настоящий
   PostToolUse-вызов под активным хуком (т.е. фактический перехват
   stdin в момент, когда харнесс реально шлёт событие). Это
   потребовало бы триггера через Task/Agent-тул (диспатч субагента)
   ИЛИ правки settings.json сессии, которой принадлежит этот
   процесс, -- оба пути вне роли builder на этой задаче (D-0037
   плоское делегирование запрещает первое; манифест t-150 запрещает
   второе -- owns ограничен exam_diet_policy_kit/**, штаб не
   трогать). Итог: контракт ниже -- ЛУЧШАЯ ДОСТУПНАЯ builder'у
   эмпирика (схема из бинарника, не из памяти/доков), но не
   100%-но живой захват; финальная сверка -- за Lead (см. отчёт).

Извлечённая схема (Zod, псевдоним в минифицированном бандле указан
для трассируемости, НЕ стабильный публичный API):
 - Базовые поля любого hook-события (функция n0() в бандле):
   session_id, transcript_path, cwd, prompt_id? (опц.), permission_mode?
   (опц.), agent_id? (опц. -- ИСПРАВЛЕНО t-159, см. ниже), agent_type?
   (опц.), effort? (опц., {level: str}). ПРЕЖНЯЯ версия этого докстринга
   (до t-159) перечисляла только session_id/transcript_path/cwd/
   prompt_id и ошибочно относила agent_id к SubagentStop-специфичной
   части -- находка t-159 (grep -a по тому же бинарнику, прямая
   выдержка .describe() из исходника): "agent_id:A.string().optional()
   .describe('Subagent identifier. Present only when the hook fires
   from within a subagent (e.g., a tool called by an AgentTool
   worker). Absent for the main thread, even in --agent sessions. Use
   this field (not agent_type) to distinguish subagent calls from
   main-thread calls.')" -- ЭТО ПОЛЕ БАЗОВОЕ, наследуется ЛЮБЫМ
   событием (включая PostToolUse), не только SubagentStop/SubagentStart.
   Используется build_fact() (_extract_agent_id) для различения
   main-thread/subagent записей -- см. правку t-159, очередь v5 п.1.
 - PostToolUse (схема NWb) добавляет: hook_event_name="PostToolUse",
   tool_name, tool_input, tool_response, tool_use_id, duration_ms?.
 - tool_response ДЛЯ Bash-тула конкретно (схемы Lkg/Pkg): {stdout:
   str, stderr: str, interrupted: bool, returnCodeInterpretation?:
   str, isImage?: bool, persistedOutputPath?: str,
   persistedOutputSize?: number}. Числового exit_code/rc-поля в ЭТОЙ
   схеме НЕТ (returnCodeInterpretation -- опциональная СТРОКА,
   заполняется только для "особых" ненулевых кодов, это не то же
   самое, что plain rc). Строка "exit_code" где-то в бинарнике
   действительно есть (21 совпадение строковым grep'ом), но
   строковый grep не даёт дерева разбора -- не подтверждено, что она
   принадлежит именно этой синхронной Bash-схеме (может быть полем
   другого тула/контекста, напр. фоновых команд). КОНСЕРВАТИВНОЕ
   допущение здесь: rc/exit_code СЧИТАЕТСЯ НЕДОСТУПНЫМ для Bash
   tool_response -- ветка спеки "rc==0, если rc доступен в payload"
   в этой среде практически НЕ применяется; исход определяется
   ТОЛЬКО текстовыми эвристиками по stdout+stderr (см.
   determine_outcome ниже). Функция всё же ПРОБУЕТ несколько
   правдоподобных числовых имён поля (rc/exit_code/returnCode) на
   случай, если живой смок Lead покажет иное, -- но в задокументированной
   выше схеме их нет, так что на практике эта ветка не сработает.

Хранилище: .claude/dod_track/<session_id>.json в cwd вызывающей
сессии (payload["cwd"] -- та же логика источника cwd, что в
tools/critic_gate.py, НЕ os.getcwd()). Формат файла (ПОЛЕ "agent_id"
добавлено t-159, очередь v5 п.1 -- см. build_fact/_extract_agent_id):
 {"edits": [{"ts": ISO, "tool_name": str, "agent_id": str|None}, ...],
  "runs":  [{"ts": ISO, "tool_name": str, "command": str,
             "outcome": "green"|"red", "agent_id": str|None}, ...],
  "gate_state": {...}}   -- поле "gate_state" пишет и читает
                             tools/dod_gate.py; этот файл его не
                             трогает, но и не стирает при
                             read-modify-write (сохраняет неизвестные
                             ключи как есть). "main_gate_state" --
                             аналогичное поле tools/main_gate.py
                             (СВОЙ, ОТДЕЛЬНЫЙ предохранитель-счётчик
                             от dod_gate.py -- один и тот же
                             session_id общий у main-хода и всех его
                             субагентов, общий счётчик дал бы ложную
                             интерференцию между Stop и SubagentStop
                             блокировками одной сессии).
   session_id ОБЩИЙ у главной сессии и ВСЕХ её субагентов (эмпирика
   t-159: конструктор события в бандле -- kf(e,void 0,i) -- всегда
   берёт session_id текущего процесса, agent_id -- отдельное поле,
   не отдельный session_id) -- значит БЕЗ "agent_id" в записи трек
   dod_track.py ДО t-159 неразличимо смешивал правки/прогоны
   main-хода и ЛЮБОГО параллельного/последовательного субагента в
   ОДНОМ файле. dod_gate.py (SubagentStop) читает ВСЕ записи, как
   раньше, -- НЕ фильтрует по agent_id (вне scope t-159, см. отчёт:
   находка-сиблинг, не фикс этим коммитом). tools/main_gate.py --
   новый читатель этого же файла t-159, фильтрует на agent_id is None
   (main-only).
ts -- локальное время без таймзоны, с системных часов в момент
обработки события хуком (F-29-конвенция), формат с микросекундами
(в отличие от logs/routing-log.jsonl) -- это внутренняя телеметрия
для dod_gate.py, не запись в маршрутизационный журнал, секундного
разрешения мало для надёжного сравнения "edit vs run" в пределах
одного инструментального хода.

ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ (не решено этим коммитом, задокументировано):
при ПАРАЛЛЕЛЬНЫХ tool-вызовах в одном ходе харнесс может запускать
несколько PostToolUse-процессов почти одновременно; read-modify-write
здесь БЕЗ блокировки файла -- гонка возможна (последний write
"выигрывает", может потерять факт от параллельного вызова). Спека
t-150 такого сценария не описывает; фиксируется как то же по духу,
что self-documented ограничение critic_gate.py (state на каталог,
не на процесс) -- не решается кодом.

Хук НИКОГДА не блокирует (только логирует) -- exit 0 всегда, кроме
нераспознаваемого/несвязанного входа, тоже exit 0 без побочных
эффектов (fail open, тот же принцип, что critic_gate.py).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

EDIT_TOOL_NAMES = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# "команда матчит pytest|python -m pytest|python .*test" -- буквально
# спека t-150, три альтернативы (первая уже покрывает вторую, но обе
# оставлены ради дословного соответствия тексту спеки).
VERIFICATION_COMMAND_RE = re.compile(
    r"pytest|python\s+-m\s+pytest|python\s+.*test", re.IGNORECASE
)

# STAGING_HQ: item-2а исключение "только самотесты гейтовой инфры"
# СОЗНАТЕЛЬНО НЕ ПЕРЕНЕСЕНО из kit-версии -- см. блок STAGING_HQ
# ВАРИАНТ в докстринге модуля выше за причину (в штабном деплое
# тесты гейтов МОГУТ быть законным деливераблом сессии).

# t-159 (очередь v5 п.2б): признать НЕ-pytest witness-формы --
# node-скрипт и UI-скриншот-прогон (прецедент №10б-t1: builder гонял
# НЕСВЯЗАННЫЙ pytest как обход, потому что его РЕАЛЬНЫЙ witness --
# node-скрипт/UI-прогон -- не распознавался VERIFICATION_COMMAND_RE и
# вообще не логировался в трек; DoD-гейт видел "нет зелёного прогона"
# при факте настоящей проверки).
#
# NODE_SCRIPT_RE: команда явно запускает .js/.mjs/.cjs-файл через
# node -- буквально спека т-159 ("node-скрипт (node .*\\.js)"),
# расширено на .mjs/.cjs (те же модули Node, тот же класс witness'а,
# не отдельная спека-ветка -- самостоятельное решение, задокументировано).
NODE_SCRIPT_RE = re.compile(r"\bnode\s+\S+\.(?:m?js|cjs)\b", re.IGNORECASE)

# UI_WITNESS_RE: спека т-159 явно оставляет выбор эвристики за
# builder'ом ("эвристика по команде -- задокументируй выбранную").
# ВЫБРАННАЯ эвристика: команда упоминает инструмент автоматизации
# браузера/захвата экрана (playwright/puppeteer/selenium/screencap)
# либо явное слово screenshot/скриншот -- это наиболее вероятные
# builder-обёртки для UI-witness прогона задачи с интерактивной
# поверхностью (CLAUDE.md кита правило 11: "witness включает ВОЖДЕНИЕ
# UI -- скриншот/запись до/после"). НЕ покрывает все мыслимые CLI --
# сознательный компромисс, не попытка угадать всё.
UI_WITNESS_RE = re.compile(
    r"screenshot|playwright|puppeteer|selenium|screencap|скриншот",
    re.IGNORECASE,
)

# "есть признаки прогона (passed|ok)" / "нет признаков провала
# (failed/error/Traceback)" -- буквально спека, case-insensitive
# (Traceback в реальном выводе Python пишется с большой буквы --
# без IGNORECASE эвристика никогда бы не сработала на настоящем
# трейсбеке). ОГРАНИЧЕНИЕ (t-159, задокументировано, не решено этим
# коммитом): determine_outcome() ниже применяется К ЛЮБОЙ распознанной
# verification-команде ОДИНАКОВО, включая node/UI-witness -- те же
# текстовые эвристики success/failure. Спека т-159 п.2б просит только
# ПРИЗНАТЬ форму командой (is_verification_command), не переопределяет
# determine_outcome отдельной веткой -- расширять эвристику outcome
# под node/UI вне объявленного scope этого пункта. ПОСЛЕДСТВИЕ: чисто
# побочный UI-скрипт БЕЗ текстового подтверждения (ни "passed"/"ok",
# ни "failed"/"error"/"traceback" в stdout/stderr -- например, скрипт,
# который молча сохраняет .png и завершается) по-прежнему попадёт в
# защитный дефолт "red" (см. determine_outcome) -- чтобы стабильно
# регистрироваться "green", witness-скрипт обязан печатать явное
# текстовое подтверждение (например "OK"/"passed"). Это РЕАЛЬНОЕ
# сужение пользы признания для молчаливых скриптов -- находка для
# отчёта, не блокер: recognized-но-red лучше, чем invisible (команда
# хотя бы попадает в трек как "run", а не пропадает вовсе, как было
# до этого пункта).
FAILURE_INDICATORS_RE = re.compile(r"failed|error|traceback", re.IGNORECASE)
SUCCESS_INDICATORS_RE = re.compile(r"passed|\bok\b", re.IGNORECASE)

NUMERIC_RC_FIELDS = ("rc", "exit_code", "returnCode", "return_code")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")


def is_edit_tool(tool_name) -> bool:
    return tool_name in EDIT_TOOL_NAMES


def is_verification_command(command: str) -> bool:
    command = command or ""
    if VERIFICATION_COMMAND_RE.search(command):
        # STAGING_HQ: без item-2а исключения -- ЛЮБОЙ pytest/python
        # test-таргет признаётся, включая самотесты гейтовой инфры.
        return True
    # t-159 п.2б: не-pytest witness-формы.
    if NODE_SCRIPT_RE.search(command):
        return True
    if UI_WITNESS_RE.search(command):
        return True
    return False


def _extract_rc(tool_response):
    """Пробует найти числовой код возврата в tool_response. По
    задокументированной эмпирике (докстринг модуля) для Bash-тула
    такого поля НЕТ -- эта функция почти всегда вернёт None в этой
    среде; оставлена на случай иной формы payload'а (не-Bash тул,
    либо живой смок Lead покажет обратное)."""
    if not isinstance(tool_response, dict):
        return None
    for key in NUMERIC_RC_FIELDS:
        value = tool_response.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return None


def _extract_text(tool_response) -> str:
    """Собирает текст для текстовых эвristик. Документированная форма
    Bash tool_response -- {"stdout": str, "stderr": str, ...}: обе
    части конкатенируются. Защитный фоллбек для иной формы (напр.
    {"type": "text", "text": ...} по примеру официальной страницы
    докво -- НЕ подтверждено эмпирикой, но безопасно попробовать) --
    если ни одно из ожидаемых полей не строка, сериализуем весь
    tool_response в JSON, чтобы регекспы всё равно имели, по чему
    искать."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        parts = []
        for key in ("stdout", "stderr", "text", "output"):
            value = tool_response.get(key)
            if isinstance(value, str):
                parts.append(value)
        if parts:
            return "\n".join(parts)
        try:
            return json.dumps(tool_response, ensure_ascii=False)
        except Exception:
            return str(tool_response)
    return str(tool_response)


def determine_outcome(tool_response) -> str:
    """"green" | "red". Спека: успех если (нет признаков провала И
    есть признаки прогона) ЛИБО rc==0 если rc доступен. rc, когда
    доступен, РЕШАЕТ безусловно (rc==0 -> green, rc!=0 -> red) --
    иначе текстовые эвристики. Если ни признаков провала, ни
    признаков успеха нет (неоднозначный вывод, напр. "no tests
    collected") -- ЗАЩИТНЫЙ дефолт "red": спека определяет, что
    считается зелёным прогоном, не что считается провалом;
    неопознанный вывод не является подтверждённым зелёным прогоном,
    а весь смысл гейта -- не пропускать сдачу без ПОДТВЕРЖДЁННОГО
    зелёного. Это самостоятельное инженерное решение (спека явно не
    описывает эту ветку), задокументировано здесь, а не молча."""
    rc = _extract_rc(tool_response)
    if rc is not None:
        return "green" if rc == 0 else "red"

    text = _extract_text(tool_response)
    has_failure = bool(FAILURE_INDICATORS_RE.search(text))
    has_success = bool(SUCCESS_INDICATORS_RE.search(text))

    if has_failure:
        return "red"
    if has_success:
        return "green"
    return "red"


def _extract_agent_id(payload: dict):
    """t-159 (очередь v5 п.1): различает main-thread от subagent-события
    БЕЗ строкового grep'а по памяти -- ПРЯМАЯ выдержка из Zod-исходника
    базовой схемы хуков (n0(), см. докстринг модуля выше), найденная
    тем же методом (grep -a по бинарнику claude.exe), что дал схемы
    XWb/NWb: "agent_id:A.string().optional().describe('Subagent
    identifier. Present only when the hook fires from within a
    subagent (e.g., a tool called by an AgentTool worker). Absent for
    the main thread, even in --agent sessions. Use this field (not
    agent_type) to distinguish subagent calls from main-thread
    calls.')" -- дословная цитата официального .describe() из
    бандла, не домысел: agent_id ЕСТЬ в БАЗОВОЙ схеме (наследуется
    ЛЮБЫМ hook-событием через n0(), включая PostToolUse и Stop), а не
    только в SubagentStop-специфичной части, как предполагал
    докстринг этого файла до t-159 (см. правку списка базовых полей
    выше). Возвращает str (subagent) | None (main thread) -- пустая
    строка тоже трактуется как None (защита от вырожденного payload)."""
    value = payload.get("agent_id")
    return value if isinstance(value, str) and value else None


def build_fact(payload: dict):
    """Чистая логика: по payload события решает, какой факт
    зафиксировать. Возвращает ("edit", {...}) | ("run", {...}) | None
    (событие не относится к DoD-треку). Побочных эффектов нет --
    тестируется напрямую, без I/O (тот же стиль, что critic_gate.decide).

    t-159: каждая запись несёт "agent_id" (str | None) -- None значит
    main-thread (payload без agent_id -- см. _extract_agent_id).
    tools/main_gate.py (Stop-хук) фильтрует по этому полю на
    main-only записи; tools/dod_gate.py (SubagentStop-хук) читает ВСЕ
    записи как раньше -- добавление поля НЕ ломает его логику (только
    новый ключ в уже существующих dict'ах edits/runs, старые ts/
    tool_name/command/outcome не тронуты)."""
    tool_name = payload.get("tool_name")
    agent_id = _extract_agent_id(payload)

    if is_edit_tool(tool_name):
        tool_input = payload.get("tool_input") or {}
        file_path = tool_input.get("file_path")
        return "edit", {
            "ts": _now_iso(),
            "tool_name": tool_name,
            "agent_id": agent_id,
            "file_path": file_path if isinstance(file_path, str) else None,
        }

    # STAGING_HQ доп. 2026-07-16 (форензика первой живой сессии, класс
    # t-151 "enforcement тихо-успешен вне среды"): штабные Windows-
    # сессии гоняют команды PowerShell-тулом, kit-среда (CLI-песочницы
    # экзаменов) -- Bash-тулом. Без PowerShell здесь (и в matcher'е
    # settings.json) verification-прогоны штаба НЕВИДИМЫ треку: три
    # no-green-run блока main_gate при фактически зелёных прогонах,
    # runs=[] в живом треке. Kit-версию не трогать -- её среда Bash.
    if tool_name in ("Bash", "PowerShell"):
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or ""
        if is_verification_command(command):
            outcome = determine_outcome(payload.get("tool_response"))
            return "run", {
                "ts": _now_iso(),
                "tool_name": tool_name,
                "command": command,
                "outcome": outcome,
                "agent_id": agent_id,
            }
        return None

    return None


def _track_path(cwd: str, session_id: str) -> Path:
    return Path(cwd or ".") / ".claude" / "dod_track" / f"{session_id}.json"


def _load_track(path: Path) -> dict:
    if not path.exists():
        return {"edits": [], "runs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Повреждённый файл трека -- не роняем хук, начинаем с
        # чистого состояния (fail open); edits/runs теряются, но это
        # лучше, чем застрявший на всю сессию гейт из-за битого JSON.
        return {"edits": [], "runs": []}
    if not isinstance(data, dict):
        return {"edits": [], "runs": []}
    data.setdefault("edits", [])
    data.setdefault("runs", [])
    return data


def _save_track(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _reconfigure_stderr_utf8():
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    _reconfigure_stderr_utf8()

    # STAGING_HQ: та же байтовая stdin-правка, что t-159 п.3
    # (dispatch_gate.py) -- платформенная кодировка stdin на Windows
    # (cp1251, эмпирика в tools/dispatch_gate.py кита) искажает
    # кириллицу при sys.stdin.read(); применено ко ВСЕМ staging_hq
    # хукам единообразно, не только к тому, что спека называла явно.
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception:
        return 0

    fact = build_fact(payload)
    if fact is None:
        return 0

    session_id = payload.get("session_id")
    if not session_id:
        # Без session_id некуда писать трек (файл именован по
        # session_id) -- fail open, факт теряется, но хук не падает.
        return 0

    cwd = payload.get("cwd") or "."
    path = _track_path(cwd, session_id)
    data = _load_track(path)

    kind, entry = fact
    data.setdefault(kind + "s", []).append(entry)
    _save_track(path, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
