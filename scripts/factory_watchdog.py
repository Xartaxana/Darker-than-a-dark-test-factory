"""factory_watchdog — сторож окна-фабрики + ночной резерв (spec-factory-window
v7 = v6 К3 + Д1 консолидированная секция, docs/tasks/factory-visible-window.md,
2026-08-16).

Архитектура «окно-фабрика + сторож» (слово оператора 2026-08-16):
`/qa-loop` ведёт скилл `.claude/skills/factory/SKILL.md` из ОТКРЫТОГО окна
Claude Code. Этот модуль тикает каждые PT30M (`scripts/heartbeat.cmd`) и
делает ДВЕ вещи:

  1. **Сторожит** (К3, v6, БЕЗ ИЗМЕНЕНИЙ) — сверяет ДВА сигнала прогресса
     (`state/loop.lock`, `state/factory-mode.json`) со снимками прошлого
     тика и объявляет тревогу (`[factory:stalled]`), если оба молчат
     дольше порога.
  2. **Ночной резерв (Д1, НОВОЕ)** — класс «фон не ведёт» здесь БОЛЬШЕ
     НЕВЕРЕН БЕЗ ОГОВОРОК: если STALLED (окно активно, но молчит) держится
     ≥ `FALLBACK_DELAY_MIN` (15 мин) И `night_fallback` не выключен И
     бюджет не исчерпан И предикаты серийных поломок (fastdeath/slowdeath)
     чисты — сторож САМ спавнит ОДИН резервный проход `/qa-loop 5` через
     `heartbeat_wrap.run_fallback_pass(...)` (та же child-spawn-машинерия,
     что депрекированный `run_pass`). Это ЕДИНСТВЕННЫЙ путь, которым фон
     когда-либо запускает `/qa-loop` сам — окно-фабрика остаётся штатным
     водителем; резерв подхватывает ТОЛЬКО мёртвое вождение.

Состояние сторожа — `state/factory-watchdog.json` (gitignored):
`last_lock_snapshot`, `last_mode_snapshot`, `last_progress_ts`,
`last_alert_ts`, `last_state`, `notes` (v6, см. ниже) + Д1:
`stalled_since` (начало ТЕКУЩЕГО эпизода STALLED «mode активный» — только
эта разновидность триггерит резерв), `empty_streak` (подряд пустых
резервных проходов), `slowdeath_streak`/`slowdeath_last_ts`/
`slowdeath_stopped` (серия медленных отказов резерва), `unknown_streak`
(подряд «неизвестных» исходов канала last-pass-summary),
`last_fallback_ts`/`last_fallback_toast_ts`/`last_fastdeath_toast_ts`/
`last_slowdeath_toast_ts` (тосты — четыре класса, п.7; **Н3 (Lead-
решение, критик-раунд Д1): тост запуска резерва звонит на КАЖДЫЙ
запуск, `last_fallback_toast_ts` — ТОЛЬКО диагностическая метка «когда
был последний», не 4ч-кулдаун — гейт триггера уже гарантирует ≤1
запуск/тик**; стоп-fastdeath/stop-slowdeath/тревога-STALLED остаются
НА 4ч-кулдауне), `fallback_runs`/`fallback_runs_24h`/
`fallback_runs_24h_ts` (Н1: телеметрия, НЕ гейт — инкремент В STATE-
ФАЙЛЕ ДО Popen, `_bump_fallback_telemetry`), `self_write_snapshot`/
`fallback_holder` (диагностика — что сторож сам записал последним
резервным проходом).

Обновляется на КАЖДОМ тике, ВКЛЮЧАЯ тихие ветки — это heartbeat САМОГО
сторожа (детектор фолбэка ридера задачи планировщика — doctor-чек
`LastRunTime задачи < 2ч` + чек 3б session-handoff, НЕ этот state-файл).

Прогресс = изменение `loop.lock` ИЛИ `factory-mode.json`
(`mode`/`updated_ts`/`passes_done`/`session_nonce` — Д п.4: nonce входит в
снимок, смена nonce = прогресс окна) относительно снимков ПРЕДЫДУЩЕГО
тика. **Атрибуция (Д п.4):** прогресс вычисляется ДО запуска резервного
прохода этого тика (если он вообще случится) — собственные записи
резерва (свой mode-write, свой лок, включая протёкший после timeout_kill)
поэтому НИКОГДА не путаются с прогрессом окна: `changed`/`last_progress_ts`
решаются по снимку НАЧАЛА тика, снимок КОНЦА тика (после резерва, если он
бежал) сохраняется в state ТОЛЬКО как база для СЛЕДУЮЩЕГО тика.

**Матрица (приоритет сверху вниз, однозначно, v6 БЕЗ ИЗМЕНЕНИЙ) — см.
докстринг ветвей 0-4 ниже; резерв (Д1) — ДОПОЛНИТЕЛЬНЫЙ шаг ПОСЛЕ
классификации, СТРОГО внутри ветки 3 (mode активный, STALLED).**

Всё I/O — неброcающее (класс BL-4): ЛЮБАЯ ошибка чтения/записи/сети
ловится локально и печатается, `main()` дополнительно обёрнут catch-all —
`sys.exit(0)` всегда.

Запуск (production, без флагов): `python scripts/factory_watchdog.py`
Флаги — ТОЛЬКО для тестов/смок-прогонов: `--lock-file/--mode-file/
--state-file/--sla-file/--escalations-file/--orchestrator-log/--now`.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import heartbeat_wrap as hw
import loop_lock as ll
import pass_summary as ps
import sla_utils

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO / "state" / "loop.lock"
DEFAULT_MODE_FILE = REPO / "state" / "factory-mode.json"
DEFAULT_STATE_FILE = REPO / "state" / "factory-watchdog.json"
DEFAULT_SLA_FILE = REPO / "state" / "sla.yaml"
DEFAULT_ESCALATIONS_FILE = REPO / "state" / "escalations.md"
DEFAULT_ORCHESTRATOR_LOG = REPO / "state" / "orchestrator-log.md"
DEFAULT_PASS_SUMMARY_FILE = REPO / "state" / "last-pass-summary.json"
DEFAULT_FASTDEATH_FILE = hw.DEFAULT_FASTDEATH_PATH

STALL_NO_LOCK_MIN_DEFAULT = 60.0
STALL_IN_PASS_MIN_DEFAULT = 90.0
TOAST_COOLDOWN_HOURS_DEFAULT = 4.0

FACTORY_STALLED_KEY = "FACTORY-STALLED"
FACTORY_STALLED_TAG = "factory:stalled"
FACTORY_STALLED_RESOLVED_MARKER = "[resolved:factory-watchdog-recovered]"

RULE = "factory-watchdog"
AGENT = "factory_watchdog"

MODE_STOPPED = "stopped"
MODE_ACTIVE_DEFAULT_NIGHT_FALLBACK = "on"

POWERSHELL = "powershell.exe"
_TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

# --- Д1 ночной резерв: пороги -----------------------------------------------
FALLBACK_DELAY_MIN_DEFAULT = 15.0
# Порог обеих поломочных серий (слово оператора) — env-ручка + M6-границы.
FALLBACK_BLOCK_THRESHOLD_DEFAULT = 3
FALLBACK_BLOCK_PROBE_HOURS = 6.0
EMPTY_STREAK_STOP = 2
UNKNOWN_STREAK_TOAST = 3

FALLBACK_BROKEN_KEY = "FACTORY-FALLBACK-BROKEN"
FALLBACK_BROKEN_TAG = "factory:fallback-broken"

# --- v8: окно лимита подписки (2026-08-18, слово оператора) ----------------
# Пока лимит не сброшен, НИКТО проехать не может: ни окно (его цепочка
# ScheduleWakeup порвана сорванным ходом), ни резерв (ребёнок умрёт за
# секунды). Поэтому в лимитном окне сторож: (1) НЕ спавнит резерв,
# (2) МОЛЧИТ всеми тревожными классами тостов, (3) даёт РОВНО ОДИН тост на
# вход в окно и РОВНО ОДИН на возврат лимитов.
# Возврат отдаёт приоритет ЖИВОМУ окну на полном ярусе: `LIMIT_GRACE_MIN`
# минут после сброса резерв не стартует — это время оператора толкнуть
# окно. Не пришёл — дальше прежние правила ночного резерва.
LIMIT_GRACE_MIN_DEFAULT = 45.0
# Возвратный тост осмыслен, только пока сброс СВЕЖИЙ. Тик — раз в 30 мин,
# то есть штатное запаздывание <= 30 мин; 3ч — с запасом на пропущенные
# тики (спящий хост). Дальше это уже не новость, а протухшее состояние:
# гасим молча, иначе «лимиты вернулись» прилетит через сутки — ровно тот
# класс шума, от которого механизм и заводится.
LIMIT_RETURN_TOAST_MAX_LAG_H = 3.0
FACTORY_LIMIT_KEY = "FACTORY-USAGE-LIMIT"
FACTORY_LIMIT_TAG = "factory:usage-limit"
# Б3: тег возврата — тоже КОНСТАНТА и тоже печатается в orchestrator-log
# литералом, чтобы детектор F-11(в) был исполнимым грепом, а не прозой.
FACTORY_LIMIT_BACK_TAG = "factory:limit-back"
GENERIC_RESOLVED_MARKER = "[resolved:factory-watchdog]"


# --------------------------------------------------------------------------
# время / парсинг ts
# --------------------------------------------------------------------------

def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _fmt_ts(dt: datetime.datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value) -> datetime.datetime | None:
    """ISO ts -> aware datetime (UTC); naive трактуется как UTC (тот же
    приём, что loop_lock._parse_ts/doctor._lock_age_hours)."""
    if not value:
        return None
    try:
        ts = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# п.0: чтение/классификация трёх файлов сторожа
# --------------------------------------------------------------------------

def _read_json_or_none(path: Path) -> tuple[dict | None, bool, bool]:
    """(data, exists, corrupt). exists=False,corrupt=False => файла нет.
    exists=True,corrupt=True => файл есть, но нечитаем/не JSON-объект."""
    if not path.exists():
        return None, False, False
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, True, True
    if not isinstance(data, dict):
        return None, True, True
    return data, True, False


def _lock_snapshot(lock_file: Path) -> dict:
    """Снимок loop.lock для сравнения прогресса. Битый/без валидного `ts`
    лок -> `corrupt=True`, `holder`/`ts`=None — но `raw_hash` ВСЕГДА
    посчитан по сырым байтам (спека п.0: «сравнение по сырым байтам
    файла» для битого случая), так что изменение содержимого битого
    файла между тиками всё равно засчитывается как прогресс."""
    if not lock_file.exists():
        return {"exists": False, "corrupt": False, "holder": None, "ts": None, "raw_hash": None}
    try:
        raw = lock_file.read_bytes()
    except OSError:
        return {"exists": True, "corrupt": True, "holder": None, "ts": None, "raw_hash": None}
    raw_hash = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("не dict")
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {"exists": True, "corrupt": True, "holder": None, "ts": None, "raw_hash": raw_hash}
    holder = data.get("holder")
    ts_raw = data.get("ts")
    ts_valid = isinstance(ts_raw, str) and bool(ts_raw) and _parse_ts(ts_raw) is not None
    return {
        "exists": True,
        "corrupt": not ts_valid,
        "holder": holder if isinstance(holder, str) else None,
        "ts": ts_raw if ts_valid else None,
        "raw_hash": raw_hash,
    }


def _lock_present(lock_snap: dict) -> bool:
    """п.0/п.3: «лок есть» — существует, независимо от читаемости (битый
    лок = «лок есть» и для orphan-проверки п.2, и для предиката п.3)."""
    return bool(lock_snap.get("exists"))


def _lock_stale_for_orphan(lock_snap: dict, now: datetime.datetime, ttl_hours: float) -> bool:
    """п.2: возраст лока > TTL. Битый/без ts лок СЧИТАЕТСЯ протухшим сразу
    (сирота-кандидат) — согласовано с loop_lock.py REAPED-семантикой."""
    if not lock_snap.get("exists"):
        return False
    if lock_snap.get("corrupt") or not lock_snap.get("ts"):
        return True
    ts = _parse_ts(lock_snap["ts"])
    if ts is None:
        return True
    age_h = (now - ts).total_seconds() / 3600.0
    return age_h > ttl_hours


def _rel_path(path: Path) -> str:
    """Repo-относительный путь для колонки артефакта orchestrator-log —
    с фолбэком на абсолютный путь, если `path` не под REPO."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _mode_snapshot(mode_data: dict | None) -> dict:
    """Нормализованный снимок mode-файла для сравнения прогресса —
    `None` (mode нет/нечитаем/трактован как «нет») даёт единый снимок
    «пусто», как и по-настоящему отсутствующий файл. **Д п.4:**
    `session_nonce` ВХОДИТ в снимок — смена nonce (takeover/новое
    вождение) сама по себе засчитывается как прогресс окна (закрывает
    эпизод STALLED/резерва), даже если остальные поля пока совпадают."""
    if mode_data is None:
        return {"mode": None, "updated_ts": None, "passes_done": None, "session_nonce": None}
    return {
        "mode": mode_data.get("mode"),
        "updated_ts": mode_data.get("updated_ts"),
        "passes_done": mode_data.get("passes_done"),
        "session_nonce": mode_data.get("session_nonce"),
    }


