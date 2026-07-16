"""dod_gate.py (t-150, V3-Б) -- SubagentStop-хук Claude Code,
блокирующий сдачу воркера, если после последней правки файлов нет
зелёного проверочного прогона (детерминированный инвариант "код
фиксирует ПОРЯДОК событий, смысл СУДИТ ярус выше" -- D-0063; тот же
класс механизма, что снимок дерева tools/critic_gate.py, V3-А).
Читает трек, который пишет tools/dod_track.py (PostToolUse-хук в этом
же ките) -- см. его докстринг за полную эмпирику payload'а
PostToolUse и её ограничения; здесь -- только контракт SubagentStop.

КОНТРАКТ SubagentStop -- ЭМПИРИКА (тот же метод/источник и то же
ОГРАНИЧЕНИЕ метода, что в tools/dod_track.py: Zod-схемы, извлечённые
строковым grep'ом с позитивным/негативным контролем из установленного
бинарника Claude Code, БЕЗ живого захвата реального payload'а через
настоящий диспатч субагента -- это потребовало бы Task/Agent-тула,
что вне роли builder, D-0037):

 - Payload (схема XWb): базовые поля (session_id, transcript_path,
   cwd, prompt_id?) + hook_event_name="SubagentStop",
   stop_hook_active: bool, agent_id, agent_transcript_path,
   agent_type, last_assistant_message?, background_tasks?.
 - Блокировка остановки -- ОБЩИЙ код раннера хуков для всех типов
   command-хуков (не специфичный для Stop): "заблокировано" =
   (exit code процесса == 2) ИЛИ (JSON на stdout при exit 0 несёт
   верхнеуровневое поле "decision": "block"). Для SubagentStop ОБА
   пути реально превентят остановку (в отличие от PostToolUse, где
   exit 2 -- НЕблокирующая ошибка, тул уже выполнился). Этот хук
   использует exit 2 + текст в stderr -- тот же контракт, что уже
   реализован и (частично) проверен смоком в tools/critic_gate.py
   этого кита, ради единообразия протокола на оба хука кита, а не
   потому что JSON-decision путь хуже задокументирован.
 - stop_hook_active (эмпирика, НЕ используется этим кодом как
   условие): раннер выставляет true при ПОВТОРНОМ вызове
   Stop-хука, случившемся ПОТОМУ ЧТО предыдущий вызов уже
   заблокировал остановку -- защита от бесконечного цикла на
   уровне харнесса; официальная рекомендация -- пропускать
   (return success), пока флаг истинный. Спека t-150 задаёт СВОЙ
   предохранитель поверх этого явно ("после 2 блоков подряд в
   одной сессии — пропустить") -- реализован ниже через СОБСТВЕННЫЙ
   счётчик в трек-файле (gate_state.consecutive_blocks), НЕ через
   stop_hook_active: независимая, более консервативная защита
   (счётчик переживает весь трек сессии; про поведение
   stop_hook_active харнесса на разных турнах эмпирики не хватает,
   чтобы полагаться только на него). Оба механизма не противоречат
   друг другу -- если Lead-смок покажет, что stop_hook_active сам по
   себе достаточен и делает счётчик избыточным, это находка для
   отдельного упрощения, не блокер для этой сдачи.

Логика (main()):
 1. Прочитать трек .claude/dod_track/<session_id>.json (тот же путь,
    что пишет tools/dod_track.py). Файла нет или "edits" пуст ->
    правок не было (типичный scout/critic-класс субагент) -> пропуск,
    exit 0, gate_state не трогаем.
 2. Правки были: сравнить max(ts правок) и max(ts ЗЕЛЁНЫХ прогонов).
    Зелёных прогонов нет ИЛИ последний зелёный раньше последней
    правки -> нарушение инварианта DoD.
 3. Нарушения нет (есть зелёный прогон после последней правки) ->
    exit 0; если до этого копился счётчик consecutive_blocks -- он
    сбрасывается в 0 (успешная сдача обнуляет предохранитель).
 4. Нарушение есть: смотрим gate_state.consecutive_blocks (0 по
    умолчанию).
      - Если < 2: блокируем (exit 2 + BLOCK_MESSAGE в stderr),
        счётчик += 1.
      - Если >= 2 (это был бы ТРЕТИЙ подряд блок): защита от
        вечного блока -- НЕ блокируем (exit 0), пишем
        предупреждение в stderr (SAFETY_SKIP_MESSAGE), счётчик
        сбрасывается в 0 (новый цикл), в трек добавляется факт
        gate_log-события "skipped_after_2_blocks" (видимость для
        witness/отладки -- не требование спеки буквально, но спека
        требует, чтобы "факт остаётся в треке", это оно и есть).
    В обеих ветках пишем gate_log-событие ("blocked" |
    "skipped_after_2_blocks") -- телеметрия для юнит-тестов и
    будущего разбора, ключ "gate_log" в том же файле трека, рядом с
    "edits"/"runs"/"gate_state"; tools/dod_track.py эти ключи не
    трогает и не удаляет при своих read-modify-write (сохраняет
    неизвестные ключи как есть).

Отсутствие session_id/трек-файла или неразборчивый payload -- fail
open (exit 0), тот же принцип, что в critic_gate.py и dod_track.py:
хук не должен ронять чужой субагент из-за собственной ошибки
парсинга, если задача НЕ распознана как "SubagentStop с правками".

===========================================================================
STAGING_HQ ВАРИАНТ (t-159, п.7 -- НЕ активирован, staging-копия для
ревью и постановки Lead'ом, D-0069). Отличия ОТ КИТА, явно:
 1. Байтовое чтение stdin (та же UTF-8-правка, что t-159 п.3/
    dispatch_gate.py) -- применено единообразно ко всем staging_hq
    хукам.
 2. НОВОЕ правило evaluate(): "правки ТОЛЬКО .md/.json файлов НЕ
    требуют прогона" (спека t-159 п.7, "док-правки без кода --
    легитимная сдача") -- если ВСЕ edit-записи трека несут
    file_path (см. staging_hq/tools/dod_track.py -- поле, которого
    нет в kit-версии) с расширением .md или .json, invariant
    ПРОПУСКАЕТСЯ целиком (не требуется НИ ОДНОГО прогона вообще, не
    только "прогон после последней"). Edit-запись с НЕИЗВЕСТНЫМ
    file_path (None -- либо старый трек до этой правки, либо
    payload без поля) трактуется КОНСЕРВАТИВНО как "не doc-only" --
    отсутствие информации НЕ даёт права на исключение (эта ОДНА
    ветка -- fail-CLOSED, в отличие от остального fail-open файла:
    спутать "не знаю" с "точно только доки" опаснее лишнего блока).
    Смешанная правка (хоть один .py/другой файл среди edits) --
    исключение НЕ применяется, обычный инвариант в силе.
 3. НОВОЕ (2026-07-16, находка 4 первой живой сессии, "разделение
    поверхностей гейтов"): evaluate()/decide() принимают agent_id --
    оценка DoD-инварианта ограничена ЗАПИСЯМИ СВОЕГО воркера
    (e.get("agent_id") == agent_id), а не всем треком сессии целиком.
    ДО этой правки dod_gate.py читал ВЕСЬ трек
    .claude/dod_track/<session>.json, включая main-правки координатора
    (agent_id=null) и правки ДРУГИХ параллельных субагентов -- живой
    gate_log этой сессии зафиксировал два реальных блока чистого
    воркера за чужие непрогнанные правки (плюс срабатывание
    предохранителя consecutive_blocks) прежде чем находка была
    замечена. Зона main-правок ЦЕЛИКОМ принадлежит tools/main_gate.py
    (Stop-хук, свой main_gate_state, свой JOURNAL-варнинг) --
    dod_gate.py (SubagentStop) их больше не видит ни при каком
    agent_id. Если SubagentStop-payload не несёт agent_id вовсе
    (defensive-ветка -- параметр agent_id=None) -- консервативный
    fallback "все НЕ-main записи" (agent_id непустой, любой субагент):
    main-правки исключены в любом случае, но субагенты между собой в
    этой ветке не различаются (эмпирики о payload недостаточно для
    точного различения -- см. main()). Побочный эффект: per-agent
    фильтр заодно исключает взаимные блокировки ПАРАЛЛЕЛЬНЫХ воркеров
    одной сессии (правило 4 политики маршрутизации -- разные воркеры
    делят session_id, но не должны блокировать друг друга чужими
    непрогнанными правками).
===========================================================================
"""

