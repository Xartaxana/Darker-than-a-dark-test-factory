"""main_gate.py (t-159, очередь v5 п.1) -- Stop-хук Claude Code,
блокирующий завершение MAIN-хода координатора той же логикой, что
tools/dod_gate.py применяет к SubagentStop: "после последней MAIN-
правки нет зелёного проверочного прогона" -> блок. Механизация
находки policy-as-code: SubagentStop структурно НЕ видит main-сессию
координатора (4 подтверждения по журналу №5-№10б,
docs/tasks/2026-07-16_economy-exam-run7.md) -- координатор мог
править деливерабл САМ после последнего critic/DoD-цикла, и ни один
существующий гейт этого не ловил (прецедент №9-t3: README дописывался
после последнего зелёного, SubagentStop-гейты этого не видят
структурно -- они срабатывают только на завершении СУБАГЕНТОВ).

КОНТРАКТ Stop -- ЭМПИРИКОЙ, тем же методом/источником, что дал схему
XWb для SubagentStop в tools/dod_gate.py (grep -a установленного
бинарника claude.exe, позитивный/негативный контроль F-30/F-34):
 - Схема zWb (найдена вырезкой из бандла): n0() (базовые поля) И
   {hook_event_name: literal("Stop"), stop_hook_active: bool,
   last_assistant_message?: str, background_tasks?: array,
   session_crons?: array}. В ОТЛИЧИЕ от SubagentStop (схема XWb) --
   "Stop" НЕ несёт agent_id/agent_transcript_path/agent_type как
   ОБЯЗАТЕЛЬНЫЕ поля СОБЫТИЯ: конструктор события в бандле (функция
   n6e) строит ветку SubagentStop с ЯВНЫМ agent_id:o (subagent id
   аргумента), а ветку "Stop" -- БЕЗ этих полей вовсе: "{...kf(e,
   void 0,i),hook_event_name:\"Stop\",stop_hook_active:n,
   last_assistant_message:p,...f}". Базовая же схема n0() технически
   несёт agent_id?/agent_type? как ОПЦИОНАЛЬНЫЕ поля (см. докстринг
   tools/dod_track.py) -- на main-ходе координатора kf() их не
   заполняет (координатор -- не субагент), поэтому оба пути (схема
   события "Stop" и общее правило n0().agent_id) сходятся: main-ход
   не несёт agent_id. Это и есть механизм различения main/subagent
   записей в общем треке (tools/dod_track.py._extract_agent_id).
 - Контракт блокировки -- ОБЩИЙ для command-хуков (тот же, что
   документирует tools/dod_gate.py): "заблокировано" = (exit code
   процесса == 2) ИЛИ (JSON на stdout при exit 0 несёт "decision":
   "block"). Этот хук использует exit 2 + текст в stderr, тот же
   протокол, что dod_gate.py/critic_gate.py этого кита. Runtime-
   подтверждение (тот же grep -a, строка предупреждения о лимите
   блоков в самом бандле): "For Stop/SubagentStop hooks, check
   stop_hook_active in the input and return success while it's true.
   Set CLAUDE_CODE_STOP_HOOK_BLOCK_CAP to raise this limit." --
   явно говорит, что Stop и SubagentStop РАЗДЕЛЯЮТ протокол
   блокировки на уровне раннера хуков (не специфично для одного типа
   события).
 - stop_hook_active -- та же трактовка, что dod_gate.py: НЕ
   используется этим кодом как условие (харнесс сам защищает от
   бесконечного цикла через CLAUDE_CODE_STOP_HOOK_BLOCK_CAP, env-
   переменная, видна в том же runtime-фрагменте бандла). Свой
   предохранитель -- через СОБСТВЕННЫЙ счётчик в треке,
   "main_gate_state.consecutive_blocks", НАМЕРЕННО ОТДЕЛЬНЫЙ от
   dod_gate.py "gate_state.consecutive_blocks": session_id ОБЩИЙ у
   main-хода и ВСЕХ его субагентов (тот же kf()-конструктор,
   session_id не зависит от agent_id) -- общий счётчик дал бы ложную
   интерференцию между Stop- и SubagentStop-блокировками одной
   сессии (см. докстринг tools/dod_track.py, раздел "Хранилище").

Проверки main() -- буквально по спеке t-159 п.1:
 (а) main-thread правки БЫЛИ (dod_track.edits/runs с agent_id
     отсутствует/None -- см. tools/dod_track.py) И нет ЗЕЛЁНОГО
     прогона (main-only) ПОСЛЕ последней main-only правки -> БЛОК.
     Тот же предохранитель "2 блока подряд", что dod_gate.py -- третий
     подряд блок В ОДНОМ цикле пропускается со честной пометкой в
     трек (gate_log, ключ "gate":"main" отличает записи main_gate.py
     от dod_gate.py в общем логе).
 (б) logs/routing-log.jsonl СУЩЕСТВУЕТ и пуст (0 непустых строк) ПРИ
     непустом main-only dod_track (хоть одна main-only edit/run) ->
     ДОПОЛНИТЕЛЬНАЯ строка-предупреждение В ТО ЖЕ block-сообщение
     (а). БУКВАЛЬНОЕ прочтение спеки ("предупреждение В блок-
     сообщение" -- предупреждение живёт ВНУТРИ сообщения (а), не
     отдельный независимый blocking/warning-путь): если (а) НЕ
     обнаруживает нарушения (зелёный прогон после последней main-only
     правки есть) -- проверка (б) НЕ производит отдельного
     вывода/exit-кода, поскольку "блок-сообщения", во что можно было
     бы дописать предупреждение, в этом случае не возникает. Это
     самостоятельное инженерное решение по буквальному тексту спеки
     (спека не описывает "б без а" отдельной веткой), задокументировано,
     не молча.
 Скоуп-констрейнт t-151 (спека т-159 п.1 ссылается буквально): "журнал
 валидируется standalone только если он полевой (не git-репо) — в
 ките это всегда так" -- в данном хуке это НЕ вопрос выбора: main_gate.py
 НЕ вызывает journal_validator.py вовсе, проверка (б) не про ВАЛИДНОСТЬ
 журнала (это ответственность tools/journal_validator.py /
 pre-commit-гейта), а буквально про "пуст/не пуст файл на диске" --
 прямое чтение, без git и без стандалон-режима validator'а.
 ЭМПИРИЧЕСКАЯ ПОПРАВКА к буквальному тексту спеки (F-30, находка t-159,
 не блокер для этого пункта): "в ките это всегда так" -- НЕВЕРНО для
 ЭТОГО каталога буквально. `git rev-parse --is-inside-work-tree` из
 D:/Improving_AI/exam_fullgates_kit возвращает true -- у кита ЕСТЬ
 СОБСТВЕННЫЙ .git (2 коммита, ветка main: "fullgates kit v4" / "v4.1
 фикс сборочной ошибки" -- та же история, что описывает run-лог t-159).
 journal_validator.py._git_available() на ЭТОМ каталоге пойдёт ОБЫЧНЫМ
 git-staged путём, НЕ standalone. Констрейнт t-151, по всей видимости,
 говорит о РАЗВЁРНУТОЙ ПОЛЕВОЙ КОПИИ кита в экзаменной песочнице (без
 .git, куда кит копируется на прогон), а не о ЭТОМ репозитории-
 источнике -- различие важное, но НЕ влияет на этот хук: main_gate.py
 не вызывает validator вовсе, риск "13/213 легаси-нарушений"
 (docs/tasks/2026-07-16_policy-as-code-design.md) для него не
 материализуется независимо от того, какой из двух смыслов "кит"
 имелся в виду.

Fail-open -- тот же принцип, что у остальных хуков кита:
нераспознаваемый JSON / отсутствующий session_id -> exit 0 без
побочных эффектов.

t-159 КОДИРОВКА STDIN: та же правка, что tools/dispatch_gate.py
(очередь v5 п.3) -- читаем sys.stdin.buffer (байты) и декодируем
явно UTF-8 с errors="replace", НЕ sys.stdin.read() (платформенная
кодировка -- cp1251 на этой машине, см. докстринг dispatch_gate.py
за эмпирику). Этот файл новый в t-159 -- пишем сразу правильно, не
копируя известный баг в новый код.
"""