# --------------------------------------------------------------------------
# non-throwing writers
# --------------------------------------------------------------------------

def _append_orchestrator_line(path: Path, artifact: str, outcome: str,
                              now: datetime.datetime) -> None:
    safe = [c.replace("|", "\\|").replace("\n", " ").strip()
            for c in (RULE, AGENT, artifact, outcome)]
    line = "| " + " | ".join([_fmt_ts(now)] + safe) + " |\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        print(f"ORCHESTRATOR-LOG write failed: {e}")


_ESCALATION_LINE_RE = re.compile(
    r"(?m)^- \[(?P<ts>[^\]]+)\] \*\*" + re.escape(FACTORY_STALLED_KEY) +
    r"\*\*(?:\s*\[resolved:[^\]]*\])?\s*\[" + re.escape(FACTORY_STALLED_TAG) +
    r"\] — [^\r\n]*")


def _write_singleton_escalation(escalations_path: Path, message: str,
                                now: datetime.datetime, *, resolved: bool = False) -> None:
    """Дедуп-запись `[factory:stalled]`-эскалации (класс BL-4: НИКОГДА не
    бросает исключение наружу). `resolved=True` — пишет якорь `[resolved:
    factory-watchdog-recovered]` СРАЗУ после `**KEY**`."""
    try:
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        text = escalations_path.read_bytes().decode("utf-8") if escalations_path.exists() else ""
        eol = "\r\n" if "\r\n" in text else "\n"
        resolved_part = f" {FACTORY_STALLED_RESOLVED_MARKER}" if resolved else ""

        m = _ESCALATION_LINE_RE.search(text)
        if m:
            new_line = (f"- [{m.group('ts')}] **{FACTORY_STALLED_KEY}**{resolved_part} "
                       f"[{FACTORY_STALLED_TAG}] — {message}")
            new_text = text[:m.start()] + new_line + text[m.end():]
        else:
            if not text:
                text = ll.ESCALATIONS_HEADER
            elif not text.endswith("\n"):
                text += eol
            new_text = (text + f"- [{stamp}] **{FACTORY_STALLED_KEY}**{resolved_part} "
                       f"[{FACTORY_STALLED_TAG}] — {message}{eol}")

        escalations_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = escalations_path.with_name(escalations_path.name + ".tmp")
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(tmp, escalations_path)
    except (OSError, ValueError) as e:
        print(f"ESCALATION write failed: {e}")


_GENERIC_ESCALATION_LINE_RE_CACHE: dict[str, re.Pattern] = {}