import json
import sys
from pathlib import Path

BLOCK_MESSAGE = (
    "Сдача заблокирована: после последней правки нет зелёного "
    "проверочного прогона. Прогони проверку по DoD (pytest/команду "
    "прогона) и сдавай зелёным."
)

SAFETY_SKIP_MESSAGE = (
    "dod_gate: предохранитель от вечного блока сработал -- 2 блока "
    "подряд уже были в этой сессии, сдача пропущена БЕЗ зелёного "
    "прогона (факт зафиксирован в треке, не является заменой "
    "проверки)."
)

CONSECUTIVE_BLOCK_LIMIT = 2

# STAGING_HQ п.7: расширения, которые считаются "документацией/
# конфигом без кода" -- правка ТОЛЬКО такими файлами не требует
# прогона. .jsonl добавлен Lead'ом при приёмке порта (ревью t-159):
# правка logs/routing-log.jsonl -- штатная операция КАЖДОЙ штабной
# сессии; журнал -- данные, не код, и гейтится СВОИМ pre-commit
# валидатором (tools/journal_validator.py, D-0069) -- pytest к нему
# отношения не имеет; без .jsonl main_gate ложно блокировал бы
# сессию, правившую только журнал+доки.
DOC_ONLY_EXTENSIONS = {".md", ".json", ".jsonl"}