import json
import sys
from pathlib import Path

BLOCK_MESSAGE = (
    "Сдача main-хода заблокирована: после последней правки координатора "
    "нет зелёного проверочного прогона. Прогони проверку по DoD "
    "(pytest/команду прогона) и завершай зелёным."
)

EMPTY_JOURNAL_WARNING = (
    " ПРЕДУПРЕЖДЕНИЕ: logs/routing-log.jsonl существует и пуст, хотя "
    "трек main-хода не пуст -- маршрутизация этой сессии не залогирована."
)

SAFETY_SKIP_MESSAGE = (
    "main_gate: предохранитель от вечного блока сработал -- 2 блока "
    "подряд уже были в этой сессии, завершение пропущено БЕЗ зелёного "
    "прогона (факт зафиксирован в треке, не является заменой проверки)."
)

CONSECUTIVE_BLOCK_LIMIT = 2

JOURNAL_REL_PATH = Path("logs") / "routing-log.jsonl"


def _track_path(cwd: str, session_id: str) -> Path:
    return Path(cwd or ".") / ".claude" / "dod_track" / f"{session_id}.json"


def _default_track() -> dict:
    return {"edits": [], "runs": [], "main_gate_state": {"consecutive_blocks": 0}}


def _load_track(path: Path) -> dict:
    if not path.exists():
        return _default_track()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_track()
    if not isinstance(data, dict):
        return _default_track()
    data.setdefault("edits", [])
    data.setdefault("runs", [])
    data.setdefault("main_gate_state", {"consecutive_blocks": 0})
    data["main_gate_state"].setdefault("consecutive_blocks", 0)
    return data