def _write_generic_singleton_escalation(escalations_path: Path, key: str, tag: str,
                                        message: str, now: datetime.datetime,
                                        resolved: bool = False) -> None:
    """Singleton-эскалация ОБЩЕГО вида (Д п.6: `[factory:fallback-broken]`)
    — тот же приём, что `_write_singleton_escalation`/`heartbeat_wrap.
    _write_singleton_escalation`, но `key`/`tag` параметризованы (не только
    `FACTORY-STALLED`).

    Н2 (критик v8.1): `resolved` добавлен, потому что без него
    `FACTORY-USAGE-LIMIT` не гасился НИКОГДА — состояние самоизлечивается за
    часы (сброс лимита), а строка «активный варнинг, требующий человека»
    оставалась навсегда и попадала в сверку чека 3 session-handoff. Момент
    снятия механизму известен точно, гасить есть чем. Маркер — тот же
    приём, что у `FACTORY-STALLED`. Non-throwing (BL-4)."""
    try:
        line_re = _GENERIC_ESCALATION_LINE_RE_CACHE.get(key + "|" + tag)
        if line_re is None:
            line_re = re.compile(
                r"(?m)^- \[(?P<ts>[^\]]+)\] \*\*" + re.escape(key) +
                r"\*\*(?:\s*\[resolved:[^\]]*\])?\s*\[" + re.escape(tag) +
                r"\] — [^\r\n]*")
            _GENERIC_ESCALATION_LINE_RE_CACHE[key + "|" + tag] = line_re
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        resolved_part = f" {GENERIC_RESOLVED_MARKER}" if resolved else ""
        text = escalations_path.read_bytes().decode("utf-8") if escalations_path.exists() else ""
        eol = "\r\n" if "\r\n" in text else "\n"

        m = line_re.search(text)
        if m:
            new_line = (f"- [{m.group('ts')}] **{key}**{resolved_part} "
                        f"[{tag}] — {message}")
            new_text = text[:m.start()] + new_line + text[m.end():]
        else:
            if not text:
                text = ll.ESCALATIONS_HEADER
            elif not text.endswith("\n"):
                text += eol
            new_text = (text + f"- [{stamp}] **{key}**{resolved_part} "
                        f"[{tag}] — {message}{eol}")

        escalations_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = escalations_path.with_name(escalations_path.name + ".tmp")
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(tmp, escalations_path)
    except (OSError, ValueError) as e:
        print(f"ESCALATION write failed: {e}")


def _write_state(state_file: Path, data: dict) -> None:
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_file.with_name(state_file.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, state_file)
    except OSError as e:
        print(f"STATE write failed: {e}")


# --------------------------------------------------------------------------
# WinRT-тост
# --------------------------------------------------------------------------

