"""scheduled_task_reader — единый локале-независимый ридер состояния
задачи Windows Task Scheduler (State/LastRunTime), spec-factory-window
v6 К5а/К5в (2026-08-16).

Почему: `schtasks.exe` печатает ЛОКАЛИЗОВАННЫЙ текст (r4 факт 5 спеки:
cp866 «Состояние: Отключено» на русской Windows) — парсить его строкой
нельзя ни в одном из двух потребителей (doctor.py / чек 3б
session-handoff SKILL). `NextRunTime` у Disabled-задачи к тому же врёт
(показывает время, как если бы задача была включена). Источник правды —
`Get-ScheduledTask(.State)` + `Get-ScheduledTaskInfo(.LastRunTime)` через
Windows PowerShell 5.1 (`powershell.exe`, НЕ `pwsh` — WinRT/CIM-обёртка
модуля ScheduledTasks под pwsh 7 в этом окружении не грузится, тот же
класс несовместимости, что и WinRT-тост scripts/factory_watchdog.py):
`.State` — .NET enum, `.ToString()` отдаёт английское имя
(Ready/Disabled/Running/…) НЕЗАВИСИМО от локали ОС; `.LastRunTime` —
`DateTime`, сериализуется через `.ToString("o")` (round-trip ISO 8601) —
тоже локале-независимо.

Публичный контракт: `read_task_state(task_name) -> TaskState`
(`ok: bool, state: str | None, last_run: datetime.datetime | None,
error: str | None`). `ok=False` — ЛЮБОЙ отказ вызова (задача не
существует, powershell недоступен/таймаут, вывод не парсится) —
вызывающий код трактует как «запрос не удался -> н/п» (К5в doctor.py /
чек 3б session-handoff SKILL), НЕ как факт отсутствия/состояния задачи
(F-30 CLAUDE.md — env-негатив без сверки не факт; здесь сверка = само
поле `ok`). `last_run=None` при `ok=True` — задача СУЩЕСТВУЕТ и
ЧИТАЕТСЯ, но никогда не запускалась (см. `_NEVER_RAN_SENTINEL_CUTOFF`,
критик-фикс Н-1: PowerShell кодирует это OLE-эпохи сентинелом, не
`null`, — сентинел распознаётся и превращается в `None` здесь).

CLI (для ручной сверки session-handoff чек 3б, без Python-импорта):
    python scripts/scheduled_task_reader.py <TaskName>
печатает `state=<...> last_run=<ISO|None>` (ok) либо `error=<...>`
(не ok) и возвращает exit 0/1 соответственно.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from dataclasses import dataclass

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

POWERSHELL = "powershell.exe"
DEFAULT_TIMEOUT_SEC = 30.0
# Критик-фикс Н-1 (2026-08-16, эмпирика критика: 0 из 200 реальных задач
# дают null): PowerShell кодирует «задача ни разу не запускалась» СЕНТИНЕЛОМ
# (наблюдалось ~1899/1899-12-30 и близкие OLE-эпохи, напр. 1999), НЕ null —
# `$i.LastRunTime` это System.DateTime (value type), `if ($i.LastRunTime)`
# для него ВСЕГДА truthy (непустой объект), ветка "$lr = $null" в PS-скрипте
# ниже практически МЕРТВА. Любой распарсенный LastRunTime РАНЬШЕ этой
# границы трактуется как сентинел -> last_run=None.
_NEVER_RAN_SENTINEL_CUTOFF = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


@dataclass(frozen=True)
class TaskState:
    ok: bool
    state: str | None
    last_run: datetime.datetime | None
    error: str | None


def _ps_escape(value: str) -> str:
    """Однокавычное PowerShell-строковое экранирование (удвоение `'`) —
    задачное имя подставляется В ТЕКСТ команды (не аргументом `-File`,
    см. докстринг read_task_state), поэтому обязано быть безопасно
    подставимо как ЛИТЕРАЛ single-quoted строки PowerShell."""
    return "'" + str(value).replace("'", "''") + "'"


def _parse_ts(value: str) -> datetime.datetime | None:
    """`.ToString('o')` -> aware datetime (UTC, если суффикс не несёт
    зону — не наш случай, PowerShell 'o' всегда несёт offset/Z, но naive
    трактуется как UTC той же семантикой, что loop_lock._parse_ts)."""
    if not value:
        return None
    try:
        ts = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts


def read_task_state(task_name: str, *, powershell: str = POWERSHELL,
                     timeout: float = DEFAULT_TIMEOUT_SEC) -> TaskState:
    """Запрос State+LastRunTime задачи `task_name`. НИКОГДА не бросает
    исключение наружу — любой отказ (вызов PowerShell не удался,
    таймаут, задача не существует, вывод не парсится) даёт
    `TaskState(ok=False, ..., error=<кратко>)`."""
    ps_name = _ps_escape(task_name)
    script = (
        "$ErrorActionPreference = 'Stop';"
        f"$t = Get-ScheduledTask -TaskName {ps_name};"
        f"$i = Get-ScheduledTaskInfo -TaskName {ps_name};"
        # `if ($i.LastRunTime)` — фактически ВСЕГДА true (DateTime value
        # type), эта ветка почти никогда не даёт null (Н-1 выше). Оставлена
        # безвредной — реальная сентинел-фильтрация теперь на стороне Python.
        "$lr = $null;"
        "if ($i.LastRunTime) { $lr = $i.LastRunTime.ToString('o') };"
        "[pscustomobject]@{State=$t.State.ToString(); LastRunTime=$lr} | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return TaskState(False, None, None, f"powershell вызов не удался: {e}")

    # Н-9 (критик r2): stderr powershell.exe на русской Windows — OEM
    # (cp866); декодирование как utf-8 давало mojibake в error=, который
    # видит оператор в doctor/handoff. stdout наш скрипт печатает сам
    # (ConvertTo-Json, ASCII-безопасно) — utf-8 с replace достаточно.
    out_text = (proc.stdout or b"").decode("utf-8", "replace")
    err_text = (proc.stderr or b"").decode("oem", "replace")

    if proc.returncode != 0:
        detail = (err_text or out_text or "").strip()
        return TaskState(False, None, None,
                          (detail[:300] if detail else f"rc={proc.returncode}"))

    try:
        data = json.loads(out_text.strip())
    except (ValueError, json.JSONDecodeError):
        return TaskState(False, None, None,
                          f"вывод не парсится как JSON: {out_text[:200]!r}")
    if not isinstance(data, dict):
        return TaskState(False, None, None, "вывод не объект JSON")

    state = data.get("State")
    last_run_raw = data.get("LastRunTime")
    last_run = None
    if last_run_raw:
        last_run = _parse_ts(str(last_run_raw))
        if last_run is None:
            return TaskState(False, state, None, f"LastRunTime не парсится: {last_run_raw!r}")
        if last_run < _NEVER_RAN_SENTINEL_CUTOFF:
            # Н-1: OLE-эпоха сентинел ("никогда не запускалась") — НЕ
            # настоящая дата последнего запуска.
            last_run = None
    return TaskState(True, state, last_run, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Единый локале-независимый ридер State/LastRunTime задачи планировщика")
    parser.add_argument("task_name")
    args = parser.parse_args(argv)

    result = read_task_state(args.task_name)
    if not result.ok:
        print(f"error={result.error}")
        return 1
    last_run_txt = result.last_run.isoformat() if result.last_run else "None"
    print(f"state={result.state} last_run={last_run_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