def _save_track(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _is_main_entry(entry: dict) -> bool:
    """agent_id отсутствует/None/пусто -> main-thread запись (см.
    tools/dod_track.py._extract_agent_id -- та же трактовка "пусто")."""
    return not entry.get("agent_id")


# STAGING_HQ (t-159 п.7): "правки ТОЛЬКО .md/.json файлов НЕ требуют
# прогона" -- то же правило и та же fail-closed трактовка неизвестного
# file_path, что tools/dod_gate.py (см. его докстринг за полное
# обоснование); здесь применяется к MAIN-ONLY подмножеству.
# .jsonl добавлен Lead'ом при приёмке порта (см. dod_gate.py --
# журнал routing-log.jsonl гейтится своим pre-commit валидатором).
DOC_ONLY_EXTENSIONS = {".md", ".json", ".jsonl"}


def _is_doc_only_file(file_path) -> bool:
    if not isinstance(file_path, str) or not file_path:
        return False
    return Path(file_path).suffix.lower() in DOC_ONLY_EXTENSIONS


def _all_edits_doc_only(edits) -> bool:
    if not edits:
        return False
    return all(_is_doc_only_file(e.get("file_path")) for e in edits)


def evaluate(track: dict) -> tuple[bool, str]:
    """Проверка (а), чистая логика -- та же сигнатура/семантика, что
    dod_gate.evaluate(), но на MAIN-ONLY подмножестве edits/runs.
    STAGING_HQ: doc-only (.md/.json) main-only правки освобождены от
    инварианта целиком (см. DOC_ONLY_EXTENSIONS выше)."""
    edits = [e for e in (track.get("edits") or []) if _is_main_entry(e)]
    if not edits:
        return False, "no-main-edits"

    if _all_edits_doc_only(edits):
        return False, "doc-only-edits-exempt"

    runs = [r for r in (track.get("runs") or []) if _is_main_entry(r)]
    last_edit_ts = max(e["ts"] for e in edits)

    green_runs = [r for r in runs if r.get("outcome") == "green"]
    if not green_runs:
        return True, "no-green-run"

    last_green_ts = max(r["ts"] for r in green_runs)
    if last_green_ts < last_edit_ts:
        return True, "green-before-last-edit"

    return False, "green-after-last-edit"


def _journal_empty_warning_applies(cwd: str, track: dict) -> bool:
    """Проверка (б): True, если logs/routing-log.jsonl СУЩЕСТВУЕТ и
    пуст (0 непустых строк) ПРИ непустом main-only dod_track (хоть
    одна main-only edit/run -- буквально "непустом dod_track", не
    "есть нарушение (а)")."""
    journal_path = Path(cwd or ".") / JOURNAL_REL_PATH
    if not journal_path.exists():
        return False
    try:
        text = journal_path.read_text(encoding="utf-8")
    except Exception:
        return False
    if text.strip():
        return False  # журнал не пуст -- проверка (б) не применяется

    main_edits = [e for e in (track.get("edits") or []) if _is_main_entry(e)]
    main_runs = [r for r in (track.get("runs") or []) if _is_main_entry(r)]
    return bool(main_edits or main_runs)


def decide(track: dict, cwd: str = ".") -> tuple[int, str, dict]:
    """Чистая логика решения ПОСЛЕ загрузки трека -- тот же стиль, что
    dod_gate.decide(). cwd нужен только для проверки (б) (чтение
    logs/routing-log.jsonl); сам track уже загружен вызывающим кодом.
    Возвращает (exit_code, stderr_message, updated_track)."""
    violation, reason = evaluate(track)
    gate_state = track.setdefault("main_gate_state", {"consecutive_blocks": 0})
    consecutive = gate_state.get("consecutive_blocks", 0)

    if not violation:
        if consecutive:
            gate_state["consecutive_blocks"] = 0
        return 0, "", track

    warn = _journal_empty_warning_applies(cwd, track)

    if consecutive >= CONSECUTIVE_BLOCK_LIMIT:
        gate_state["consecutive_blocks"] = 0
        track.setdefault("gate_log", []).append(
            {"action": "skipped_after_2_blocks", "reason": reason, "gate": "main"}
        )
        message = SAFETY_SKIP_MESSAGE + (EMPTY_JOURNAL_WARNING if warn else "")
        return 0, message, track

    gate_state["consecutive_blocks"] = consecutive + 1
    track.setdefault("gate_log", []).append(
        {"action": "blocked", "reason": reason, "gate": "main"}
    )
    message = BLOCK_MESSAGE + (EMPTY_JOURNAL_WARNING if warn else "")
    return 2, message, track


def _reconfigure_stderr_utf8():
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    _reconfigure_stderr_utf8()

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

    exit_code, message, updated_track = decide(track, cwd)

    # Тот же принцип, что dod_gate.py: не создаём трек-файл на ровном
    # месте, если он не существовал и main-only правок нет вовсе
    # (сессия без единой правки координатора -- read-only ход).
    if existed_before or updated_track.get("edits"):
        _save_track(path, updated_track)

    if message:
        sys.stderr.write(message + "\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