def _ps_escape(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def show_toast(title: str, message: str, *, powershell: str = POWERSHELL,
              timeout: float = 15.0) -> tuple[bool, str]:
    """WinRT-тост через Windows PowerShell 5.1. НИКОГДА не бросает
    исключение наружу — отказ тоста НЕ должен ронять сторож."""
    script = (
        f"$AppId = '{_TOAST_APP_ID}';"
        "try {"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null;"
        "$xmlText = '<toast><visual><binding template=\"ToastGeneric\"><text>' + "
        f"[System.Security.SecurityElement]::Escape({_ps_escape(title)}) + "
        "'</text><text>' + "
        f"[System.Security.SecurityElement]::Escape({_ps_escape(message)}) + "
        "'</text></binding></visual></toast>';"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$xml.LoadXml($xmlText);"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier"
        "($AppId).Show($toast);"
        "Write-Output 'TOAST_OK'"
        "} catch {"
        "Write-Output ('TOAST_FAIL: ' + $_.Exception.Message);"
        "exit 1"
        "}"
    )
    try:
        proc = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"toast вызов не удался: {e}"
    out = (proc.stdout or "").strip()
    if proc.returncode == 0 and "TOAST_OK" in out:
        return True, out
    return False, out or f"rc={proc.returncode}"


# --------------------------------------------------------------------------
# Д1 ночной резерв — вспомогательные функции
# --------------------------------------------------------------------------

def _coerce_mode_int(value, *, default) -> tuple:
    """Защищённый читатель числовых полей mode-файла (Б3, критик-раунд
    Д1 rework attempt 2, класс BL-4): `value is None` -> `(default,
    False)` — легитимное отсутствие поля/безлимит (`budget_total: null`),
    НЕ ошибка. Иначе — `int(value)`: ловит И настоящие `int`, И
    числовые СТРОКИ (`"0"`, `"20"` — оператор мог вписать число в
    кавычках при ручной правке mode-файла) -> `(int(value), False)`.
    Нечисловое значение (нечисловая строка/список/dict/bool — `bool`
    ЯВНО исключён, хоть и подкласс `int` в Python, здесь это НЕ число
    мод-файла) -> `(default, True)` — **corrupt: НЕ молчаливый 0**
    (прежний идиом `value or default` совмещал ДВЕ разные вещи: "поля
    нет" И "значение труcи, напр. пустая строка/0" — а строка `"0"`,
    будучи truthy, вообще НЕ давала default сработать, оставляя мусорный
    `str` в дальнейшей арифметике, откуда `TypeError` наружу вызывающего
    — критик-сценарий passes_done='0' глушил CAS/two_empty). Вызывающий
    ОБЯЗАН завести notes-строку при `corrupt=True` — оператор должен
    увидеть, что скилл/ручная правка записали мусор, не молчать."""
    if value is None:
        return default, False
    if isinstance(value, bool):
        return default, True
    try:
        return int(value), False
    except (TypeError, ValueError):
        return default, True


FALLBACK_RUNS_24H_HOURS = 24.0


def _bump_fallback_telemetry(state_file: Path, now: datetime.datetime, delta: int) -> None:
    """Н1 (Lead-решение, критик-раунд Д1): атомарный инкремент/откат
    `fallback_runs` (счётчик за эпизод) + `fallback_runs_24h`
    (скользящее 24ч-окно, СВОЙ список ts `fallback_runs_24h_ts`) — В
    STATE-ФАЙЛЕ, ДО Popen (вызывается из `on_spawn`, delta=+1) и на
    компенсирующем откате `spawn_failed` (delta=-1, из `on_spawn`'s
    undo-callable). Non-throwing (BL-4) — телеметрия НЕ гейт (архив v5,
    слово оператора: FALLBACK_MAX_RUNS как ограничитель работы удалён),
    отказ записи не должен ронять проход."""
    try:
        data, _exists, _corrupt = _read_json_or_none(state_file)
        if data is None:
            data = {}
        window = [ts for ts in (data.get("fallback_runs_24h_ts") or [])
                 if isinstance(ts, str) and _parse_ts(ts) is not None
                 and (now - _parse_ts(ts)).total_seconds() < FALLBACK_RUNS_24H_HOURS * 3600]
        if delta > 0:
            window.append(_fmt_ts(now))
        elif delta < 0 and window:
            window.pop()
        prev_runs, _corrupt2 = _coerce_mode_int(data.get("fallback_runs"), default=0)
        data["fallback_runs"] = max(0, prev_runs + delta)
        data["fallback_runs_24h_ts"] = window
        data["fallback_runs_24h"] = len(window)
        _write_state(state_file, data)
    except Exception as e:                    # non-throwing (BL-4)
        print(f"FALLBACK telemetry state-write failed (non-throwing): {e}")


def _series_blocked(count: int, last_ts: datetime.datetime | None,
                    now: datetime.datetime, threshold: int, probe_hours: float) -> bool:
    """count>=threshold И (now-last_ts) <= probe_hours -> заблокировано;
    last_ts отсутствует ИЛИ СТРОГО старше probe_hours -> НЕ заблокировано
    (пробный запуск разрешён несмотря на count — Д п.6). Граница M6: РОВНО
    probe_hours ещё блокирована (симметрично STALL_IN_PASS/TOAST_COOLDOWN
    — «на границе» = старое поведение держится, «за границей» = новое)."""
    if count < threshold:
        return False
    if last_ts is None:
        return False
    age_h = (now - last_ts).total_seconds() / 3600.0
    return age_h <= probe_hours


def _read_last_pass_summary(path: Path) -> dict | None:
    """None = файла нет/нечитаем/не dict — «неизвестно» на вызывающей
    стороне (канал сломан ≠ пусто)."""
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _classify_pass_summary(data: dict | None, pass_started: datetime.datetime) -> str:
    """"empty"|"nonempty"|"unknown". Свежесть: `ts` ОБЯЗАН быть >=
    `pass_started` (написан скриптом ВНУТРИ этого прохода, не протух от
    прошлого) — протухший/битый/отсутствующий ts = "unknown", НЕ "пусто"
    (Б5 r5/канал пустоты — иначе отказ канала молча снял бы two_empty-
    терминатор unlimited-резерва)."""
    if data is None:
        return "unknown"
    ts = _parse_ts(data.get("ts"))
    if ts is None or ts < pass_started:
        return "unknown"
    try:
        triggered = int(data.get("triggered"))
        deferred = int(data.get("deferred"))
        rescan_delta = int(data.get("rescan_delta"))
    except (TypeError, ValueError):
        return "unknown"
    if triggered == 0 and deferred == 0 and rescan_delta == 0:
        return "empty"
    return "nonempty"


def _run_reserve_pass(*, lock_file: Path, reaps_path: Path, escalations_path: Path,
                      sla_path: Path, fastdeath_path: Path, pass_summary_path: Path,
                      mode_file: Path, target_nonce: str, current_empty_streak: int,
                      now: datetime.datetime, log_path: Path | None,
                      state_file: Path | None = None) -> dict:
    """Запускает ОДИН резервный проход и возвращает
    `{result: <run_fallback_pass-исход>, classification: str|None,
    cas_ok: bool|None, wrote_two_empty: bool, telemetry_delta: int}`.

    Guard two_empty (Д п.5, r6-фикс: ОДНА перечитка mode-файла, СОВПАДАЮЩАЯ
    с перечиткой CAS-инкремента, ДО собственной записи; инкремент
    `passes_done` и `mode=stopped/two_empty` — ОДНА запись, не две
    подряд): (а) nonce не менялся; (б) mode != stopped; (в) driver ==
    "watchdog-fallback" (любой пульс окна, включая BUSY-пульс, ставит
    `factory-skill` и ОТМЕНЯЕТ two_empty).

    Н1 (Lead-решение, критик-раунд Д1): `state_file` (опционален —
    `None` пропускает телеметрию без ошибки, тестовый смысл) — `on_spawn`
    пишет `fallback_runs`/`fallback_runs_24h` НАПРЯМУЮ в state-файл ДО
    Popen (`_bump_fallback_telemetry`, delta=+1); компенсирующий откат на
    `spawn_failed` — delta=-1. `telemetry_delta` в возврате остаётся
    (обратная совместимость слоя тестов), но АВТОРИТЕТНОЕ значение —
    сам state-файл, вызывающий (`run_tick`) перечитывает его после
    возврата."""
    telemetry_box = {"delta": 0}
    result_box = {"classification": None, "cas_ok": None, "wrote_two_empty": False}

    def _on_spawn():
        telemetry_box["delta"] += 1
        if state_file is not None:
            _bump_fallback_telemetry(state_file, now, +1)

        def _undo():
            telemetry_box["delta"] -= 1
            if state_file is not None:
                _bump_fallback_telemetry(state_file, now, -1)
        return _undo

    def _on_pass_done(rc, runtime):
        # Б3 (критик-раунд Д1, rework attempt 2): ВЕСЬ корпус — ПОД
        # blanket except (class BL-4). on_pass_done вызывается ГЛУБОКО
        # внутри _run_child, ПОКА лок ещё держится, ДО release в его
        # finally; необработанное исключение здесь не сиротит лок само по
        # себе (_run_child ловит Exception вокруг всей секции wait()), но
        # искажает outcome/child_rc наружу (child_rc уже проставлен,
        # wait_exception тоже — смешанное, вводящее в заблуждение
        # состояние) — явный try/except здесь даёт ЧЕСТНУЮ диагностику и
        # предсказуемый non-throwing возврат (None = «CAS не применился»).
        try:
            summary = _read_last_pass_summary(pass_summary_path)
            classification = _classify_pass_summary(summary, now)
            result_box["classification"] = classification

            if not mode_file.exists():
                result_box["cas_ok"] = False
                return None
            try:
                raw = json.loads(mode_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                result_box["cas_ok"] = False
                return None
            if not isinstance(raw, dict):
                result_box["cas_ok"] = False
                return None

            if raw.get("session_nonce") != target_nonce or raw.get("mode") == MODE_STOPPED:
                result_box["cas_ok"] = False
                return None
            result_box["cas_ok"] = True

            # Б3: защищённое int-приведение (класс BL-4) — нечисловой
            # passes_done ("abc", список, ...) НЕ глушится молча в 0 через
            # прежний идиом `value or 0` (который к тому же ЛОМАЛСЯ на
            # ЧИСЛОВОЙ строке "0" — truthy, `or` не срабатывал, мусорный
            # str утекал в арифметику `+1` -> TypeError наружу). Числовая
            # строка ("0", "20") коэрцируется корректно int()'ом.
            passes_done_raw, passes_done_corrupt = _coerce_mode_int(
                raw.get("passes_done"), default=0)
            if passes_done_corrupt:
                print(f"FALLBACK on_pass_done: mode-файл несёт нечисловой "
                      f"passes_done={raw.get('passes_done')!r} — трактован как 0 "
                      "(corrupt-mode, оператор должен увидеть мусор), инкремент "
                      "всё равно применяется от 0 (CAS не блокируется этим)")

            driver_before = raw.get("driver")
            prospective_streak = (current_empty_streak + 1) if classification == "empty" else 0
            write_two_empty = (classification == "empty"
                              and prospective_streak >= EMPTY_STREAK_STOP
                              and driver_before == "watchdog-fallback")
            result_box["wrote_two_empty"] = write_two_empty

            write_ts = _fmt_ts(_utcnow())
            updated = dict(raw)
            updated["passes_done"] = passes_done_raw + 1
            updated["updated_ts"] = write_ts
            updated["driver"] = "watchdog-fallback"
            updated["last_fallback_ts"] = write_ts
            updated["heartbeat_note"] = f"резервный проход {updated['passes_done']}"
            if write_two_empty:
                updated["mode"] = MODE_STOPPED
                updated["stopped_reason"] = "two_empty"

            try:
                tmp = mode_file.with_name(mode_file.name + ".tmp")
                tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2),
                               encoding="utf-8")
                os.replace(tmp, mode_file)
            except OSError as e:
                print(f"FALLBACK mode-write failed: {e}")
                return None
            return updated
        except Exception as e:              # blanket non-throwing (BL-4, Б3)
            print(f"FALLBACK on_pass_done unexpected error (non-throwing, BL-4): {e}")
            return None

    result = hw.run_fallback_pass(
        on_spawn=_on_spawn, on_pass_done=_on_pass_done,
        lock_file=lock_file, reaps_path=reaps_path, escalations_path=escalations_path,
        sla_path=sla_path, fastdeath_path=fastdeath_path, log_path=log_path, now=now)

    return {
        "result": result,
        "classification": result_box["classification"],
        "cas_ok": result_box["cas_ok"],
        "wrote_two_empty": result_box["wrote_two_empty"],
        "telemetry_delta": telemetry_box["delta"],
    }


# --------------------------------------------------------------------------
# основной тик
# --------------------------------------------------------------------------

