"""factory_watchdog — сторож окна-фабрики (spec-factory-window v6 К3,
docs/tasks/factory-visible-window.md, 2026-08-16).

Архитектура «окно-фабрика + сторож» (слово оператора 2026-08-16):
`/qa-loop` больше не гоняется headless из Task Scheduler
(`scripts/heartbeat_wrap.py` — ДЕПРЕКИРОВАНО, см. его докстринг) — его
ведёт скилл `.claude/skills/factory/SKILL.md` из ОТКРЫТОГО окна Claude
Code. Этот модуль — ТОЛЬКО сторож: планировщик тикает его каждые PT30M
(`scripts/heartbeat.cmd`), он НЕ запускает `/qa-loop` сам, а проверяет
ДВА сигнала прогресса — `state/loop.lock` (проход идёт) и
`state/factory-mode.json` (окно ведёт кто-то, К1/К2 спеки) — и объявляет
тревогу (`[factory:stalled]`), если оба молчат дольше порога.

Состояние сторожа — `state/factory-watchdog.json` (gitignored):
`last_lock_snapshot`, `last_mode_snapshot`, `last_progress_ts`,
`last_alert_ts`, `last_state`, **`notes`** (критик-фикс Б-1,
2026-08-16: список строк ТЕКУЩИХ аномалий — битый mode/lock/
watchdog-state, непоказанный тост; ПЕРЕЗАПИСЫВАЕТСЯ целиком каждый
тик, не накапливается). Обновляется на КАЖДОМ тике, ВКЛЮЧАЯ тихие
ветки (mode нет/stopped) — это heartbeat САМОГО сторожа (детектор
фолбэка ридера задачи планировщика — doctor-чек `LastRunTime задачи <
2ч` + чек 3б session-handoff, НЕ этот state-файл — правка спеки
2026-08-16). Orchestrator-log получает строку про `notes` ТОЛЬКО когда
список реально изменился относительно прошлого тика (дедуп
бессрочного шума при устойчиво битом файле).

Прогресс = изменение `loop.lock` (появился/исчез/holder/ts, либо — для
НЕЧИТАЕМОГО лока — изменение сырых байт файла, см. `_lock_snapshot`)
ИЛИ изменение mode-файла (`mode`/`updated_ts`/`passes_done`)
относительно снапшотов ПРЕДЫДУЩЕГО тика; изменение -> `last_progress_ts
= now`. Bootstrap (снапшотов ещё нет — файл `state/factory-watchdog.json`
отсутствует ИЛИ нечитаем) — записать текущие снапшоты,
`last_progress_ts = now`, тихий exit 0, БЕЗ оценки тревоги.

**Матрица (приоритет сверху вниз, однозначно):**

0. Битые JSON-состояния (класс, все три файла сторожа) — интерпретация
   ПЕРЕД любой веткой 1-4, независимо от исхода:
   - `state/factory-mode.json` нечитаем -> трактуется КАК «файла нет»
     (ветка 1) + строка в orchestrator-log.
   - `state/loop.lock` нечитаем/без валидного `ts` -> **сирота-кандидат**
     (согласовано с семантикой `loop_lock.py`: REAPED/CORRUPT) — в ветке
     2 считается протухшим (СРАЗУ, без вычисления возраста); в
     вычислении прогресса — сравнение по сырым байтам файла (см.
     `_lock_snapshot`); для предиката ветки 3 битый лок = «лок есть»
     (используется порог STALL_IN_PASS, не STALL_NO_LOCK) — плюс строка
     в orchestrator-log.
   - `state/factory-watchdog.json` нечитаем -> bootstrap (как «снапшотов
     нет») + строка в orchestrator-log.
   Ни одна из трёх веток не роняет процесс — exit 0 всегда.
1. `state/factory-mode.json` НЕТ (или нечитаем, см. п.0) -> тишина
   (ручной `/qa-loop` без вождения — штатный carve-out), state-файл
   сторожа обновить, exit 0. Лок НЕ проверяется в этой ветке вовсе.
2. `mode == "stopped"` -> тишина, НО: лок ЕСТЬ И возраст САМОГО лока
   (`now - lock.ts`; `ts` фиксируется в `acquire` и не обновляется) >
   `loop_lock_ttl_hours` (4ч, `sla_utils.load_loop_lock_ttl_hours`) ->
   «лок без вождения» -> STALLED. Порог — возраст ЛОКА, НЕ
   `last_progress_ts` (пульса при `stopped` нет by construction).
3. `mode` активный (файл читается, `mode != "stopped"`):
   - лока нет И `now - last_progress_ts` > `STALL_NO_LOCK` (60 мин,
     `AO3_FACTORY_STALL_MIN`) -> STALLED;
   - лок есть И `now - last_progress_ts` > `STALL_IN_PASS` (90 мин,
     `AO3_FACTORY_STALL_INPASS_MIN`) -> STALLED.
4. Переход ok->stalled: тост (кулдаун `TOAST_COOLDOWN_HOURS` = 4ч на
   ЛЮБОЙ тост — если предыдущий тост младше кулдауна, тост
   ПРОПУСКАЕТСЯ, но эскалация/лог всё равно пишутся; отказ тоста —
   строка в `notes`, см. выше, п.4 не единственный писатель notes) +
   singleton-эскалация `[factory:stalled]` (**текст несёт ТЕКУЩИЙ ts** —
   при повторе singleton-механизм сохраняет исходный bracket-ts,
   поэтому свежесть видна только в теле сообщения) + строка
   orchestrator-log. stalled->ok: строка orchestrator-log + гашение
   эскалации маркером `[resolved:factory-watchdog-recovered]` —
   **СРАЗУ после `**KEY**`, ДО `[tag]`** (критик-фикс Б-2, 2026-08-16,
   образец `scripts/gitlab_sync.py:457`): `- [ts] **FACTORY-STALLED**
   [resolved:factory-watchdog-recovered] [factory:stalled] — сообщение`
   — НЕ в теле сообщения (та форма позволяла дедуп-регексу не найти
   строку после гашения и завести вторую на повторном стуке; дедуп
   `_ESCALATION_LINE_RE` толерантен к опциональному маркеру). Оба
   действия — ТОЛЬКО на транзиции, не на каждом тике продолжающейся
   тревоги.

Всё I/O — неброcающее (класс BL-4, образец
`heartbeat_wrap._write_singleton_escalation`): ЛЮБАЯ ошибка чтения/
записи/сети (WinRT-тост) ловится локально и печатается, `main()`
дополнительно обёрнут catch-all — `sys.exit(0)` всегда.

Запуск (production, без флагов — `scripts/heartbeat.cmd` вызывает
именно так): `python scripts/factory_watchdog.py`
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

import loop_lock as ll
import sla_utils

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO / "state" / "loop.lock"
DEFAULT_MODE_FILE = REPO / "state" / "factory-mode.json"
DEFAULT_STATE_FILE = REPO / "state" / "factory-watchdog.json"
DEFAULT_SLA_FILE = REPO / "state" / "sla.yaml"
DEFAULT_ESCALATIONS_FILE = REPO / "state" / "escalations.md"
DEFAULT_ORCHESTRATOR_LOG = REPO / "state" / "orchestrator-log.md"

STALL_NO_LOCK_MIN_DEFAULT = 60.0
STALL_IN_PASS_MIN_DEFAULT = 90.0
TOAST_COOLDOWN_HOURS_DEFAULT = 4.0

FACTORY_STALLED_KEY = "FACTORY-STALLED"
FACTORY_STALLED_TAG = "factory:stalled"
FACTORY_STALLED_RESOLVED_MARKER = "[resolved:factory-watchdog-recovered]"

RULE = "factory-watchdog"
AGENT = "factory_watchdog"

MODE_STOPPED = "stopped"

POWERSHELL = "powershell.exe"
_TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


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
    """Repo-относительный путь для колонки артефакта orchestrator-log
    (критик-фикс Н-2, 2026-08-16) — с фолбэком на абсолютный путь, если
    `path` не под REPO (тестовые/scratch-пути в tmp_path не бросают
    исключение наружу, просто не сокращаются)."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _mode_snapshot(mode_data: dict | None) -> dict:
    """Нормализованный снимок mode-файла для сравнения прогресса —
    `None` (mode нет/нечитаем/трактован как «нет») даёт единый снимок
    «пусто», как и по-настоящему отсутствующий файл."""
    if mode_data is None:
        return {"mode": None, "updated_ts": None, "passes_done": None}
    return {
        "mode": mode_data.get("mode"),
        "updated_ts": mode_data.get("updated_ts"),
        "passes_done": mode_data.get("passes_done"),
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
# Критик-фикс Б-2 (2026-08-16, образец scripts/gitlab_sync.py:457
# `_escalation_key_already_pending`): якорь `[resolved:...]` — ОПЦИОНАЛЬНЫЙ
# и стоит СРАЗУ после `**KEY**`, ДО `[tag]` (не в теле сообщения) — регекс
# дедупа обязан матчить строку И с маркером, И без него, иначе повторный
# стук после гашения завёл бы ВТОРУЮ строку вместо переписывания той же.


def _write_singleton_escalation(escalations_path: Path, message: str,
                                now: datetime.datetime, *, resolved: bool = False) -> None:
    """Дедуп-запись `[factory:stalled]`-эскалации — тот же приём, что
    `loop_lock._write_loop_escalation`/`heartbeat_wrap._write_singleton_
    escalation` (класс BL-4: НИКОГДА не бросает исключение наружу).
    `key`/`tag` фиксированы (singleton, не растущий счётчик).

    `resolved=True` (Б-2, 2026-08-16) — пишет якорь `[resolved:
    factory-watchdog-recovered]` СРАЗУ после `**KEY**` (не в теле
    сообщения): `- [ts] **FACTORY-STALLED** [resolved:...] [factory:
    stalled] — сообщение`. Повторный стук (`resolved=False`) на ТОЙ ЖЕ
    строке пересобирает её БЕЗ якоря — маркер снимается автоматически
    (переписывается вся строка, не патчится точечно)."""
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
    """WinRT-тост через Windows PowerShell 5.1 (НЕ pwsh — см. докстринг
    scripts/scheduled_task_reader.py, тот же класс несовместимости).
    НИКОГДА не бросает исключение наружу — отказ тоста НЕ должен ронять
    сторож (спека К3 п.4: «Отказ тоста не роняет; exit всегда 0»)."""
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
# основной тик
# --------------------------------------------------------------------------

def run_tick(*, lock_file: Path = DEFAULT_LOCK_FILE,
            mode_file: Path = DEFAULT_MODE_FILE,
            state_file: Path = DEFAULT_STATE_FILE,
            sla_file: Path = DEFAULT_SLA_FILE,
            escalations_file: Path = DEFAULT_ESCALATIONS_FILE,
            orchestrator_log: Path = DEFAULT_ORCHESTRATOR_LOG,
            now: datetime.datetime | None = None,
            stall_no_lock_min: float | None = None,
            stall_inpass_min: float | None = None,
            cooldown_hours: float = TOAST_COOLDOWN_HOURS_DEFAULT,
            toast_fn=show_toast) -> int:
    """Один тик сторожа. Возвращает 0 ВСЕГДА (см. докстринг модуля,
    non-throwing по построению — каждый writer/toast ловит свои ошибки
    сам; здесь дополнительных try/except не нужно, кроме там, где явно
    указано)."""
    lock_file, mode_file, state_file = Path(lock_file), Path(mode_file), Path(state_file)
    sla_file, escalations_file = Path(sla_file), Path(escalations_file)
    orchestrator_log = Path(orchestrator_log)

    now = now or _utcnow()
    stall_no_lock_min = (STALL_NO_LOCK_MIN_DEFAULT if stall_no_lock_min is None
                         else stall_no_lock_min)
    stall_inpass_min = (STALL_IN_PASS_MIN_DEFAULT if stall_inpass_min is None
                        else stall_inpass_min)
    ttl_hours = sla_utils.load_loop_lock_ttl_hours(sla_file)

    # --- п.0: классификация битости трёх файлов, накопитель notes -------
    # Б-1 (критик-фикс, 2026-08-16): аномалии больше НЕ логируются в
    # orchestrator-log немедленно на каждом тике (бессрочный шум при
    # устойчиво битом файле) — собираются в `notes_now`, пишутся в
    # state-файл (перезаписывается ЦЕЛИКОМ каждый тик — актуальный
    # снимок, не журнал) и логируются ОДНОЙ строкой ТОЛЬКО когда набор
    # notes реально изменился относительно прошлого тика (дедуп).
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
        if notes_now:                       # нет валидного прошлого notes -> сравнение с []
            _append_orchestrator_line(orchestrator_log, _rel_path(state_file),
                                      "notes: " + "; ".join(notes_now), now)
        _write_state(state_file, {
            "last_lock_snapshot": lock_snap,
            "last_mode_snapshot": mode_snap,
            "last_progress_ts": _fmt_ts(now),
            "last_alert_ts": None,
            "last_state": "ok",
            "notes": notes_now,
        })
        return 0

    prev_lock_snap = watchdog_data.get("last_lock_snapshot") or {}
    prev_mode_snap = watchdog_data.get("last_mode_snapshot") or {}
    prev_progress_ts = _parse_ts(watchdog_data.get("last_progress_ts"))
    prev_alert_ts = _parse_ts(watchdog_data.get("last_alert_ts"))
    prev_state_label = watchdog_data.get("last_state") or "ok"
    # Б-3 (критик r2): типовой guard — валидный JSON-объект с нелистовым
    # `notes` (например число) ронял тик TypeError'ом ДО _write_state:
    # состояние самоподдерживалось, сторож слепнул бессрочно при exit 0.
    # Нелистовое значение трактуем как отсутствие notes (родственно п.0).
    raw_notes = watchdog_data.get("notes")
    prev_notes = [str(n) for n in raw_notes] if isinstance(raw_notes, list) else []

    changed = (lock_snap != prev_lock_snap) or (mode_snap != prev_mode_snap)
    progress_ts = now if (changed or prev_progress_ts is None) else prev_progress_ts

    # --- ветки 1-3 --------------------------------------------------------
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
        detail = (f"mode активный ({mode_data.get('mode')!r}), лок "
                 f"{'есть' if lock_here else 'нет'}, тишина {silence_min:.1f} мин "
                 f"(порог {threshold_min:.0f} мин)")

    new_state_label = "stalled" if alarm else "ok"

    # --- ветка 4: транзиции -----------------------------------------------
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
        if toast_due:
            shown, toast_detail = toast_fn("[factory:stalled]", detail)
            if shown:
                prev_alert_ts = now
            else:
                # Б-1: раньше уходило только в print() — heartbeat.cmd больше
                # НЕ перенаправляет stdout в файл (новая шапка без echo), тост-
                # отказ терял след целиком. Теперь — в notes (та же дедуп-
                # логика ниже), print() оставлен как второй, не единственный, канал.
                notes_now.append(f"тост не показан: {toast_detail}")
                print(f"toast не показан: {toast_detail}")
    elif new_state_label == "ok" and prev_state_label == "stalled":
        _write_singleton_escalation(
            escalations_file, f"восстановлено {_fmt_ts(now)}", now, resolved=True)
        _append_orchestrator_line(orchestrator_log, _rel_path(mode_file),
                                  f"stalled->ok: восстановлено в {_fmt_ts(now)}", now)

    if notes_now != prev_notes:
        # Н-7 (критик r2): не утверждать «аномалии устранены» — среди notes
        # бывают одноразовые СОБЫТИЯ (отказ тоста), которые «уходят» сами
        # на следующем тике без какого-либо устранения. Нейтральная форма
        # фиксирует факт смены набора, не интерпретируя причину.
        _append_orchestrator_line(
            orchestrator_log, _rel_path(state_file),
            ("notes: " + "; ".join(notes_now))
            if notes_now else ("notes: сняты (были: " + "; ".join(prev_notes) + ")"),
            now)

    _write_state(state_file, {
        "last_lock_snapshot": lock_snap,
        "last_mode_snapshot": mode_snap,
        "last_progress_ts": _fmt_ts(progress_ts),
        "last_alert_ts": _fmt_ts(prev_alert_ts),
        "last_state": new_state_label,
        "notes": notes_now,
    })
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="factory_watchdog — сторож окна-фабрики (spec-factory-window v6)")
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    parser.add_argument("--mode-file", default=str(DEFAULT_MODE_FILE))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--sla-file", default=str(DEFAULT_SLA_FILE))
    parser.add_argument("--escalations-file", default=str(DEFAULT_ESCALATIONS_FILE))
    parser.add_argument("--orchestrator-log", default=str(DEFAULT_ORCHESTRATOR_LOG))
    parser.add_argument("--now", help="переопределить текущее время (ISO, тесты/смок)")
    args = parser.parse_args(argv)

    now = _parse_ts(args.now) if args.now else None
    stall_no_lock_min = _env_float("AO3_FACTORY_STALL_MIN", STALL_NO_LOCK_MIN_DEFAULT)
    stall_inpass_min = _env_float("AO3_FACTORY_STALL_INPASS_MIN", STALL_IN_PASS_MIN_DEFAULT)

    try:
        return run_tick(
            lock_file=Path(args.lock_file), mode_file=Path(args.mode_file),
            state_file=Path(args.state_file), sla_file=Path(args.sla_file),
            escalations_file=Path(args.escalations_file),
            orchestrator_log=Path(args.orchestrator_log),
            now=now, stall_no_lock_min=stall_no_lock_min, stall_inpass_min=stall_inpass_min)
    except Exception as e:                    # non-throwing catch-all (спека К3)
        print(f"factory_watchdog: непойманная ошибка тика (не должна была случиться): {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