def _is_doc_only_file(file_path) -> bool:
    if not isinstance(file_path, str) or not file_path:
        return False  # неизвестный путь -- консервативно НЕ doc-only
    return Path(file_path).suffix.lower() in DOC_ONLY_EXTENSIONS


def _all_edits_doc_only(edits) -> bool:
    """STAGING_HQ п.7: True, если В КАЖДОЙ edit-записи file_path
    известен И doc-only (.md/.json). См. докстринг модуля за
    обоснование fail-closed трактовки неизвестного file_path."""
    if not edits:
        return False
    return all(_is_doc_only_file(e.get("file_path")) for e in edits)


def _track_path(cwd: str, session_id: str) -> Path:
    return Path(cwd or ".") / ".claude" / "dod_track" / f"{session_id}.json"


def _load_track(path: Path) -> dict:
    if not path.exists():
        return {"edits": [], "runs": [], "gate_state": {"consecutive_blocks": 0}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"edits": [], "runs": [], "gate_state": {"consecutive_blocks": 0}}
    if not isinstance(data, dict):
        return {"edits": [], "runs": [], "gate_state": {"consecutive_blocks": 0}}
    data.setdefault("edits", [])
    data.setdefault("runs", [])
    data.setdefault("gate_state", {"consecutive_blocks": 0})
    data["gate_state"].setdefault("consecutive_blocks", 0)
    return data