def run_tick(*, lock_file: Path = DEFAULT_LOCK_FILE,
            mode_file: Path = DEFAULT_MODE_FILE,
            state_file: Path = DEFAULT_STATE_FILE,
            sla_file: Path = DEFAULT_SLA_FILE,
            escalations_file: Path = DEFAULT_ESCALATIONS_FILE,
            orchestrator_log: Path = DEFAULT_ORCHESTRATOR_LOG,
            pass_summary_file: Path = DEFAULT_PASS_SUMMARY_FILE,
            fastdeath_file: Path = DEFAULT_FASTDEATH_FILE,
            fallback_log_path: Path | None = None,
            now: datetime.datetime | None = None,
            stall_no_lock_min: float | None = None,
            stall_inpass_min: float | None = None,
            cooldown_hours: float = TOAST_COOLDOWN_HOURS_DEFAULT,
            fallback_delay_min: float | None = None,
            fallback_block_threshold: int | None = None,
            limit_grace_min: float | None = None,
            toast_fn=show_toast,
            reserve_runner=_run_reserve_pass) -> int:
    """Один тик сторожа. Возвращает 0 ВСЕГДА."""
    lock_file, mode_file, state_file = Path(lock_file), Path(mode_file), Path(state_file)
    sla_file, escalations_file = Path(sla_file), Path(escalations_file)
    orchestrator_log = Path(orchestrator_log)
    pass_summary_file, fastdeath_file = Path(pass_summary_file), Path(fastdeath_file)

    now = now or _utcnow()
    stall_no_lock_min = (STALL_NO_LOCK_MIN_DEFAULT if stall_no_lock_min is None
                         else stall_no_lock_min)
    stall_inpass_min = (STALL_IN_PASS_MIN_DEFAULT if stall_inpass_min is None
                        else stall_inpass_min)
    fallback_delay_min = (FALLBACK_DELAY_MIN_DEFAULT if fallback_delay_min is None
                          else fallback_delay_min)
    fallback_block_threshold = (FALLBACK_BLOCK_THRESHOLD_DEFAULT
                                if fallback_block_threshold is None else fallback_block_threshold)
    limit_grace_min = (LIMIT_GRACE_MIN_DEFAULT if limit_grace_min is None
                       else limit_grace_min)
    ttl_hours = sla_utils.load_loop_lock_ttl_hours(sla_file)

    # --- п.0: классификация битости трёх файлов, накопитель notes -------
    notes_now: list[str] = []

    lock_snap = _lock_snapshot(lock_file)
    if lock_snap["exists"] and lock_snap["corrupt"]:
        notes_now.append(
            f"{_rel_path(lock_file)}: нечитаем/без валидного ts — трактован как "
            "сирота-кандидат (К3 п.0)")

    mode_data, mode_exists, mode_corrupt = _read_json_or_none(mode_file)
    if mode_corrupt:
        notes_now.append(f"{_rel_path(mode_file)}: нечитаем — трактован как «файла нет» (К3 п.0)")
    mode_missing = (not mode_exists) or mode_corrupt

    watchdog_data, watchdog_exists, watchdog_corrupt = _read_json_or_none(state_file)
    if watchdog_corrupt:
        notes_now.append(f"{_rel_path(state_file)}: нечитаем — bootstrap (К3 п.0)")
    bootstrap = (not watchdog_exists) or watchdog_corrupt

    mode_snap = _mode_snapshot(None if mode_missing else mode_data)

    # --- bootstrap: записать снапшоты, last_progress_ts=now, тихий exit -
    if bootstrap:
        if notes_now:
            _append_orchestrator_line(orchestrator_log, _rel_path(state_file),
                                      "notes: " + "; ".join(notes_now), now)
        _write_state(state_file, {
            "last_lock_snapshot": lock_snap,
            "last_mode_snapshot": mode_snap,
            "last_progress_ts": _fmt_ts(now),
            "last_alert_ts": None,
            "last_state": "ok",
            "notes": notes_now,
            "stalled_since": None,
            "empty_streak": 0,
            "slowdeath_streak": 0,
            "slowdeath_last_ts": None,
            "slowdeath_stopped": False,
            "unknown_streak": 0,
            "last_fallback_ts": None,
            "last_fallback_toast_ts": None,
            "last_fastdeath_toast_ts": None,
            "last_slowdeath_toast_ts": None,
            "fallback_runs": 0,
            "fallback_runs_24h": 0,
            "fallback_runs_24h_ts": [],
            "self_write_snapshot": None,
            "fallback_holder": None,
            "usage_limit_until": None,
            "usage_limit_raw": None,
            "usage_limit_toast_ts": None,
            "usage_limit_grace_until": None,
        })
        return 0

    prev_lock_snap = watchdog_data.get("last_lock_snapshot") or {}
    prev_mode_snap = watchdog_data.get("last_mode_snapshot") or {}
    prev_progress_ts = _parse_ts(watchdog_data.get("last_progress_ts"))
    prev_alert_ts = _parse_ts(watchdog_data.get("last_alert_ts"))
    prev_state_label = watchdog_data.get("last_state") or "ok"
    raw_notes = watchdog_data.get("notes")
    prev_notes = [str(n) for n in raw_notes] if isinstance(raw_notes, list) else []

    prev_stalled_since = _parse_ts(watchdog_data.get("stalled_since"))
    empty_streak = int(watchdog_data.get("empty_streak") or 0)
    slowdeath_streak = int(watchdog_data.get("slowdeath_streak") or 0)
    slowdeath_last_ts = _parse_ts(watchdog_data.get("slowdeath_last_ts"))
    slowdeath_stopped = bool(watchdog_data.get("slowdeath_stopped") or False)
    unknown_streak = int(watchdog_data.get("unknown_streak") or 0)
    last_fallback_ts = _parse_ts(watchdog_data.get("last_fallback_ts"))
    last_fallback_toast_ts = _parse_ts(watchdog_data.get("last_fallback_toast_ts"))
    last_fastdeath_toast_ts = _parse_ts(watchdog_data.get("last_fastdeath_toast_ts"))
    last_slowdeath_toast_ts = _parse_ts(watchdog_data.get("last_slowdeath_toast_ts"))
    fallback_runs = int(watchdog_data.get("fallback_runs") or 0)
    fallback_runs_24h = int(watchdog_data.get("fallback_runs_24h") or 0)
    fallback_runs_24h_ts = watchdog_data.get("fallback_runs_24h_ts") or []
    self_write_snapshot = watchdog_data.get("self_write_snapshot")
    fallback_holder = watchdog_data.get("fallback_holder")
    usage_limit_until = _parse_ts(watchdog_data.get("usage_limit_until"))
    usage_limit_raw = watchdog_data.get("usage_limit_raw")
    usage_limit_toast_ts = _parse_ts(watchdog_data.get("usage_limit_toast_ts"))
    usage_limit_grace_until = _parse_ts(watchdog_data.get("usage_limit_grace_until"))

    changed = (lock_snap != prev_lock_snap) or (mode_snap != prev_mode_snap)
    progress_ts = now if (changed or prev_progress_ts is None) else prev_progress_ts

    # --- ветки 1-3 (К3, v6, БЕЗ ИЗМЕНЕНИЙ) ---------------------------------
    mode_active_alarm = False       # branch 3 (mode активный) — единственная ветка, триггерящая резерв
    if mode_missing:
        alarm = False
        detail = "mode-файла нет/нечитаем — тишина (ручной проход без вождения штатен)"
    elif mode_data.get("mode") == MODE_STOPPED:
        if _lock_present(lock_snap) and _lock_stale_for_orphan(lock_snap, now, ttl_hours):
            alarm = True
            detail = (f"mode=stopped, лок без вождения: holder={lock_snap.get('holder')!r} "
                      f"— возраст лока > TTL {ttl_hours}ч (сирота-кандидат)")
        else:
            alarm = False
            detail = "mode=stopped — тишина"
    else:
        lock_here = _lock_present(lock_snap)
        threshold_min = stall_inpass_min if lock_here else stall_no_lock_min
        silence_min = (now - progress_ts).total_seconds() / 60.0
        alarm = silence_min > threshold_min
        mode_active_alarm = alarm
        detail = (f"mode активный ({mode_data.get('mode')!r}), лок "
                 f"{'есть' if lock_here else 'нет'}, тишина {silence_min:.1f} мин "
                 f"(порог {threshold_min:.0f} мин)")

    new_state_label = "stalled" if alarm else "ok"

    # --- Д п.4/п.6: закрытие эпизода (прогресс окна ИЛИ смена nonce) сбрасывает
    # ВСЕ стрики резерва (empty/slowdeath/unknown) + fastdeath-реестр другого
    # модуля — «результативный проход» ТОЖЕ сбрасывает (обрабатывается ниже,
    # ПОСЛЕ решения о резервном проходе, если он в этом тике случится).
    episode_closed_by_window = (not mode_active_alarm) and (prev_stalled_since is not None)
    if episode_closed_by_window:
        # v8: живой прогресс окна закрывает и лимитное окно — кто-то (чаще
        # всего оператор по возвратному тосту) фабрику толкнул, ждать
        # больше нечего. Иначе протухший `usage_limit_until` глушил бы
        # резерв уже после того, как всё поехало.
        usage_limit_until = None
        usage_limit_raw = None
        usage_limit_grace_until = None
        empty_streak = 0
        slowdeath_streak = 0
        slowdeath_last_ts = None
        slowdeath_stopped = False
        unknown_streak = 0
        try:
            fd = hw._read_fastdeath(fastdeath_file)
            if fd.get("count"):
                hw._write_fastdeath(fastdeath_file, {"count": 0, "first_ts": None,
                                                     "last_ts": None, "last_rc": None})
        except Exception as e:                 # non-throwing (BL-4)
            print(f"FASTDEATH reset-on-window-progress failed: {e}")

    if mode_active_alarm:
        stalled_since = prev_stalled_since if prev_stalled_since is not None else now
    else:
        stalled_since = None

    # --- Д1: ночной резерв — СТРОГО внутри ветки «mode активный, STALLED» -
    reserve_outcome = None
    night_fallback_notes: list[str] = []
    if mode_active_alarm and stalled_since is not None:
        elapsed_min = (now - stalled_since).total_seconds() / 60.0
        night_fallback_value = str(mode_data.get("night_fallback") or
                                   MODE_ACTIVE_DEFAULT_NIGHT_FALLBACK).lower()
        # Б3 (критик-раунд Д1): защищённое int-приведение budget_total/
        # passes_done (класс BL-4) — прежний `mode_data.get(...) or 0`
        # либо молча искажал ЛЕГИТИМНЫЕ числовые СТРОКИ ("20" в кавычках,
        # оператор мог так вписать вручную), либо ронял тик TypeError'ом
        # на сравнении `int < str` (некоэрцированный budget_total).
        # Нечисловой мусор (НЕ None, НЕ коэрцируемый) — corrupt-mode:
        # резерв консервативно НЕ стартует (не рискуем прогнать мимо
        # непрочитанного лимита), notes ЯВНО называют мусор оператору.
        budget_total, budget_total_corrupt = _coerce_mode_int(
            mode_data.get("budget_total"), default=None)
        passes_done_current, passes_done_corrupt = _coerce_mode_int(
            mode_data.get("passes_done"), default=0)
        mode_numeric_corrupt = budget_total_corrupt or passes_done_corrupt
        budget_ok = (not mode_numeric_corrupt
                    and ((budget_total is None) or (passes_done_current < budget_total)))

        # --- v8: лимитное окно — САМЫЙ ВЕРХНИЙ гейт --------------------
        # Стоит выше night_fallback/бюджета/поломочных серий намеренно:
        # это не «нельзя запускать по политике», а «запуск физически не
        # доедет». Возвратный тост тоже здесь — он нужен ровно тогда,
        # когда окно мертво (иначе будить оператора незачем).
        limit_active = (usage_limit_until is not None and now < usage_limit_until)
        limit_return_lag_h = (
            (now - usage_limit_until).total_seconds() / 3600.0
            if (usage_limit_until is not None and not limit_active) else None)
        if (limit_return_lag_h is not None
                and limit_return_lag_h > LIMIT_RETURN_TOAST_MAX_LAG_H):
            # протухшее окно (сброс наступил, пока фабрика стояла) —
            # гасим МОЛЧА, без тоста и без grace
            night_fallback_notes.append(
                f"[{FACTORY_LIMIT_BACK_TAG}] лимитное окно протухло (сброс "
                f"{_fmt_ts(usage_limit_until)}, давность "
                f"{limit_return_lag_h:.1f}ч) — снято молча")
            _write_generic_singleton_escalation(
                escalations_file, FACTORY_LIMIT_KEY, FACTORY_LIMIT_TAG,
                f"лимитное окно снято {_fmt_ts(now)} (протухло: сброс был "
                f"{_fmt_ts(usage_limit_until)}, давность {limit_return_lag_h:.1f}ч). "
                "Человеку делать нечего.", now, resolved=True)
            usage_limit_until = None
            usage_limit_raw = None
            usage_limit_toast_ts = None
        elif (usage_limit_until is not None and not limit_active
                and usage_limit_grace_until is None):
            # момент сброса наступил — РОВНО ОДИН возвратный тост, дальше
            # grace-окно приоритета живого окна над резервом
            usage_limit_grace_until = now + datetime.timedelta(minutes=limit_grace_min)
            shown, _detail = toast_fn(
                "[factory:limit-back]",
                f"лимиты вернулись — толкни окно (/factory). Резерв ждёт "
                f"{limit_grace_min:.0f} мин, потом поедет сам")
            # Б3 (критик v8.1): тег печатается ЛИТЕРАЛОМ. Прежний детектор
            # F-11(в) грепал `[factory:limit-back]` по orchestrator-log, где
            # этой строки не было никогда (счётный греп критика с позитивным
            # контролем: `factory:stalled` = 0 при `stalled` = 12) — то есть
            # механизм был без работающего детектора, ровно «пожелание».
            _append_orchestrator_line(
                orchestrator_log, _rel_path(state_file),
                f"[{FACTORY_LIMIT_BACK_TAG}] сброс наступил "
                f"({_fmt_ts(usage_limit_until)}), возвратный тост "
                f"{'показан' if shown else 'НЕ показан'}, резерв придержан до "
                f"{_fmt_ts(usage_limit_grace_until)}", now)
            _write_generic_singleton_escalation(
                escalations_file, FACTORY_LIMIT_KEY, FACTORY_LIMIT_TAG,
                f"лимиты вернулись {_fmt_ts(now)} (сброс "
                f"{_fmt_ts(usage_limit_until)}); окно требует ручного толчка, "
                f"резерв поедет сам после {_fmt_ts(usage_limit_grace_until)}",
                now, resolved=True)
            usage_limit_until = None
            usage_limit_raw = None
            usage_limit_toast_ts = None

        grace_active = (usage_limit_grace_until is not None
                       and now < usage_limit_grace_until)
        if grace_active:
            night_fallback_notes.append(
                f"лимиты вернулись — приоритет живому окну, резерв придержан до "
                f"{_fmt_ts(usage_limit_grace_until)}")
        elif usage_limit_grace_until is not None:
            usage_limit_grace_until = None       # grace истёк — прежние правила

        if limit_active:
            limit_reason = usage_limit_raw or "причина в logs/fallback-*.log"
            night_fallback_notes.append(
                f"лимиты подписки исчерпаны ({limit_reason}) — резерв спит до "
                f"{_fmt_ts(usage_limit_until)}, тревоги подавлены")
        elif grace_active:
            pass                                  # нота уже добавлена выше
        elif night_fallback_value == "off":
            night_fallback_notes.append("резерв выключен (night_fallback=off)")
        elif mode_numeric_corrupt:
            night_fallback_notes.append(
                "резерв не стартует: mode-файл несёт нечисловые budget_total/"
                f"passes_done (budget_total={mode_data.get('budget_total')!r}, "
                f"passes_done={mode_data.get('passes_done')!r}) — corrupt-mode, "
                "оператор чинит файл")
        elif not budget_ok:
            night_fallback_notes.append(
                f"резерв не стартует: бюджет доехал (passes_done={passes_done_current} "
                f">= budget_total={budget_total})")
        elif elapsed_min >= fallback_delay_min:
            fd = hw._read_fastdeath(fastdeath_file)
            fastdeath_count = int(fd.get("count") or 0)
            fastdeath_last_ts = _parse_ts(fd.get("last_ts"))
            fastdeath_blocked = _series_blocked(
                fastdeath_count, fastdeath_last_ts, now, fallback_block_threshold,
                FALLBACK_BLOCK_PROBE_HOURS)
            slowdeath_blocked = _series_blocked(
                slowdeath_streak, slowdeath_last_ts, now, fallback_block_threshold,
                FALLBACK_BLOCK_PROBE_HOURS)

            if fastdeath_blocked:
                night_fallback_notes.append(
                    f"резерв заблокирован: fastdeath-серия ({fastdeath_count}) — "
                    "см. logs/fallback-*.log")
            elif slowdeath_blocked:
                night_fallback_notes.append(
                    f"резерв заблокирован: slowdeath-серия ({slowdeath_streak}) — "
                    "см. logs/fallback-*.log")
            else:
                target_nonce = mode_data.get("session_nonce")
                log_path = fallback_log_path or hw.fallback_log_path(now)
                _write_state(state_file, {
                    "last_lock_snapshot": lock_snap, "last_mode_snapshot": mode_snap,
                    "last_progress_ts": _fmt_ts(progress_ts), "last_alert_ts": _fmt_ts(prev_alert_ts),
                    "last_state": new_state_label, "notes": notes_now,
                    "stalled_since": _fmt_ts(stalled_since), "empty_streak": empty_streak,
                    "slowdeath_streak": slowdeath_streak, "slowdeath_last_ts": _fmt_ts(slowdeath_last_ts),
                    "slowdeath_stopped": slowdeath_stopped, "unknown_streak": unknown_streak,
                    "last_fallback_ts": _fmt_ts(last_fallback_ts),
                    "last_fallback_toast_ts": _fmt_ts(last_fallback_toast_ts),
                    "last_fastdeath_toast_ts": _fmt_ts(last_fastdeath_toast_ts),
                    "last_slowdeath_toast_ts": _fmt_ts(last_slowdeath_toast_ts),
                    "fallback_runs": fallback_runs, "fallback_runs_24h": fallback_runs_24h,
                    "fallback_runs_24h_ts": fallback_runs_24h_ts,
                    "self_write_snapshot": self_write_snapshot,
                    "fallback_holder": fallback_holder,
                    "usage_limit_until": _fmt_ts(usage_limit_until),
                    "usage_limit_raw": usage_limit_raw,
                    "usage_limit_toast_ts": _fmt_ts(usage_limit_toast_ts),
                    "usage_limit_grace_until": _fmt_ts(usage_limit_grace_until),
                })   # Д п.1: state-файл пишется ДО спавна (чек 3б не дрейфует на длинном тике)

                reserve_outcome = reserve_runner(
                    lock_file=lock_file, reaps_path=lock_file.with_name("loop-lock-reaps.json"),
                    escalations_path=escalations_file, sla_path=sla_file,
                    fastdeath_path=fastdeath_file, pass_summary_path=pass_summary_file,
                    mode_file=mode_file, target_nonce=target_nonce,
                    current_empty_streak=empty_streak, now=now, log_path=log_path,
                    state_file=state_file)
                last_fallback_ts = now

                # Н1 (Lead-решение): АВТОРИТЕТНОЕ значение fallback_runs/24h —
                # сам state-файл (реальный `on_spawn` внутри `_run_reserve_pass`
                # пишет его туда ДО Popen, `_bump_fallback_telemetry`);
                # перечитываем ПОСЛЕ возврата. Фолбэк на `telemetry_delta` —
                # ТОЛЬКО если файл почему-то не отражает изменение (напр.
                # тестовый reserve_runner, не пишущий state сам, класс
                # обратной совместимости слоя тестов).
                post_data, _pe, _pc = _read_json_or_none(state_file)
                if post_data is not None and post_data.get("fallback_runs") != fallback_runs:
                    fallback_runs, _ = _coerce_mode_int(post_data.get("fallback_runs"),
                                                        default=fallback_runs)
                    fallback_runs_24h, _ = _coerce_mode_int(post_data.get("fallback_runs_24h"),
                                                            default=fallback_runs_24h)
                    fallback_runs_24h_ts = post_data.get("fallback_runs_24h_ts") or fallback_runs_24h_ts
                else:
                    fallback_runs += reserve_outcome["telemetry_delta"]

                rr = reserve_outcome["result"]
                self_write_snapshot = rr.get("mode_write")
                fallback_holder = rr.get("holder")

                # --- v8: ребёнок умер от лимита подписки ----------------
                # heartbeat_wrap уже откатил свой fastdeath-инкремент; здесь
                # заводим окно сна и даём РОВНО ОДИН тост-объяснение. Ни
                # [factory:fallback], ни [factory:child-death], ни
                # [factory:stalled] в этом окне больше не звучат.
                detected_limit = rr.get("usage_limit")
                if detected_limit:
                    reset_ts = detected_limit.get("reset_ts")
                    if reset_ts is None:
                        reset_ts = now + datetime.timedelta(
                            hours=hw.USAGE_LIMIT_DEFAULT_SLEEP_H)
                        reset_txt = (f"{_fmt_ts(reset_ts)} (время сброса не "
                                    f"распознано: {detected_limit.get('note')})")
                    else:
                        reset_txt = _fmt_ts(reset_ts)
                    usage_limit_until = reset_ts
                    usage_limit_raw = detected_limit.get("raw")
                    usage_limit_grace_until = None
                    night_fallback_notes.append(
                        f"[{FACTORY_LIMIT_TAG}] резерв умер от лимита "
                        f"подписки ({usage_limit_raw}) — "
                        f"окно сна до {reset_txt}")
                    _write_generic_singleton_escalation(
                        escalations_file, FACTORY_LIMIT_KEY, FACTORY_LIMIT_TAG,
                        f"лимиты подписки исчерпаны ({usage_limit_raw}); резерв и "
                        f"тревоги молчат до {reset_txt}; окно-фабрика после сброса "
                        "требует РУЧНОГО толчка (цепочка ScheduleWakeup порвана "
                        "сорванным ходом — самовосстановления у окна нет)", now)
                    shown, _detail = toast_fn(
                        "[factory:usage-limit]",
                        f"лимиты подписки кончились — фабрика спит до "
                        f"{detected_limit.get('reset_hint') or reset_txt}")
                    if shown:
                        usage_limit_toast_ts = now

                outcome_kind = rr["outcome"]
                if outcome_kind == "spawned" and rr["child_rc"] == 0:
                    # результативный проход — сбрасывает ОБЕ поломочные серии
                    slowdeath_streak = 0
                    slowdeath_last_ts = None
                    slowdeath_stopped = False
                    classification = reserve_outcome["classification"]
                    if classification == "empty":
                        empty_streak = empty_streak + 1 if reserve_outcome["cas_ok"] else empty_streak
                        unknown_streak = 0
                    elif classification == "nonempty":
                        empty_streak = 0
                        unknown_streak = 0
                    else:                        # "unknown" — канал сломан, НЕ пусто
                        unknown_streak += 1
                        night_fallback_notes.append(
                            "канал last-pass-summary неизвестен (битый/протухший/отсутствует)")
                elif not detected_limit and (
                        outcome_kind == "timeout_kill" or (outcome_kind == "spawned"
                                                           and rr["child_rc"] not in (0, None)
                                                           and not rr["fast_death"])):
                    # v8: `not detected_limit` — ОБЯЗАТЕЛЕН. Смерть от лимита
                    # приходит сюда с fast_death=False (обёртка откатила свой
                    # инкремент), и без этого условия она копила бы
                    # slowdeath-серию, то есть ровно ту «поломку», от
                    # ложного объявления которой механизм и заводится.
                    slowdeath_streak += 1
                    slowdeath_last_ts = now
                    if slowdeath_streak >= fallback_block_threshold and not slowdeath_stopped:
                        slowdeath_stopped = True
                        night_fallback_notes.append(
                            f"{slowdeath_streak} медленных отказов резерва подряд — поломка, "
                            "см. logs/fallback-*.log")
                        _write_generic_singleton_escalation(
                            escalations_file, FALLBACK_BROKEN_KEY, FALLBACK_BROKEN_TAG,
                            f"{slowdeath_streak} медленных отказов резерва подряд, "
                            f"зафиксировано {_fmt_ts(now)}; см. logs/fallback-*.log", now)
                        toast_due = (last_slowdeath_toast_ts is None or
                                    (now - last_slowdeath_toast_ts).total_seconds() / 3600.0
                                    >= cooldown_hours)
                        if toast_due:
                            shown, _detail = toast_fn(
                                "[factory:fallback-broken]",
                                f"{slowdeath_streak} прохода подряд безрезультатны — "
                                "поломка, см. logs/fallback-*.log")
                            if shown:
                                last_slowdeath_toast_ts = now
                # fast_death (spawn_failed/быстрая смерть) — fastdeath уже учтён
                # общим ядром (state/heartbeat-fastdeath.json); slowdeath НЕ трогаем.

                if rr["fast_death"]:
                    fd_after = hw._read_fastdeath(fastdeath_file)
                    fd_count_after = int(fd_after.get("count") or 0)
                    if fd_count_after >= fallback_block_threshold:
                        night_fallback_notes.append(
                            f"{fd_count_after} быстрых смертей резерва подряд — см. "
                            "logs/fallback-*.log")
                        toast_due = (last_fastdeath_toast_ts is None or
                                    (now - last_fastdeath_toast_ts).total_seconds() / 3600.0
                                    >= cooldown_hours)
                        if toast_due:
                            shown, _detail = toast_fn(
                                "[factory:child-death]",
                                f"{fd_count_after} быстрых смертей резерва подряд — "
                                "см. logs/fallback-*.log")
                            if shown:
                                last_fastdeath_toast_ts = now

                if unknown_streak >= UNKNOWN_STREAK_TOAST:
                    night_fallback_notes.append("канал сводки прохода сломан")
                    toast_fn("[factory:fallback-channel]", "канал сводки прохода сломан")

                # Н3 (Lead-решение, критик-раунд Д1): тост запуска резерва —
                # ОДИН НА КАЖДЫЙ запуск (семантика спеки п.7 «один на
                # запуск» — это ПРО ЗАПУСК, не ПРО 4ч-окно наравне с
                # тревогой). Этот код-путь исполняется РОВНО ОДИН РАЗ за
                # триггернутый резервный проход (гейт выше уже гарантирует
                # ≤1 запуск/тик) — поэтому тост зовётся БЕЗУСЛОВНО, без
                # 4ч-кулдауна; `last_fallback_toast_ts` остаётся ТОЛЬКО как
                # диагностическая метка «когда был последний» (анти-
                # дребезг на случай будущего повторного вызова В ПРЕДЕЛАХ
                # ОДНОГО запуска — не расходует и не гейтит НИЧЕГО здесь).
                # v8: при распознанном лимите тост запуска НЕ звучит — про
                # этот запуск оператору уже сказано тостом [factory:usage-
                # limit], и сказано ПРИЧИНОЙ, а не «резервный проход
                # (spawned)».
                if not detected_limit:
                    shown, _detail = toast_fn(
                        "[factory:fallback]", f"окно молчит — резервный проход ({outcome_kind})")
                    if shown:
                        last_fallback_toast_ts = now

    notes_now.extend(night_fallback_notes)

    # --- ветка 4: транзиции (тревога) --------------------------------------
    # v8: `limit_quiet` глушит ТОЛЬКО тост. Запись в escalations.md и строку
    # orchestrator-log оставляем всегда — это след, а не оповещение: разбор
    # постфактум обязан видеть, что окно стояло.
    limit_quiet = ((usage_limit_until is not None and now < usage_limit_until)
                  or (usage_limit_grace_until is not None
                      and now < usage_limit_grace_until))
    if new_state_label == "stalled" and prev_state_label != "stalled":
        _write_singleton_escalation(
            escalations_file,
            f"{detail}; зафиксировано {_fmt_ts(now)}; вариант снятия лока — "
            "`python scripts/loop_lock.py release --force`",
            now)
        _append_orchestrator_line(orchestrator_log, _rel_path(mode_file),
                                  f"ok->stalled: {detail}", now)
        toast_due = (prev_alert_ts is None or
                    (now - prev_alert_ts).total_seconds() / 3600.0 >= cooldown_hours)
        if limit_quiet:
            notes_now.append("тревога STALLED подавлена: лимитное окно "
                            "(фабрика не может поехать — будить незачем)")
        elif toast_due:
            shown, toast_detail = toast_fn("[factory:stalled]", detail)
            if shown:
                prev_alert_ts = now
            else:
                notes_now.append(f"тост не показан: {toast_detail}")
                print(f"toast не показан: {toast_detail}")
    elif new_state_label == "ok" and prev_state_label == "stalled":
        _write_singleton_escalation(
            escalations_file, f"восстановлено {_fmt_ts(now)}", now, resolved=True)
        _append_orchestrator_line(orchestrator_log, _rel_path(mode_file),
                                  f"stalled->ok: восстановлено в {_fmt_ts(now)}", now)

    if notes_now != prev_notes:
        _append_orchestrator_line(
            orchestrator_log, _rel_path(state_file),
            ("notes: " + "; ".join(notes_now))
            if notes_now else ("notes: сняты (были: " + "; ".join(prev_notes) + ")"),
            now)

    # снимок КОНЦА тика (после резерва, если он бежал) — база для СЛЕДУЮЩЕГО
    # тика; last_progress_ts НЕ пересчитывается по нему (Д п.4 — атрибуция).
    end_lock_snap = _lock_snapshot(lock_file)
    end_mode_data, end_mode_exists, end_mode_corrupt = _read_json_or_none(mode_file)
    end_mode_snap = _mode_snapshot(None if ((not end_mode_exists) or end_mode_corrupt)
                                   else end_mode_data)

    _write_state(state_file, {
        "last_lock_snapshot": end_lock_snap,
        "last_mode_snapshot": end_mode_snap,
        "last_progress_ts": _fmt_ts(progress_ts),
        "last_alert_ts": _fmt_ts(prev_alert_ts),
        "last_state": new_state_label,
        "notes": notes_now,
        "stalled_since": _fmt_ts(stalled_since),
        "empty_streak": empty_streak,
        "slowdeath_streak": slowdeath_streak,
        "slowdeath_last_ts": _fmt_ts(slowdeath_last_ts),
        "slowdeath_stopped": slowdeath_stopped,
        "unknown_streak": unknown_streak,
        "last_fallback_ts": _fmt_ts(last_fallback_ts),
        "last_fallback_toast_ts": _fmt_ts(last_fallback_toast_ts),
        "last_fastdeath_toast_ts": _fmt_ts(last_fastdeath_toast_ts),
        "last_slowdeath_toast_ts": _fmt_ts(last_slowdeath_toast_ts),
        "fallback_runs": fallback_runs,
        "fallback_runs_24h": fallback_runs_24h,
        "fallback_runs_24h_ts": fallback_runs_24h_ts,
        "self_write_snapshot": self_write_snapshot,
        "fallback_holder": fallback_holder,
        "usage_limit_until": _fmt_ts(usage_limit_until),
        "usage_limit_raw": usage_limit_raw,
        "usage_limit_toast_ts": _fmt_ts(usage_limit_toast_ts),
        "usage_limit_grace_until": _fmt_ts(usage_limit_grace_until),
    })
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="factory_watchdog — сторож окна-фабрики + ночной резерв (spec-factory-window v7)")
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--mode-file", default=str(DEFAULT_MODE_FILE))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--sla-file", default=str(DEFAULT_SLA_FILE))
    parser.add_argument("--escalations-file", default=str(DEFAULT_ESCALATIONS_FILE))
    parser.add_argument("--orchestrator-log", default=str(DEFAULT_ORCHESTRATOR_LOG))
    parser.add_argument("--now", help="переопределить текущее время (ISO, тесты/смок)")
    parser.add_argument("--no-toast", action="store_true",
                        help="ТОЛЬКО для смок-прогонов/CLI-отладки на синтетических "
                             "фикстурах — подменяет show_toast заглушкой (permission-"
                             "hygiene: живой тост НЕ бьёт по реальному экрану оператора). "
                             "Тот же эффект даёт env AO3_FACTORY_NO_TOAST=1.")
    args = parser.parse_args(argv)

    now = _parse_ts(args.now) if args.now else None
    stall_no_lock_min = _env_float("AO3_FACTORY_STALL_MIN", STALL_NO_LOCK_MIN_DEFAULT)
    stall_inpass_min = _env_float("AO3_FACTORY_STALL_INPASS_MIN", STALL_IN_PASS_MIN_DEFAULT)
    fallback_delay_min = _env_float("AO3_FACTORY_FALLBACK_DELAY_MIN", FALLBACK_DELAY_MIN_DEFAULT)
    fallback_block_threshold = int(_env_float(
        "AO3_FACTORY_FALLBACK_BLOCK_THRESHOLD", FALLBACK_BLOCK_THRESHOLD_DEFAULT))
    limit_grace_min = _env_float("AO3_FACTORY_LIMIT_GRACE_MIN", LIMIT_GRACE_MIN_DEFAULT)
    no_toast = args.no_toast or os.environ.get("AO3_FACTORY_NO_TOAST") == "1"
    toast_fn = (lambda title, message: (False, "AO3_FACTORY_NO_TOAST/--no-toast: подавлен")
               ) if no_toast else show_toast

    try:
        return run_tick(
            lock_file=Path(args.lock_file), mode_file=Path(args.mode_file),
            state_file=Path(args.state_file), sla_file=Path(args.sla_file),
            escalations_file=Path(args.escalations_file),
            orchestrator_log=Path(args.orchestrator_log),
            now=now, stall_no_lock_min=stall_no_lock_min, stall_inpass_min=stall_inpass_min,
            fallback_delay_min=fallback_delay_min,
            fallback_block_threshold=fallback_block_threshold,
            limit_grace_min=limit_grace_min, toast_fn=toast_fn)
    except Exception as e:                    # non-throwing catch-all (спека К3)
        print(f"factory_watchdog: непойманная ошибка тика (не должна была случиться): {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