def _save_track(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def evaluate(track: dict, agent_id: str | None = None) -> tuple[bool, str]:
    """Чистая логика инварианта, без I/O -- тестируемая напрямую.

    agent_id задан (штатный путь SubagentStop): edits и runs
    фильтруются до записей ИМЕННО этого агента (e.get("agent_id") ==
    agent_id) ДО применения остальной логики -- правки других
    воркеров и main-правки (agent_id null/пусто) этой оценке не
    видны (находка 4 первой живой сессии, 2026-07-16 -- см. блок
    STAGING_HQ ВАРИАНТ п.3 в докстринге модуля).
    agent_id НЕ задан (None -- payload без поля, defensive-ветка):
    консервативный fallback "все НЕ-main записи" (agent_id непустой)
    -- main-правки исключаются в любом случае (их зона -- зона
    tools/main_gate.py), но субагенты между собой не различаются.

    Возвращает (violation: bool, reason: str). reason -- только для
    отладки/тестов, не парсится вызывающим кодом."""
    all_edits = track.get("edits") or []
    if agent_id:
        edits = [e for e in all_edits if e.get("agent_id") == agent_id]
    else:
        edits = [e for e in all_edits if e.get("agent_id")]
    if not edits:
        return False, "no-edits"

    if _all_edits_doc_only(edits):
        return False, "doc-only-edits-exempt"

    all_runs = track.get("runs") or []
    if agent_id:
        runs = [r for r in all_runs if r.get("agent_id") == agent_id]
    else:
        runs = [r for r in all_runs if r.get("agent_id")]
    last_edit_ts = max(e["ts"] for e in edits)

    green_runs = [r for r in runs if r.get("outcome") == "green"]
    if not green_runs:
        return True, "no-green-run"

    last_green_ts = max(r["ts"] for r in green_runs)
    if last_green_ts < last_edit_ts:
        return True, "green-before-last-edit"

    return False, "green-after-last-edit"


def decide(track: dict, agent_id: str | None = None) -> tuple[int, str, dict]:
    """Чистая логика решения ПОСЛЕ загрузки трека. agent_id прокидывается
    в evaluate() без изменений (см. его докстринг за семантику фильтра).
    Возвращает (exit_code, stderr_message, updated_track). updated_track --
    трек с обновлённым gate_state/добавленным gate_log-событием;
    запись на диск -- забота main()."""
    violation, reason = evaluate(track, agent_id)
    gate_state = track.setdefault("gate_state", {"consecutive_blocks": 0})
    consecutive = gate_state.get("consecutive_blocks", 0)

    if not violation:
        if consecutive:
            gate_state["consecutive_blocks"] = 0
        return 0, "", track

    if consecutive >= CONSECUTIVE_BLOCK_LIMIT:
        gate_state["consecutive_blocks"] = 0
        track.setdefault("gate_log", []).append(
            {"action": "skipped_after_2_blocks", "reason": reason}
        )
        return 0, SAFETY_SKIP_MESSAGE, track

    gate_state["consecutive_blocks"] = consecutive + 1
    track.setdefault("gate_log", []).append({"action": "blocked", "reason": reason})
    return 2, BLOCK_MESSAGE, track


def _reconfigure_stderr_utf8():
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _extract_agent_id_from_payload(payload: dict):
    """Достаёт agent_id из payload-поля верхнего уровня "agent_id" --
    та же трактовка пустоты, что tools/dod_track.py._extract_agent_id
    и tools/main_gate.py._is_main_entry (None/пустая строка -- не
    задан). Локальная копия, не импорт из dod_track.py/main_gate.py:
    тот же паттерн дублирования, что main_gate.py уже применяет
    (_is_main_entry) -- оба файла вне owns этой задачи (main_gate.py,
    dod_track.py -- НЕ трогать)."""
    value = payload.get("agent_id")
    return value if isinstance(value, str) and value else None


def main() -> int:
    _reconfigure_stderr_utf8()

    # STAGING_HQ: байтовое stdin-чтение (t-159 п.3-стиль правка).
    raw_bytes = sys.stdin.buffer.read()
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception:
        return 0

    session_id = payload.get("session_id")
    if not session_id:
        return 0

    cwd = payload.get("cwd") or "."
    path = _track_path(cwd, session_id)
    existed_before = path.exists()
    track = _load_track(path)

    agent_id = _extract_agent_id_from_payload(payload)
    exit_code, message, updated_track = decide(track, agent_id)

    # "Правок не было -> пропуск" (спека): если трек-файла ещё не
    # было И правок в этом вызове нет -- по-настоящему ничего не
    # делаем, файл не создаём (scout/critic-класс субагент не должен
    # обрастать пустым .claude/dod_track/<session_id>.json). Если
    # файл уже существовал (dod_track.py его создал раньше) --
    # пишем всегда, чтобы gate_state/gate_log были согласованы.
    if existed_before or updated_track.get("edits"):
        _save_track(path, updated_track)

    if message:
        sys.stderr.write(message + "\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
